"""Kapselt alle KI-Aufrufe – wahlweise DeepSeek oder Google Gemini (LLM_PROVIDER in .env).

Gemeinsam für beide Anbieter:
- Retry mit exponentiellem Backoff bei Rate-Limits (429), Serverfehlern und Timeouts
- klare Fehler bei erschöpftem Kontingent / Guthaben (QuotaError) -> „Wiederholen“ später
- Festplatten-Cache: sha256(Anbieter + Modell + Prompt + Schema) -> .cache/<hash>.json
- Token-Zählung pro Lauf (Usage)
- Antworten werden gegen das Pydantic-Schema geprüft; ist eine Antwort kein gültiges
  JSON nach Schema, bekommt das Modell die Fehlermeldung und darf nachbessern.

Bilder erzeugt nur Gemini (DeepSeek hat kein Bildmodell).
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import random
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Type, TypeVar

from pydantic import BaseModel, ValidationError

from .config import PROMPTS_DIR, get_settings

log = logging.getLogger("krimi.llm")
T = TypeVar("T", bound=BaseModel)

RETRY_CODES = {408, 429, 500, 502, 503, 504}
MAX_FORMAT_FIXES = 2  # so oft darf das Modell eine ungültige JSON-Antwort nachbessern


class LLMError(RuntimeError):
    pass


class QuotaError(LLMError):
    """Kontingent, Rate-Limit oder Guthaben dauerhaft erschöpft – später erneut versuchen."""


QUOTA_HINT = ("KI-Kontingent erschöpft bzw. Guthaben aufgebraucht. Der bisherige Fortschritt "
              "ist gespeichert – später mit „Wiederholen“ (Web) bzw. `krimi resume` fortsetzen.")


class APIStatusError(LLMError):
    def __init__(self, code: int, message: str):
        super().__init__(f"HTTP {code}: {message}")
        self.code = code


def _is_hard_quota(exc: Exception) -> bool:
    """Fälle, in denen Warten nichts bringt: Tageslimit (Gemini), kein Guthaben (DeepSeek 402)."""
    if getattr(exc, "code", None) == 402:
        return True
    text = str(exc).lower()
    return getattr(exc, "code", None) == 429 and ("perday" in text or "per day" in text or "daily" in text)


@dataclass
class Usage:
    api_calls: int = 0
    cache_hits: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    calls: list[dict] = field(default_factory=list)

    def add(self, label: str, model: str, meta: dict | None, cached: bool) -> None:
        meta = meta or {}
        if cached:
            self.cache_hits += 1
        else:
            self.api_calls += 1
            self.prompt_tokens += meta.get("prompt", 0)
            self.output_tokens += meta.get("output", 0)
            self.total_tokens += meta.get("total", 0)
        self.calls.append({"label": label, "model": model, "cached": cached, **meta})
        log.info("%s [%s] %s – Tokens: %s", label, model, "CACHE" if cached else "API",
                 meta.get("total", 0) if not cached else 0)

    def to_dict(self) -> dict:
        return asdict(self)


def load_prompt(name: str, **values) -> str:
    """Lädt prompts/<name>.txt und ersetzt {{platzhalter}}."""
    text = (PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8")
    for key, val in values.items():
        text = text.replace("{{" + key + "}}", str(val))
    return text


def extract_json(text: str) -> str:
    """Holt das JSON-Objekt aus einer Antwort (entfernt ```json-Zäune und Vor-/Nachtext)."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else text


def _add_meta(a: dict, b: dict) -> dict:
    return {k: a.get(k, 0) + b.get(k, 0) for k in ("prompt", "output", "total")}


# --------------------------------------------------------------------------
# Backends
# --------------------------------------------------------------------------

class DeepSeekBackend:
    """DeepSeek über die OpenAI-kompatible Chat-Completions-API."""
    name = "deepseek"

    def __init__(self, api_key: str, base_url: str, max_tokens: int = 32000, thinking: str = "",
                 timeout: float = 600.0):
        self.api_key, self.base_url = api_key, base_url.rstrip("/")
        self.max_tokens, self.thinking, self.timeout = max_tokens, thinking, timeout
        self._http = None

    @property
    def http(self):
        if self._http is None:
            if not self.api_key:
                raise LLMError("DEEPSEEK_API_KEY fehlt (in .env eintragen).")
            import httpx
            self._http = httpx.Client(timeout=self.timeout)
        return self._http

    def complete_json(self, prompt: str, schema: Type[BaseModel], model: str,
                      temperature: float) -> tuple[str, dict]:
        schema_txt = json.dumps(schema.model_json_schema(), ensure_ascii=False, separators=(",", ":"))
        system = ("Du bist ein präziser Generator für strukturierte Daten. Antworte ausschließlich mit "
                  "EINEM gültigen JSON-Objekt – ohne Markdown, ohne Erklärungen. Das JSON muss exakt "
                  "diesem JSON-Schema entsprechen (alle Pflichtfelder, korrekte Typen, Feldnamen "
                  f"unverändert):\n{schema_txt}")
        body = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        if self.thinking in ("enabled", "disabled"):
            body["thinking"] = {"type": self.thinking}
        resp = self.http.post(f"{self.base_url}/chat/completions", json=body,
                              headers={"Authorization": f"Bearer {self.api_key}"})
        if resp.status_code != 200:
            try:
                msg = resp.json().get("error", {}).get("message") or resp.text
            except ValueError:
                msg = resp.text
            raise APIStatusError(resp.status_code, msg[:500])
        data = resp.json()
        choice = data["choices"][0]
        if choice.get("finish_reason") == "length":
            raise LLMError("Die Antwort wurde abgeschnitten (Längenlimit). DEEPSEEK_MAX_TOKENS in .env "
                           "erhöhen oder ein Modell mit längerer Ausgabe wählen.")
        u = data.get("usage") or {}
        meta = {"prompt": u.get("prompt_tokens", 0), "output": u.get("completion_tokens", 0),
                "total": u.get("total_tokens", 0)}
        return choice["message"].get("content") or "", meta

    def generate_image(self, prompt: str, model: str):
        raise LLMError("DeepSeek kann keine Bilder erzeugen.")


class GeminiBackend:
    """Google Gemini über das offizielle SDK (google-genai)."""
    name = "gemini"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = None

    @property
    def client(self):
        if self._client is None:
            if not self.api_key:
                raise LLMError("GEMINI_API_KEY fehlt (in .env eintragen).")
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    @staticmethod
    def _meta(resp) -> dict:
        um = getattr(resp, "usage_metadata", None)
        if not um:
            return {}
        return {"prompt": getattr(um, "prompt_token_count", 0) or 0,
                "output": getattr(um, "candidates_token_count", 0) or 0,
                "total": getattr(um, "total_token_count", 0) or 0}

    def complete_json(self, prompt: str, schema: Type[BaseModel], model: str,
                      temperature: float) -> tuple[str, dict]:
        from google.genai import types
        try:
            cfg = types.GenerateContentConfig(response_mime_type="application/json",
                                              response_schema=schema, temperature=temperature)
        except Exception:  # Schema nicht konvertierbar -> rohes JSON-Schema
            cfg = types.GenerateContentConfig(response_mime_type="application/json",
                                              response_json_schema=schema.model_json_schema(),
                                              temperature=temperature)
        resp = self.client.models.generate_content(model=model, contents=prompt, config=cfg)
        return resp.text or "", self._meta(resp)

    def generate_image(self, prompt: str, model: str) -> tuple[bytes | None, dict]:
        from google.genai import types
        resp = self.client.models.generate_content(
            model=model, contents=prompt, config=types.GenerateContentConfig(response_modalities=["IMAGE"]))
        for cand in resp.candidates or []:
            for part in (cand.content.parts if cand.content else []) or []:
                inline = getattr(part, "inline_data", None)
                if inline and inline.data:
                    return inline.data, self._meta(resp)
        return None, self._meta(resp)


def make_backend(provider: str | None = None, api_key: str | None = None):
    s = get_settings()
    provider = provider or s.provider
    if provider == "deepseek":
        return DeepSeekBackend(api_key if api_key is not None else s.api_key, s.base_url,
                               s.max_tokens, s.thinking)
    if provider == "gemini":
        key = api_key if api_key is not None else (s.api_key if s.provider == "gemini" else s.image_api_key)
        return GeminiBackend(key)
    raise LLMError(f"Unbekannter Anbieter '{provider}'")


# --------------------------------------------------------------------------
# Client mit Cache, Retry und Token-Zählung
# --------------------------------------------------------------------------

class LLMClient:
    def __init__(self, provider: str | None = None, api_key: str | None = None, use_cache: bool = True,
                 cache_dir: Path | None = None, max_retries: int = 5,
                 sleep: Callable[[float], None] = time.sleep, backend=None):
        s = get_settings()
        self.backend = backend or make_backend(provider, api_key)
        self.provider = getattr(self.backend, "name", provider or s.provider)
        self.use_cache = use_cache
        self.cache_dir = Path(cache_dir or s.cache_dir)
        self.max_retries = max_retries
        self.sleep = sleep
        self.usage = Usage()

    # -- Cache ------------------------------------------------------------
    def _cache_path(self, kind: str, model: str, prompt: str, extra: str = "") -> Path:
        h = hashlib.sha256(f"{self.provider}:{kind}\n{model}\n{extra}\n{prompt}".encode()).hexdigest()
        return self.cache_dir / f"{h}.json"

    def _read_cache(self, path: Path) -> dict | None:
        if self.use_cache and path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return None
        return None

    def _write_cache(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    # -- Retry ------------------------------------------------------------
    def _with_retry(self, fn: Callable):
        delay = 2.0
        for attempt in range(1, self.max_retries + 1):
            try:
                return fn()
            except LLMError as exc:
                if not isinstance(exc, APIStatusError):
                    raise  # z. B. fehlender Key, abgeschnittene Antwort
                err = exc
            except Exception as exc:  # noqa: BLE001 – SDKs/HTTP werfen verschiedene Typen
                err = exc
            code = getattr(err, "code", None)
            is_timeout = "timeout" in type(err).__name__.lower() or "timed out" in str(err).lower()
            if _is_hard_quota(err):
                raise QuotaError(f"{QUOTA_HINT}\n({err})") from err
            if (code in RETRY_CODES or is_timeout) and attempt < self.max_retries:
                wait = delay + random.uniform(0, 1)
                log.warning("KI-Fehler (%s), neuer Versuch in %.1fs …", code or err, wait)
                self.sleep(wait)
                delay *= 2
                continue
            if code == 429:
                raise QuotaError(f"{QUOTA_HINT}\n({err})") from err
            raise LLMError(f"KI-Aufruf fehlgeschlagen: {err}") from err

    # -- Öffentliche Methoden ----------------------------------------------
    def generate_json(self, prompt: str, schema: Type[T], model: str,
                      label: str = "", temperature: float = 0.8) -> T:
        """Strukturierte Ausgabe als Pydantic-Objekt."""
        schema_json = json.dumps(schema.model_json_schema(), sort_keys=True)
        path = self._cache_path("json", model, prompt, schema_json)
        cached = self._read_cache(path)
        if cached is not None:
            self.usage.add(label or schema.__name__, model, cached.get("usage"), cached=True)
            return schema.model_validate_json(cached["text"])

        meta: dict = {}
        current = prompt
        for fix in range(MAX_FORMAT_FIXES + 1):
            text, m = self._with_retry(lambda: self.backend.complete_json(current, schema, model, temperature))
            meta = _add_meta(meta, m)
            text = extract_json(text)
            try:
                obj = schema.model_validate_json(text)
                break
            except (ValidationError, ValueError) as exc:
                fehler = str(exc)[:1500]
                if fix == MAX_FORMAT_FIXES:
                    self.usage.add(label or schema.__name__, model, meta, cached=False)
                    raise LLMError(f"Antwort passt auch nach {MAX_FORMAT_FIXES} Nachbesserungen nicht zum "
                                   f"Schema {schema.__name__}: {fehler}\n{text[:300]}") from exc
                log.warning("%s: ungültiges JSON, Nachbesserung %s …", label or schema.__name__, fix + 1)
                current = (f"{prompt}\n\nACHTUNG: Deine vorige Antwort war ungültig und wurde verworfen. "
                           f"Fehler bei der Prüfung:\n{fehler}\n\nAntworte erneut mit dem VOLLSTÄNDIGEN, "
                           f"gültigen JSON-Objekt nach Schema.")
        self.usage.add(label or schema.__name__, model, meta, cached=False)
        self._write_cache(path, {"text": text, "usage": meta, "model": model})
        return obj

    def generate_image(self, prompt: str, model: str, label: str = "Bild") -> bytes | None:
        """Erzeugt ein Bild (PNG/JPEG-Bytes) oder None, wenn das Modell keins liefert."""
        path = self._cache_path("image", model, prompt)
        cached = self._read_cache(path)
        if cached is not None:
            self.usage.add(label, model, cached.get("usage"), cached=True)
            return base64.b64decode(cached["data"]) if cached.get("data") else None
        data, meta = self._with_retry(lambda: self.backend.generate_image(prompt, model))
        self.usage.add(label, model, meta, cached=False)
        self._write_cache(path, {"data": base64.b64encode(data).decode() if data else None,
                                 "usage": meta, "model": model})
        return data
