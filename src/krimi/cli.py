"""Kommandozeile: krimi new | validate | render | all | demo | serve"""
from __future__ import annotations

import logging
from pathlib import Path

import typer

app = typer.Typer(help="Krimidinner-Generator: druckfertige Murder-Mystery-Kits mit Gemini.",
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
    typer.echo(f"Gemini: {u['api_calls']} API-Aufrufe, {u['cache_hits']} aus dem Cache, "
               f"{u['total_tokens']} Tokens ({u['prompt_tokens']} Eingabe / {u['output_tokens']} Ausgabe)")


def _run(render: bool, theme, players, lang, paper, images, cache, variante, verbose):
    from .gemini_client import GeminiError
    from .pipeline import KitFailed, generate_kit
    _setup_logging(verbose)
    try:
        res = generate_kit(theme, players, lang, paper, images=images, use_cache=cache,
                           variante=variante, progress=_progress, render=render)
    except (KitFailed, GeminiError) as exc:
        typer.secho(f"✘ {exc}", fg="red")
        raise typer.Exit(1)
    for w in res["warnings"]:
        typer.secho(f"⚠ {w}", fg="yellow")
    typer.secho(f"✔ Fertig: {res['kit_dir']}", fg="green")
    _usage(res["usage"])


@app.command()
def new(theme: str = typer.Option(..., "--theme", "-t", help="Thema des Krimidinners"),
        players: int = typer.Option(6, "--players", "-p", min=3, max=12),
        lang: str = typer.Option("de", "--lang", help="de oder en"),
        variante: int = typer.Option(1, "--variante", help="Andere Geschichte zum selben Thema"),
        cache: bool = typer.Option(True, "--cache/--no-cache", help="Gemini-Cache nutzen"),
        verbose: bool = typer.Option(False, "--verbose", "-v")):
    """Story erzeugen und prüfen -> output/<kit>/story.json"""
    _run(False, theme, players, lang, "a4", False, cache, variante, verbose)


@app.command()
def all(theme: str = typer.Option(..., "--theme", "-t"),
        players: int = typer.Option(6, "--players", "-p", min=3, max=12),
        lang: str = typer.Option("de", "--lang"),
        paper: str = typer.Option("a4", "--paper", help="a4 oder letter"),
        images: bool = typer.Option(True, "--images/--no-images", help="Illustrationen erzeugen"),
        variante: int = typer.Option(1, "--variante"),
        cache: bool = typer.Option(True, "--cache/--no-cache"),
        verbose: bool = typer.Option(False, "--verbose", "-v")):
    """Alles in einem Lauf: Story, Prüfung, Bilder, PDFs, ZIP."""
    _run(True, theme, players, lang, paper, images, cache, variante, verbose)


@app.command()
def validate(story_json: Path = typer.Argument(..., exists=True, dir_okay=False),
             gegencheck: bool = typer.Option(True, "--gegencheck/--ohne-gegencheck",
                                             help="Täter zusätzlich per Gemini ermitteln lassen"),
             cache: bool = typer.Option(True, "--cache/--no-cache")):
    """Logikprüfung einer (ggf. von Hand bearbeiteten) story.json."""
    from .gemini_client import GeminiError
    from .pipeline import validate_kit
    _setup_logging(False)
    try:
        r = validate_kit(story_json, gegencheck=gegencheck, use_cache=cache)
    except GeminiError as exc:
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
           paper: str = typer.Option("a4", "--paper", help="a4 oder letter")):
    """PDFs aus output/<kit>/story.json neu setzen (ohne KI-Kosten)."""
    from .pipeline import render_existing
    _setup_logging(False)
    files, warnings = render_existing(kit_dir, paper)
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
def serve(host: str = typer.Option("0.0.0.0", "--host"), port: int = typer.Option(8000, "--port")):
    """Web-Oberfläche starten."""
    import uvicorn
    _setup_logging(True)
    uvicorn.run("krimi.web.app:app", host=host, port=port)


if __name__ == "__main__":
    app()
