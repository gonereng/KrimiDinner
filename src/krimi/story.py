"""Story-Generierung in zwei Schritten: erst Gerüst (Logik), dann Ausarbeitung (Texte)."""
from __future__ import annotations

import hashlib
import json

from .llm_client import LLMClient, load_prompt
from . import themes
from .models import Ausarbeitung, Geruest, Story

SPRACHEN = {"de": "Deutsch", "en": "Englisch (English)"}


def sprache_name(lang: str) -> str:
    return SPRACHEN.get(lang, lang)


def spieler_text(von: int, bis: int) -> str:
    return str(von) if bis <= von else f"{von}–{bis} (variabel)"


def besetzung_text(von: int, bis: int) -> str:
    """Vorgaben zur Besetzung für das Gerüst."""
    if bis <= von:
        return (f"- Anzahl Spieler: {von} (= genau {von} spielbare Charaktere; das Opfer ist KEIN Spieler). "
                f"Setze bei allen Charakteren ab_spieler = {von} und flexibel = false.")
    stufen = ", ".join(str(n) for n in range(von + 1, bis + 1))
    return f"""- VARIABLE SPIELERZAHL: {von} bis {bis} Spieler. Erfinde genau {bis} spielbare Charaktere (das Opfer ist KEIN Spieler):
  • {von} Stammfiguren mit ab_spieler = {von} – sie werden immer besetzt. Täter:in sowie alle Fakten und Alibis, die den Fall entscheiden, gehören zu den Stammfiguren.
  • {bis - von} optionale Figuren mit ab_spieler = {stufen} (jede Zahl genau einmal). Sie werden nur besetzt, wenn so viele Gäste kommen.
  • Optionale Figuren sind unschuldig, haben aber eigene Motive und Geheimnisse (gute falsche Fährten). Ihr Alibi lässt sich durch einen eigenen Fakt bestätigen. Kein Alibi einer Stammfigur darf von einer optionalen Figur abhängen; optionale Figuren stehen in der Zeitleiste in eigenen Einträgen.
  • Optionale Figuren sind geschlechtsflexibel (flexibel = true): ein Vorname, der zu jedem Geschlecht passt (z. B. Kim, Alex, Sascha, Robin, Charlie, Toni, Jo, Luca), die Rolle in beiden Formen (z. B. "Ärztin / Arzt") und in allen Texten über sie KEINE Pronomen wie er/sie/ihm/ihr – immer den Namen verwenden.
  • Stammfiguren haben flexibel = false."""


def besetzung_regeln(von: int, bis: int) -> str:
    """Regeln für Hinweise und Texte bei variabler Spielerzahl (Ausarbeitung und Korrektur)."""
    if bis <= von:
        return ""
    return f"""
VARIABLE SPIELERZAHL ({von}–{bis}): Charaktere mit ab_spieler > {von} sind optional und fehlen bei weniger Spielern. Deshalb:
- Alle Hinweise, die für die Lösung nötig sind (Belastung des Täters, Entlastung der Stammfiguren), gehen an Stammfiguren und erwähnen KEINE optionale Figur.
- Jede optionale Figur bekommt in jeder Runde mindestens einen eigenen Hinweis (empfaenger = diese Figur); einer davon entlastet sie (entlastet = ihre ID). Diese Hinweise dürfen Stammfiguren erwähnen, aber keine optionale Figur mit höherem ab_spieler.
- Einleitung, Runden, Auflösung, Gastgeber-Texte sowie Profil, Geheimnis, Motiv, Alibi und Beziehungen der Stammfiguren erwähnen KEINE optionale Figur. Beziehungen nur zu Figuren mit gleichem oder kleinerem ab_spieler.
- Die Auflösung (Schritte, Tathergang) kommt allein mit den Hinweisen der Stammfiguren aus.
- Über geschlechtsflexible Figuren (flexibel = true) immer mit Namen schreiben, ohne Pronomen; Kostümtipps passend für jedes Geschlecht."""


