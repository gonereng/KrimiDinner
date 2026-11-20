"""Kommandozeile: krimi new | validate | render | all | demo | serve"""
from __future__ import annotations

import logging
from pathlib import Path

import typer

app = typer.Typer(help="Krimidinner-Generator: druckfertige Murder-Mystery-Kits mit KI (DeepSeek oder Gemini).",
                  no_args_is_help=True, add_completion=False)


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("fontTools").setLevel(logging.ERROR)
    logging.getLogger("weasyprint").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _progress(msg: str) -> None:
    typer.echo(f"  → {msg}")


def _usage(u: dict) -> None:
    typer.echo(f"KI: {u['api_calls']} API-Aufrufe, {u['cache_hits']} aus dem Cache, "
               f"{u['total_tokens']} Tokens ({u['prompt_tokens']} Eingabe / {u['output_tokens']} Ausgabe)")


def _check_design(design: str) -> str:
    from .themes import THEMES
    if design != "auto" and design not in THEMES:
        typer.secho(f"✘ Unbekanntes Design '{design}'. Verfügbar: auto, {', '.join(THEMES)}", fg="red")
        raise typer.Exit(2)
    return design


def _run(render: bool, theme, players, lang, paper, images, cache, variante, verbose, design="auto"):
    from .pipeline import parse_spieler
    try:
        players, players_bis = parse_spieler(players)
    except ValueError as exc:
        typer.secho(f"✘ {exc}", fg="red")
        raise typer.Exit(2)
    from .llm_client import LLMError
    from .pipeline import KitFailed, generate_kit, kit_name
    _setup_logging(verbose)
    try:
        res = generate_kit(theme, players, lang, paper, images=images, use_cache=cache, spieler_bis=players_bis,
                           variante=variante, progress=_progress, render=render,
                           design=_check_design(design))
    except (KitFailed, LLMError) as exc:
        from .config import get_settings
        typer.secho(f"✘ {exc}", fg="red")
        kit = get_settings().output_dir / kit_name(theme, players, lang, variante, players_bis)
        typer.echo(f"  Fortschritt gesichert – später fortsetzen mit: krimi resume {kit}")
        raise typer.Exit(1)
    for w in res["warnings"]:
        typer.secho(f"⚠ {w}", fg="yellow")
    typer.secho(f"✔ Fertig: {res['kit_dir']}", fg="green")
    _usage(res["usage"])


DESIGN_HELP = "PDF-Design (siehe `krimi designs`), Standard: auto = KI wählt passend zum Thema"


@app.command()
def new(theme: str = typer.Option(..., "--theme", "-t", help="Thema des Krimidinners"),
        players: str = typer.Option("6", "--players", "-p",
                                    help="Spielerzahl, fest (6) oder variabel (6-10, max. 4 optionale Figuren)"),
        design: str = typer.Option("auto", "--design", "-d", help=DESIGN_HELP),
        lang: str = typer.Option("de", "--lang", help="de oder en"),
        variante: int = typer.Option(1, "--variante", help="Andere Geschichte zum selben Thema"),
        cache: bool = typer.Option(True, "--cache/--no-cache", help="KI-Cache nutzen"),
        verbose: bool = typer.Option(False, "--verbose", "-v")):
    """Story erzeugen und prüfen -> output/<kit>/story.json"""
    _run(False, theme, players, lang, "a4", False, cache, variante, verbose, design)


@app.command()
def all(theme: str = typer.Option(..., "--theme", "-t"),
        players: str = typer.Option("6", "--players", "-p",
                                    help="Spielerzahl, fest (6) oder variabel (6-10, max. 4 optionale Figuren)"),
        lang: str = typer.Option("de", "--lang"),
        paper: str = typer.Option("a4", "--paper", help="a4 oder letter"),
        design: str = typer.Option("auto", "--design", "-d", help=DESIGN_HELP),
        images: bool = typer.Option(True, "--images/--no-images", help="Illustrationen erzeugen"),
        variante: int = typer.Option(1, "--variante"),
        cache: bool = typer.Option(True, "--cache/--no-cache"),
        verbose: bool = typer.Option(False, "--verbose", "-v")):
    """Alles in einem Lauf: Story, Prüfung, Bilder, PDFs, ZIP."""
    _run(True, theme, players, lang, paper, images, cache, variante, verbose, design)


