"""Optionale Illustrationen über GEMINI_IMAGE_MODEL (Cover + Charakterporträts)."""
from __future__ import annotations

import logging
from pathlib import Path

from .gemini_client import GeminiClient, load_prompt
from .models import Story

log = logging.getLogger("krimi.images")

STIL = {
    "chalet": "Vintage-Gouache-Illustration im Stil alter Skiplakate der 1980er, gedeckte Blau- und Goldtöne, weiches Licht",
    "noir": "Schwarz-Weiß-Tuschezeichnung im Film-noir-Stil, harte Schatten, Kreuzschraffur",
    "klassisch": "Aquarell-Illustration im Stil klassischer Kriminalromane der 1930er, warme Bordeaux- und Cremetöne",
}


def generate_images(story: Story, client: GeminiClient, model: str, kit_dir: Path,
                    progress=lambda msg: None) -> list[str]:
    """Erzeugt images/cover.png und images/<charakter-id>.png. Gibt Warnungen zurück."""
    warnings: list[str] = []
    if not model:
        return ["Kein GEMINI_IMAGE_MODEL gesetzt – Bilder übersprungen."]
    img_dir = Path(kit_dir) / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    stil = STIL.get(story.design, STIL["klassisch"])
    jobs = [("cover", load_prompt("bild_cover", thema=story.thema, ort=story.setting.ort,
                                  zeit=story.setting.zeit, atmosphaere=story.setting.atmosphaere, stil=stil))]
    for c in story.charaktere:
        jobs.append((c.id, load_prompt("bild_portrait", name=c.name, rolle=c.rolle, zeit=story.setting.zeit,
                                       ort=story.setting.ort, kostuem=c.kostuemtipp, stil=stil)))
    for i, (name, prompt) in enumerate(jobs, 1):
        progress(f"Bild {i}/{len(jobs)}: {name}")
        try:
            data = client.generate_image(prompt, model, label=f"Bild {name}")
        except Exception as exc:  # Bilder sind optional – Kit bleibt nutzbar
            warnings.append(f"Bild '{name}' fehlgeschlagen: {exc}")
            continue
        if data:
            (img_dir / f"{name}.png").write_bytes(data)
        else:
            warnings.append(f"Bild '{name}': Modell hat kein Bild geliefert")
    return warnings
