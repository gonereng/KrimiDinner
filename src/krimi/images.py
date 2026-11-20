"""Optionale Illustrationen über Gemini (GEMINI_IMAGE_MODEL): Cover + Charakterporträts.

DeepSeek hat kein Bildmodell – Bilder brauchen daher immer einen GEMINI_API_KEY."""
from __future__ import annotations

import logging
from pathlib import Path

from .llm_client import LLMClient, QuotaError, load_prompt
from . import themes
from .models import Story

log = logging.getLogger("krimi.images")



def generate_images(story: Story, client: LLMClient, model: str, kit_dir: Path,
                    progress=lambda msg: None) -> list[str]:
    """Erzeugt images/cover.png und images/<charakter-id>.png. Gibt Warnungen zurück."""
    warnings: list[str] = []
    if not model:
        return ["Kein GEMINI_IMAGE_MODEL gesetzt – Bilder übersprungen."]
    img_dir = Path(kit_dir) / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    stil = themes.get_theme(story.design).bildstil
    jobs = [("cover", load_prompt("bild_cover", thema=story.thema, ort=story.setting.ort,
                                  zeit=story.setting.zeit, atmosphaere=story.setting.atmosphaere, stil=stil))]
    for c in story.charaktere:
        jobs.append((c.id, load_prompt("bild_portrait", name=c.name, rolle=c.rolle, zeit=story.setting.zeit,
                                       ort=story.setting.ort, kostuem=c.kostuemtipp, stil=stil)))
    for i, (name, prompt) in enumerate(jobs, 1):
        if (img_dir / f"{name}.png").exists():  # schon vorhanden (z. B. beim Fortsetzen)
            continue
        progress(f"Bild {i}/{len(jobs)}: {name}")
        try:
            data = client.generate_image(prompt, model, label=f"Bild {name}")
        except QuotaError:
            raise  # Kontingent weg: abbrechen, damit „Wiederholen“ die fehlenden Bilder nachholt
        except Exception as exc:  # Bilder sind optional – Kit bleibt nutzbar
            warnings.append(f"Bild '{name}' fehlgeschlagen: {exc}")
            continue
        if data:
            (img_dir / f"{name}.png").write_bytes(data)
        else:
            warnings.append(f"Bild '{name}': Modell hat kein Bild geliefert")
    return warnings
