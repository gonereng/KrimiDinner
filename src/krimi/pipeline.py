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
from .models import Ausarbeitung, Geruest, Story
from .render import render_kit, slug
from .story import generate_ausarbeitung, generate_geruest, load_story, merge, repair_story, save_story
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


class Zwischenstand:
    """Speichert jeden abgeschlossenen Schritt in <kit>/zwischenstand/, damit ein abgebrochener
    Lauf (z. B. Kontingent erschöpft) später ohne Verlust fortgesetzt werden kann."""

    def __init__(self, kit_dir: Path):
        self.kit_dir = Path(kit_dir)
        self.dir = self.kit_dir / "zwischenstand"
        self.path = self.dir / "fortschritt.json"
        self.data = read_json(self.path) or {}

    def reset(self) -> None:
        if self.dir.exists():
            shutil.rmtree(self.dir)
        self.data = {}

    def save(self, **updates) -> None:
        self.data.update(updates)
        write_json(self.path, self.data)

    def load_model(self, name: str, model_cls):
        p = self.dir / f"{name}.json"
        if p.exists():
            try:
                return model_cls.model_validate_json(p.read_text(encoding="utf-8"))
            except ValueError:
                return None
        return None

    def save_model(self, name: str, obj) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / f"{name}.json").write_text(obj.model_dump_json(indent=1), encoding="utf-8")

    def summary(self) -> list[str]:
        """Lesbare Liste der gesicherten Schritte (für Web/CLI)."""
        out = []
        if (self.dir / "geruest.json").exists():
            out.append("Gerüst")
        if (self.dir / "ausarbeitung.json").exists():
            out.append("Texte & Hinweise")
        if self.data.get("story"):
            n = self.data.get("korrekturen", 0)
            out.append("Story" + (f" + {n} Korrektur(en)" if n else ""))
        if self.data.get("pruefung_ok"):
            out.append("Logikprüfung")
        bilder = list((self.kit_dir / "images").glob("*.png")) if (self.kit_dir / "images").is_dir() else []
        if bilder:
            out.append(f"{len(bilder)} Bild(er)")
        return out


def read_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def check_and_repair(story: Story, client: GeminiClient, text_model: str, check_model: str,
                     progress=lambda m: None, max_korrekturen: int = MAX_KORREKTUREN,
                     zs: Zwischenstand | None = None, kit_dir: Path | None = None) -> tuple[Story, Report]:
    """Prüft und korrigiert bis zu `max_korrekturen` Mal. Mit Zwischenstand wird nach jeder
    Korrektur gesichert; ein Wiederholen setzt die Nummerierung fort (neue Cache-Schlüssel)."""
    erledigt = zs.data.get("korrekturen", 0) if zs else 0
    for i in range(max_korrekturen + 1):
        progress(f"Logikprüfung (Durchlauf {erledigt + i + 1}) …")
        report = full_check(story, client, check_model)
        if report.ok:
            progress("Logikprüfung bestanden ✔"
                     + (f" – Gegencheck findet {report.ermittlung.taeter_id} "
                        f"(Sicherheit {report.ermittlung.sicherheit:.2f})" if report.ermittlung else ""))
            return story, report
        progress(f"{len(report.fehler)} Problem(e) gefunden: " + " | ".join(report.fehler[:3])
                 + (" …" if len(report.fehler) > 3 else ""))
        if kit_dir:
            write_json(Path(kit_dir) / "report.json", report.to_dict())
        if i == max_korrekturen:
            break
        nr = erledigt + i + 1
        progress(f"Korrektur {i + 1}/{max_korrekturen} durch Gemini …")
        story = repair_story(client, text_model, story, report.fehler, nr)
        if zs and kit_dir:
            save_story(story, Path(kit_dir) / "story.json")
            zs.save(korrekturen=nr)
    return story, report


