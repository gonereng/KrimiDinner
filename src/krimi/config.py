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


@dataclass
class Settings:
    api_key: str
    text_model: str
    check_model: str
    image_model: str
    output_dir: Path
    cache_dir: Path
    app_password: str
    session_secret: str


def get_settings() -> Settings:
    text_model = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.8-flash")
    return Settings(
        api_key=os.getenv("GEMINI_API_KEY", ""),
        text_model=text_model,
        check_model=os.getenv("GEMINI_CHECK_MODEL") or text_model,
        image_model=os.getenv("GEMINI_IMAGE_MODEL", ""),
        output_dir=Path(os.getenv("KRIMI_OUTPUT_DIR", ROOT / "output")),
        cache_dir=Path(os.getenv("KRIMI_CACHE_DIR", ROOT / ".cache")),
        app_password=os.getenv("APP_PASSWORD", ""),
        session_secret=os.getenv("SESSION_SECRET", ""),
    )
