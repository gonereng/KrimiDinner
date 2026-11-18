"""Gesamtablauf: Story -> Prüfung (+ Korrekturschleife) -> Bilder -> PDFs.

Wird von CLI und Web-App gleichermaßen benutzt.
"""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from .config import get_settings
from .gemini_client import GeminiClient
from .images import generate_images
from .models import Story
from .render import render_kit, slug
from .story import generate_story, load_story, repair_story, save_story
from .validate import Report, full_check

log = logging.getLogger("krimi.pipeline")
MAX_KORREKTUREN = 3
DEMO_STORY = Path(__file__).parent / "demo" / "silvester_schneechalet.json"


class KitFailed(RuntimeError):
    def __init__(self, message: str, report: Report | None = None):
        super().__init__(message)
        self.report = report


def kit_name(thema: str, spieler: int, lang: str, variante: int = 1) -> str:
    name = f"{slug(thema)}-{spieler}p-{lang}"
    return name if variante <= 1 else f"{name}-v{variante}"


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def check_and_repair(story: Story, client: GeminiClient, text_model: str, check_model: str,
                     progress=lambda m: None, max_korrekturen: int = MAX_KORREKTUREN) -> tuple[Story, Report]:
    for versuch in range(max_korrekturen + 1):
        progress(f"Logikprüfung (Durchlauf {versuch + 1}) …")
        report = full_check(story, client, check_model)
        if report.ok:
            progress("Logikprüfung bestanden ✔"
                     + (f" – Gegencheck findet {report.ermittlung.taeter_id} "
                        f"(Sicherheit {report.ermittlung.sicherheit:.2f})" if report.ermittlung else ""))
            return story, report
        progress(f"{len(report.fehler)} Problem(e) gefunden: " + " | ".join(report.fehler[:3])
                 + (" …" if len(report.fehler) > 3 else ""))
        if versuch == max_korrekturen:
            break
        progress(f"Korrektur {versuch + 1}/{max_korrekturen} durch Gemini …")
        story = repair_story(client, text_model, story, report.fehler, versuch + 1)
    return story, report


def generate_kit(thema: str, spieler: int = 6, lang: str = "de", paper: str = "a4",
                 images: bool = False, use_cache: bool = True, variante: int = 1,
                 progress=lambda m: None, client: GeminiClient | None = None,
                 kit_dir: Path | None = None, render: bool = True) -> dict:
    s = get_settings()
    client = client or GeminiClient(use_cache=use_cache)
    kit_dir = Path(kit_dir or s.output_dir / kit_name(thema, spieler, lang, variante))
    kit_dir.mkdir(parents=True, exist_ok=True)
    try:
        story = generate_story(client, s.text_model, thema, spieler, lang, progress=progress,
                               variante=variante)
        save_story(story, kit_dir / "story.json")
        story, report = check_and_repair(story, client, s.text_model, s.check_model, progress)
        save_story(story, kit_dir / "story.json")
        write_json(kit_dir / "report.json", report.to_dict())
        if not report.ok:
            raise KitFailed(f"Kit ist nach {MAX_KORREKTUREN} Korrekturen noch fehlerhaft:\n- "
                            + "\n- ".join(report.fehler), report)
        warnings = list(report.warnungen)
        if not render:
            return {"kit_dir": str(kit_dir), "files": [str(kit_dir / "story.json")],
                    "warnings": warnings, "usage": client.usage.to_dict()}
        if images:
            progress("Bilder werden erzeugt …")
            warnings += generate_images(story, client, s.image_model, kit_dir, progress)
        progress("PDFs werden gesetzt …")
        files, render_warn = render_kit(story, kit_dir, paper)
        warnings += render_warn
        return {"kit_dir": str(kit_dir), "files": [str(f) for f in files],
                "warnings": warnings, "usage": client.usage.to_dict()}
    finally:
        write_json(kit_dir / "usage.json", client.usage.to_dict())
        log.info("Token-Verbrauch: %s API-Aufrufe, %s Cache-Treffer, %s Tokens",
                 client.usage.api_calls, client.usage.cache_hits, client.usage.total_tokens)


def validate_kit(story_path: Path, gegencheck: bool = True, use_cache: bool = True) -> Report:
    story = load_story(story_path)
    if gegencheck:
        s = get_settings()
        client = GeminiClient(use_cache=use_cache)
        report = full_check(story, client, s.check_model)
        write_json(story_path.parent / "usage-validate.json", client.usage.to_dict())
    else:
        report = full_check(story)
    write_json(story_path.parent / "report.json", report.to_dict())
    return report


def render_existing(kit_dir: Path, paper: str = "a4") -> tuple[list[Path], list[str]]:
    story = load_story(Path(kit_dir) / "story.json")
    return render_kit(story, Path(kit_dir), paper)


def create_demo(kit_dir: Path | None = None, paper: str = "a4") -> tuple[Path, list[Path], list[str]]:
    kit_dir = Path(kit_dir or get_settings().output_dir / "demo-silvester-im-schneechalet")
    kit_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(DEMO_STORY, kit_dir / "story.json")
    story = load_story(kit_dir / "story.json")
    write_json(kit_dir / "report.json", full_check(story).to_dict())
    files, warn = render_kit(story, kit_dir, paper)
    return kit_dir, files, warn
