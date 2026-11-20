"""Kapselt alle Aufrufe an die Gemini API.

- Retry mit exponentiellem Backoff bei Rate-Limits (429), Serverfehlern und Timeouts
- Festplatten-Cache: sha256(Modell + Prompt + Schema) -> .cache/<hash>.json
- Token-Zählung pro Lauf (Usage)
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import random
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Type, TypeVar

from pydantic import BaseModel

from .config import PROMPTS_DIR, get_settings

log = logging.getLogger("krimi.gemini")
T = TypeVar("T", bound=BaseModel)

RETRY_CODES = {408, 429, 500, 502, 503, 504}


class GeminiError(RuntimeError):
    pass


class GeminiQuotaError(GeminiError):
    """Kontingent/Rate-Limit dauerhaft überschritten – später erneut versuchen."""


QUOTA_HINT = ("Gemini-Kontingent erschöpft (Rate-Limit oder Tageslimit). Der bisherige Fortschritt "
              "ist gespeichert – später mit „Wiederholen“ (Web) bzw. `krimi resume` fortsetzen.")


def _is_daily_quota(exc: Exception) -> bool:
    text = str(exc).lower()
    return "perday" in text or "per day" in text or "daily" in text


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


class GeminiClient:
    def __init__(self, api_key: str | None = None, use_cache: bool = True,
                 cache_dir: Path | None = None, max_retries: int = 5,
                 sleep: Callable[[float], None] = time.sleep):
        s = get_settings()
        self.api_key = api_key if api_key is not None else s.api_key
        self.use_cache = use_cache
        self.cache_dir = Path(cache_dir or s.cache_dir)
        self.max_retries = max_retries
        self.sleep = sleep
        self.usage = Usage()
        self._client = None

    # ------------------------------------------------------------------
    @property
    def client(self):
        if self._client is None:
            if not self.api_key:
                raise GeminiError("GEMINI_API_KEY fehlt (in .env eintragen).")
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def _cache_path(self, kind: str, model: str, prompt: str, extra: str = "") -> Path:
        h = hashlib.sha256(f"{kind}\n{model}\n{extra}\n{prompt}".encode()).hexdigest()
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

    def _with_retry(self, fn: Callable):
        delay = 2.0
        for attempt in range(1, self.max_retries + 1):
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001 – SDK wirft verschiedene Typen
                code = getattr(exc, "code", None)
                is_timeout = "timeout" in type(exc).__name__.lower() or "timed out" in str(exc).lower()
                if code == 429 and _is_daily_quota(exc):  # Tageslimit: Warten lohnt nicht
                    raise GeminiQuotaError(f"{QUOTA_HINT}\n({exc})") from exc
                if (code in RETRY_CODES or is_timeout) and attempt < self.max_retries:
                    wait = delay + random.uniform(0, 1)
                    log.warning("Gemini-Fehler (%s), neuer Versuch in %.1fs …", code or exc, wait)
                    self.sleep(wait)
                    delay *= 2
                    continue
                if code == 429:
                    raise GeminiQuotaError(f"{QUOTA_HINT}\n({exc})") from exc
                raise GeminiError(f"Gemini-Aufruf fehlgeschlagen: {exc}") from exc

    @staticmethod
    def _usage_meta(resp) -> dict:
        um = getattr(resp, "usage_metadata", None)
        if not um:
            return {}
        return {
            "prompt": getattr(um, "prompt_token_count", 0) or 0,
            "output": getattr(um, "candidates_token_count", 0) or 0,
            "total": getattr(um, "total_token_count", 0) or 0,
        }

    # ------------------------------------------------------------------
    def generate_json(self, prompt: str, schema: Type[T], model: str,
                      label: str = "", temperature: float = 0.8) -> T:
        """Strukturierte Ausgabe als Pydantic-Objekt."""
        schema_json = json.dumps(schema.model_json_schema(), sort_keys=True)
        path = self._cache_path("json", model, prompt, schema_json)
        cached = self._read_cache(path)
        if cached is not None:
            self.usage.add(label or schema.__name__, model, cached.get("usage"), cached=True)
            return schema.model_validate_json(cached["text"])

        from google.genai import types

        def call():
            try:
                cfg = types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema, temperature=temperature)
            except Exception:  # Schema nicht konvertierbar -> rohes JSON-Schema
                cfg = types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_json_schema=schema.model_json_schema(), temperature=temperature)
            return self.client.models.generate_content(model=model, contents=prompt, config=cfg)

        resp = self._with_retry(call)
        text = resp.text or ""
        meta = self._usage_meta(resp)
        try:
            obj = schema.model_validate_json(text)
        except Exception as exc:
            raise GeminiError(f"Antwort passt nicht zum Schema {schema.__name__}: {exc}\n{text[:500]}") from exc
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

        from google.genai import types

        def call():
            return self.client.models.generate_content(
                model=model, contents=prompt,
                config=types.GenerateContentConfig(response_modalities=["IMAGE"]))

        resp = self._with_retry(call)
        meta = self._usage_meta(resp)
        data = None
        for cand in resp.candidates or []:
            for part in (cand.content.parts if cand.content else []) or []:
                inline = getattr(part, "inline_data", None)
                if inline and inline.data:
                    data = inline.data
                    break
            if data:
                break
        self.usage.add(label, model, meta, cached=False)
        self._write_cache(path, {"data": base64.b64encode(data).decode() if data else None,
                                 "usage": meta, "model": model})
        return data
