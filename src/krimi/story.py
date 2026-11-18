"""Story-Generierung in zwei Schritten: erst Gerüst (Logik), dann Ausarbeitung (Texte)."""
from __future__ import annotations

import json

from .gemini_client import GeminiClient, load_prompt
from .models import Ausarbeitung, Geruest, Story

SPRACHEN = {"de": "Deutsch", "en": "Englisch (English)"}


def sprache_name(lang: str) -> str:
    return SPRACHEN.get(lang, lang)


def generate_geruest(client: GeminiClient, model: str, thema: str, spieler: int,
                     lang: str = "de", dauer: str = "2 Stunden") -> Geruest:
    prompt = load_prompt("geruest", thema=thema, spieler=spieler, dauer=dauer,
                         sprache_name=sprache_name(lang))
    return client.generate_json(prompt, Geruest, model, label="Gerüst")


def generate_ausarbeitung(client: GeminiClient, model: str, geruest: Geruest, spieler: int,
                          lang: str = "de", dauer: str = "2 Stunden") -> Ausarbeitung:
    prompt = load_prompt(
        "ausarbeitung",
        geruest_json=geruest.model_dump_json(indent=1),
        spieler=spieler, dauer=dauer, sprache_name=sprache_name(lang),
        hinweise_anzahl=max(3 * spieler + 3, 18))
    return client.generate_json(prompt, Ausarbeitung, model, label="Ausarbeitung")


def merge(geruest: Geruest, aus: Ausarbeitung, thema: str, spieler: int, lang: str) -> Story:
    """Führt Gerüst und Ausarbeitung zu einer vollständigen Story zusammen."""
    details = {d.id: d for d in aus.charaktere}
    charaktere = []
    for gc in geruest.charaktere:
        d = details.get(gc.id)
        charaktere.append({
            **gc.model_dump(),
            **({k: v for k, v in d.model_dump().items() if k != "id"} if d else {}),
        })
    return Story(
        titel=geruest.titel, untertitel=geruest.untertitel, thema=thema, sprache=lang,
        spieler=spieler, design=geruest.design,
        seed=int.from_bytes(thema.encode()[:4].ljust(4, b"\0"), "big") % 100000,
        einleitung=aus.einleitung, setting=geruest.setting, opfer=geruest.opfer,
        charaktere=charaktere, fakten=geruest.fakten, zeitleiste=geruest.zeitleiste,
        hinweise=aus.hinweise, runden=aus.runden, aufloesung=aus.aufloesung,
        gastgeber=aus.gastgeber,
    )


def generate_story(client: GeminiClient, model: str, thema: str, spieler: int,
                   lang: str = "de", progress=lambda msg: None) -> Story:
    progress("Schritt 1/2: Gerüst (Täter, Motiv, Zeitleiste, Alibis) …")
    geruest = generate_geruest(client, model, thema, spieler, lang)
    progress(f"Gerüst fertig: „{geruest.titel}“ – Schritt 2/2: Charaktere, Hinweise, Runden …")
    aus = generate_ausarbeitung(client, model, geruest, spieler, lang)
    return merge(geruest, aus, thema, spieler, lang)


def repair_story(client: GeminiClient, model: str, story: Story, fehler: list[str],
                 versuch: int) -> Story:
    """Schickt die Fehlerliste an Gemini und bekommt ein korrigiertes Kit zurück."""
    taeter = story.taeter()
    prompt = load_prompt(
        "korrektur",
        fehler="\n".join(f"- {f}" for f in fehler),
        story_json=story.model_dump_json(indent=1),
        taeter_id=taeter[0].id if taeter else "?",
        sprache_name=sprache_name(story.sprache))
    fixed = client.generate_json(prompt, Story, model, label=f"Korrektur {versuch}", temperature=0.4)
    # Metadaten, die Gemini nicht ändern soll, beibehalten
    fixed.thema, fixed.spieler, fixed.sprache, fixed.seed = story.thema, story.spieler, story.sprache, story.seed
    return fixed


def save_story(story: Story, path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(story.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")


def load_story(path) -> Story:
    return Story.model_validate_json(path.read_text(encoding="utf-8"))
