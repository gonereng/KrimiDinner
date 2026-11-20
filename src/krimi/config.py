"""Konfiguration aus .env / Umgebungsvariablen."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = ROOT / "prompts"
TEMPLATES_DIR = ROOT / "templates"

load_dotenv(ROOT / ".env")
load_dotenv()  # zusätzlich .env im aktuellen Verzeichnis


PROVIDERS = ("deepseek", "gemini")
DEFAULT_MODELS = {"deepseek": "deepseek-v4-flash", "gemini": "gemini-3.8-flash"}


@dataclass
class Settings:
    provider: str          # "deepseek" oder "gemini" – für Story, Texte und Prüfung
    api_key: str           # Key des gewählten Anbieters
    text_model: str
    check_model: str
    base_url: str          # nur DeepSeek (OpenAI-kompatibler Endpunkt)
    max_tokens: int        # nur DeepSeek: maximale Antwortlänge
    thinking: str          # nur DeepSeek: "", "enabled" oder "disabled"
    image_api_key: str     # Bilder laufen immer über Gemini (DeepSeek kann keine Bilder)
    image_model: str
    output_dir: Path
    cache_dir: Path
    app_password: str
    session_secret: str

    @property
    def provider_name(self) -> str:
        return {"deepseek": "DeepSeek", "gemini": "Gemini"}.get(self.provider, self.provider)

    @property
    def key_var(self) -> str:
        return f"{self.provider.upper()}_API_KEY"


def get_settings() -> Settings:
    provider = os.getenv("LLM_PROVIDER", "deepseek").strip().lower()
    if provider not in PROVIDERS:
        raise ValueError(f"LLM_PROVIDER muss 'deepseek' oder 'gemini' sein, nicht '{provider}'")
    P = provider.upper()
    text_model = os.getenv(f"{P}_TEXT_MODEL") or DEFAULT_MODELS[provider]
    return Settings(
        provider=provider,
        api_key=os.getenv(f"{P}_API_KEY", ""),
        text_model=text_model,
        check_model=os.getenv(f"{P}_CHECK_MODEL") or text_model,
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        max_tokens=int(os.getenv("DEEPSEEK_MAX_TOKENS", "32000")),
        thinking=os.getenv("DEEPSEEK_THINKING", "").strip().lower(),
        image_api_key=os.getenv("GEMINI_API_KEY", ""),
        image_model=os.getenv("GEMINI_IMAGE_MODEL", ""),
        output_dir=Path(os.getenv("KRIMI_OUTPUT_DIR", ROOT / "output")),
        cache_dir=Path(os.getenv("KRIMI_CACHE_DIR", ROOT / ".cache")),
        app_password=os.getenv("APP_PASSWORD", ""),
        session_secret=os.getenv("SESSION_SECRET", ""),
    )