@app.command()
def resume(kit_dir: Path = typer.Argument(..., exists=True, file_okay=False),
           cache: bool = typer.Option(True, "--cache/--no-cache"),
           verbose: bool = typer.Option(False, "--verbose", "-v")):
    """Abgebrochenen Lauf (z. B. Kontingent erschöpft) ab dem letzten gesicherten Schritt fortsetzen."""
    from .llm_client import LLMError
    from .pipeline import KitFailed, resume_kit
    _setup_logging(verbose)
    try:
        res = resume_kit(kit_dir, progress=_progress, use_cache=cache)
    except (KitFailed, LLMError) as exc:
        typer.secho(f"✘ {exc}", fg="red")
        raise typer.Exit(1)
    for w in res["warnings"]:
        typer.secho(f"⚠ {w}", fg="yellow")
    typer.secho(f"✔ Fertig: {res['kit_dir']}", fg="green")
    _usage(res["usage"])


@app.command()
def validate(story_json: Path = typer.Argument(..., exists=True, dir_okay=False),
             gegencheck: bool = typer.Option(True, "--gegencheck/--ohne-gegencheck",
                                             help="Täter zusätzlich per KI ermitteln lassen"),
             cache: bool = typer.Option(True, "--cache/--no-cache")):
    """Logikprüfung einer (ggf. von Hand bearbeiteten) story.json."""
    from .llm_client import LLMError
    from .pipeline import validate_kit
    _setup_logging(False)
    try:
        r = validate_kit(story_json, gegencheck=gegencheck, use_cache=cache)
    except LLMError as exc:
        typer.secho(f"✘ {exc}\n  (Tipp: --ohne-gegencheck prüft nur die feste Logik)", fg="red")
        raise typer.Exit(1)
    for w in r.warnungen:
        typer.secho(f"⚠ {w}", fg="yellow")
    if r.ermittlung:
        typer.echo(f"Gegencheck: {r.ermittlung.taeter_id} (Sicherheit {r.ermittlung.sicherheit:.2f})")
    if r.ok:
        typer.secho("✔ Logikprüfung bestanden", fg="green")
    else:
        for f in r.fehler:
            typer.secho(f"✘ {f}", fg="red")
        raise typer.Exit(1)


@app.command()
def render(kit_dir: Path = typer.Argument(..., exists=True, file_okay=False),
           paper: str = typer.Option("a4", "--paper", help="a4 oder letter"),
           design: str = typer.Option("", "--design", "-d",
                                      help="Design wechseln (wird in story.json gespeichert); leer = beibehalten")):
    """PDFs aus output/<kit>/story.json neu setzen (ohne KI-Kosten)."""
    from .pipeline import render_existing
    _setup_logging(False)
    if design:
        _check_design(design)
    files, warnings = render_existing(kit_dir, paper, design or None)
    for w in warnings:
        typer.secho(f"⚠ {w}", fg="yellow")
    typer.secho(f"✔ {len(files)} Dateien in {kit_dir}", fg="green")


@app.command()
def demo(paper: str = typer.Option("a4", "--paper")):
    """Beispiel-Kit „Silvester im Schneechalet“ ohne API-Key erzeugen."""
    from .pipeline import create_demo
    _setup_logging(False)
    kit_dir, files, warnings = create_demo(paper=paper)
    for w in warnings:
        typer.secho(f"⚠ {w}", fg="yellow")
    typer.secho(f"✔ Demo-Kit: {kit_dir} ({len(files)} Dateien)", fg="green")


@app.command()
def designs():
    """Verfügbare PDF-Designs auflisten."""
    from .themes import THEMES
    for t in THEMES.values():
        typer.echo(f"  {t.name:<14} {t.label:<15} {t.beschreibung}")


@app.command()
def serve(host: str = typer.Option("0.0.0.0", "--host"), port: int = typer.Option(8000, "--port")):
    """Web-Oberfläche starten."""
    import uvicorn
    _setup_logging(True)
    uvicorn.run("krimi.web.app:app", host=host, port=port)


if __name__ == "__main__":
    app()