def generate_geruest(client: LLMClient, model: str, thema: str, spieler: int,
                     lang: str = "de", dauer: str = "2 Stunden", variante: int = 1,
                     spieler_bis: int | None = None) -> Geruest:
    bis = max(spieler, spieler_bis or spieler)
    prompt = load_prompt("geruest", thema=thema, besetzung=besetzung_text(spieler, bis), dauer=dauer,
                         sprache_name=sprache_name(lang), variante=variante, designs=themes.prompt_list())
    return client.generate_json(prompt, Geruest, model, label="Gerüst")


def generate_ausarbeitung(client: LLMClient, model: str, geruest: Geruest, spieler: int,
                          lang: str = "de", dauer: str = "2 Stunden",
                          spieler_bis: int | None = None) -> Ausarbeitung:
    bis = max(spieler, spieler_bis or spieler)
    prompt = load_prompt(
        "ausarbeitung",
        geruest_json=geruest.model_dump_json(indent=1),
        spieler=spieler_text(spieler, bis), dauer=dauer, sprache_name=sprache_name(lang),
        besetzung_regeln=besetzung_regeln(spieler, bis),
        hinweise_anzahl=max(3 * bis + 3, 18))
    return client.generate_json(prompt, Ausarbeitung, model, label="Ausarbeitung")


def merge(geruest: Geruest, aus: Ausarbeitung, thema: str, spieler: int, lang: str,
          spieler_bis: int | None = None) -> Story:
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
        spieler=max(spieler, spieler_bis or spieler),
        spieler_min=spieler if (spieler_bis or spieler) > spieler else 0,
        design=themes.normalize(geruest.design),
        seed=int(hashlib.sha256(thema.encode()).hexdigest()[:6], 16) % 100000,
        einleitung=aus.einleitung, setting=geruest.setting, opfer=geruest.opfer,
        charaktere=charaktere, fakten=geruest.fakten, zeitleiste=geruest.zeitleiste,
        hinweise=aus.hinweise, runden=aus.runden, aufloesung=aus.aufloesung,
        gastgeber=aus.gastgeber,
    )


def generate_story(client: LLMClient, model: str, thema: str, spieler: int,
                   lang: str = "de", progress=lambda msg: None, variante: int = 1,
                   spieler_bis: int | None = None) -> Story:
    progress("Schritt 1/2: Gerüst (Täter, Motiv, Zeitleiste, Alibis) …")
    geruest = generate_geruest(client, model, thema, spieler, lang, variante=variante, spieler_bis=spieler_bis)
    progress(f"Gerüst fertig: „{geruest.titel}“ – Schritt 2/2: Charaktere, Hinweise, Runden …")
    aus = generate_ausarbeitung(client, model, geruest, spieler, lang, spieler_bis=spieler_bis)
    return merge(geruest, aus, thema, spieler, lang, spieler_bis)


def repair_story(client: LLMClient, model: str, story: Story, fehler: list[str],
                 versuch: int) -> Story:
    """Schickt die Fehlerliste an die KI und bekommt ein korrigiertes Kit zurück."""
    taeter = story.taeter()
    prompt = load_prompt(
        "korrektur",
        fehler="\n".join(f"- {f}" for f in fehler),
        story_json=story.model_dump_json(indent=1),
        taeter_id=taeter[0].id if taeter else "?", versuch=versuch,
        besetzung_regeln=besetzung_regeln(story.min_spieler, story.spieler),
        sprache_name=sprache_name(story.sprache))
    fixed = client.generate_json(prompt, Story, model, label=f"Korrektur {versuch}", temperature=0.4)
    # Metadaten, die die KI nicht ändern soll, beibehalten
    fixed.thema, fixed.spieler, fixed.sprache, fixed.seed = story.thema, story.spieler, story.sprache, story.seed
    fixed.spieler_min = story.spieler_min
    return fixed


def save_story(story: Story, path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(story.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")


def load_story(path) -> Story:
    return Story.model_validate_json(path.read_text(encoding="utf-8"))