def generate_kit(thema: str, spieler: int = 6, lang: str = "de", paper: str = "a4",
                 images: bool = False, use_cache: bool = True, variante: int = 1,
                 progress=lambda m: None, client: GeminiClient | None = None,
                 kit_dir: Path | None = None, render: bool = True, resume: bool = False) -> dict:
    """Erzeugt ein Kit. Mit resume=True wird ab dem letzten gesicherten Schritt weitergemacht."""
    s = get_settings()
    client = client or GeminiClient(use_cache=use_cache)
    kit_dir = Path(kit_dir or s.output_dir / kit_name(thema, spieler, lang, variante))
    kit_dir.mkdir(parents=True, exist_ok=True)
    zs = Zwischenstand(kit_dir)
    if not resume:
        zs.reset()
    write_json(kit_dir / "params.json", {"thema": thema, "spieler": spieler, "lang": lang, "paper": paper,
                                         "images": images, "variante": variante, "render": render})
    if resume and zs.summary():
        progress("Fortsetzen – bereits gesichert: " + ", ".join(zs.summary()))
    try:
        # 1. Gerüst
        geruest = zs.load_model("geruest", Geruest) if resume else None
        if geruest is None:
            progress("Schritt 1/2: Gerüst (Täter, Motiv, Zeitleiste, Alibis) …")
            geruest = generate_geruest(client, s.text_model, thema, spieler, lang, variante=variante)
            zs.save_model("geruest", geruest)
        # 2. Ausarbeitung
        aus = zs.load_model("ausarbeitung", Ausarbeitung) if resume else None
        if aus is None:
            progress(f"Gerüst „{geruest.titel}“ – Schritt 2/2: Charaktere, Hinweise, Runden …")
            aus = generate_ausarbeitung(client, s.text_model, geruest, spieler, lang)
            zs.save_model("ausarbeitung", aus)
        # 3. Story (ggf. schon korrigierte Fassung übernehmen)
        if resume and zs.data.get("story") and (kit_dir / "story.json").exists():
            story = load_story(kit_dir / "story.json")
        else:
            story = merge(geruest, aus, thema, spieler, lang)
            save_story(story, kit_dir / "story.json")
            zs.save(story=True, korrekturen=0, pruefung_ok=False)
        # 4. Prüfung + Korrekturen
        if resume and zs.data.get("pruefung_ok") and (kit_dir / "report.json").exists():
            report = Report(**{k: v for k, v in (read_json(kit_dir / "report.json") or {}).items()
                               if k in ("fehler", "warnungen")})
            progress("Logikprüfung war bereits bestanden ✔")
        else:
            story, report = check_and_repair(story, client, s.text_model, s.check_model, progress,
                                             zs=zs, kit_dir=kit_dir)
            save_story(story, kit_dir / "story.json")
            write_json(kit_dir / "report.json", report.to_dict())
            zs.save(pruefung_ok=report.ok)
        if not report.ok:
            raise KitFailed(f"Kit ist nach {MAX_KORREKTUREN} Korrekturen noch fehlerhaft "
                            f"(mit „Wiederholen“ gibt es {MAX_KORREKTUREN} weitere Versuche):\n- "
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
        zs.save(fertig=True)
        return {"kit_dir": str(kit_dir), "files": [str(f) for f in files],
                "warnings": warnings, "usage": client.usage.to_dict()}
    finally:
        write_json(kit_dir / "usage.json", client.usage.to_dict())
        log.info("Token-Verbrauch: %s API-Aufrufe, %s Cache-Treffer, %s Tokens",
                 client.usage.api_calls, client.usage.cache_hits, client.usage.total_tokens)


def resume_kit(kit_dir: Path, progress=lambda m: None, client: GeminiClient | None = None,
               use_cache: bool = True) -> dict:
    """Setzt einen abgebrochenen Lauf mit den ursprünglichen Parametern fort."""
    params = read_json(Path(kit_dir) / "params.json")
    if not params:
        raise KitFailed(f"Keine params.json in {kit_dir} – dieses Kit kann nicht fortgesetzt werden.")
    return generate_kit(params["thema"], params["spieler"], params["lang"], params.get("paper", "a4"),
                        images=params.get("images", False), use_cache=use_cache,
                        variante=params.get("variante", 1), progress=progress, client=client,
                        kit_dir=Path(kit_dir), render=params.get("render", True), resume=True)


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
