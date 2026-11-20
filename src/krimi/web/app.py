"""Web-Oberfläche (FastAPI). Start: `krimi serve` oder `uvicorn krimi.web.app:app`.

Schutz: ein gemeinsames Passwort aus APP_PASSWORD (.env), Sitzung per signiertem Cookie.
Lange Aufgaben (Generierung, Rendern, Prüfen) laufen in Hintergrund-Threads; der Fortschritt
steht in output/<kit>/status.json und wird von der Seite abgefragt.
"""
from __future__ import annotations

import hmac
import json
import logging
import re
import secrets
import shutil
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from starlette.middleware.sessions import SessionMiddleware

from ..config import TEMPLATES_DIR, get_settings
from ..themes import THEMES, font_face_css
from ..models import Story

log = logging.getLogger("krimi.web")
HERE = Path(__file__).parent
settings = get_settings()

app = FastAPI(title="Krimidinner-Generator", docs_url=None, redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret or secrets.token_hex(32),
                   same_site="lax", max_age=60 * 60 * 24 * 14, https_only=False)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
app.mount("/fonts", StaticFiles(directory=TEMPLATES_DIR / "fonts"), name="fonts")
templates = Jinja2Templates(directory=HERE / "templates")
templates.env.globals["themes"] = list(THEMES.values())

executor = ThreadPoolExecutor(max_workers=2)
_lock = threading.Lock()
_running: set[str] = set()
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")
FILE_LABELS = {
    "01_gastgeber.pdf": "Gastgeber-Anleitung", "02_einladungen.pdf": "Einladungen",
    "03_charakterhefte.pdf": "Charakterhefte (alle)", "04_hinweiskarten.pdf": "Hinweiskarten",
    "05_beweisstuecke.pdf": "Beweisstücke", "06_aufloesung.pdf": "Auflösung (versiegelt)",
    "07_namensschilder.pdf": "Namensschilder", "08_notizblaetter.pdf": "Detektiv-Notizblätter",
    "kit.zip": "Alles als ZIP", "story.json": "story.json",
}


# --------------------------------------------------------------------------
# Hilfen
# --------------------------------------------------------------------------

def out_dir() -> Path:
    d = get_settings().output_dir
    d.mkdir(parents=True, exist_ok=True)
    return d


def kit_path(name: str) -> Path:
    if not NAME_RE.match(name):
        raise HTTPException(404)
    p = out_dir() / name
    if not p.is_dir():
        raise HTTPException(404, "Kit nicht gefunden")
    return p


def read_json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def logged_in(request: Request) -> bool:
    return request.session.get("auth") is True


def need_login(request: Request):
    if not logged_in(request):
        raise HTTPException(status_code=303, headers={"Location": "/login"})


def now() -> str:
    return datetime.now().strftime("%H:%M:%S")


class Job:
    """Schreibt den Fortschritt einer Hintergrundaufgabe nach <kit>/status.json."""

    def __init__(self, kit_dir: Path, aufgabe: str):
        self.path = kit_dir / "status.json"
        self.state = {"aufgabe": aufgabe, "status": "laeuft", "log": [], "gestartet": time.time(),
                      "beendet": None, "fehler": None, "warnungen": []}
        self.save()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def progress(self, msg: str):
        self.state["log"].append(f"{now()}  {msg}")
        self.save()

    def finish(self, ok: bool, fehler: str | None = None, warnungen=None):
        self.state.update(status="fertig" if ok else "fehler", beendet=time.time(), fehler=fehler,
                          warnungen=warnungen or [])
        self.state["log"].append(f"{now()}  " + ("✔ Fertig" if ok else "✘ Abgebrochen"))
        self.save()


def start_job(name: str, kit_dir: Path, aufgabe: str, fn):
    with _lock:
        if name in _running:
            raise HTTPException(409, "Für dieses Kit läuft bereits eine Aufgabe.")
        _running.add(name)
    job = Job(kit_dir, aufgabe)

    def run():
        try:
            warnungen = fn(job) or []
            job.finish(True, warnungen=warnungen)
        except Exception as exc:  # Fehler sichtbar machen, nicht verschlucken
            log.error("Aufgabe %s für %s fehlgeschlagen:\n%s", aufgabe, name, traceback.format_exc())
            job.finish(False, fehler=str(exc))
        finally:
            with _lock:
                _running.discard(name)

    executor.submit(run)


def kit_summary(d: Path) -> dict:
    story = read_json(d / "story.json", {}) or {}
    status = read_json(d / "status.json", {}) or {}
    report = read_json(d / "report.json")
    if status.get("status") == "laeuft" and d.name not in _running:
        status["status"] = "abgebrochen"  # z. B. Server-Neustart während der Generierung
    return {
        "name": d.name, "titel": story.get("titel") or d.name, "thema": story.get("thema", ""),
        "spieler": story.get("spieler"), "sprache": story.get("sprache"),
        "status": status.get("status", "fertig" if (d / "kit.zip").exists() else "entwurf"),
        "aufgabe": status.get("aufgabe", ""), "report_ok": report.get("ok") if report else None,
        "has_pdf": (d / "kit.zip").exists(), "mtime": d.stat().st_mtime,
    }


# --------------------------------------------------------------------------
# Anmeldung
# --------------------------------------------------------------------------

@app.exception_handler(HTTPException)
async def http_exc(request: Request, exc: HTTPException):
    if exc.status_code == 303:
        return RedirectResponse(exc.headers["Location"], status_code=303)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    return templates.TemplateResponse(request, "error.html",
                                      {"code": exc.status_code, "detail": exc.detail}, status_code=exc.status_code)


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html",
                                      {"configured": bool(get_settings().app_password), "error": None})


@app.post("/login")
def login(request: Request, password: str = Form("")):
    expected = get_settings().app_password
    if expected and hmac.compare_digest(password.encode(), expected.encode()):
        request.session["auth"] = True
        return RedirectResponse("/", status_code=303)
    time.sleep(1)  # bremst Durchprobieren
    return templates.TemplateResponse(request, "login.html",
                                      {"configured": bool(expected), "error": "Falsches Passwort."},
                                      status_code=401)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/themes.css")
def themes_css():
    """Schriften + Vorschau-Farben der PDF-Designs für die Auswahlkarten in der Web-App."""
    from fastapi.responses import Response
    rules = [font_face_css("/fonts")]
    for t in THEMES.values():
        c = t.colors
        rules.append(
            f".dp-{t.name} .dp-cover {{ background: {c['cover_bg']}; color: {c['cover_ink']}; }}\n"
            f".dp-{t.name} .dp-cover .dp-frame {{ border-color: {c['gold']}; }}\n"
            f".dp-{t.name} .dp-title {{ font-family: {t.head}; text-transform: {t.head_transform}; "
            f"letter-spacing: {t.head_spacing}; }}\n"
            f".dp-{t.name} .dp-sym {{ color: {c['gold']}; }}\n"
            f".dp-{t.name} .dp-paper {{ background: {c['paper']}; border-top: 3px solid {c['accent']}; }}\n"
            f".dp-{t.name} .dp-paper b {{ font-family: {t.head}; color: {c['primary']}; }}\n"
            f".dp-{t.name} .dp-paper span {{ font-family: {t.body}; color: {c['ink']}; }}")
    return Response("\n".join(rules), media_type="text/css",
                    headers={"Cache-Control": "public, max-age=3600"})


@app.get("/healthz")
def healthz():
    return {"ok": True}


# --------------------------------------------------------------------------
# Übersicht & neue Kits
# --------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    need_login(request)
    kits = sorted((kit_summary(d) for d in out_dir().iterdir()
                   if d.is_dir() and NAME_RE.match(d.name)), key=lambda k: -k["mtime"])
    s = get_settings()
    return templates.TemplateResponse(request, "index.html", {
        "kits": kits, "has_key": bool(s.api_key), "text_model": s.text_model,
        "check_model": s.check_model, "provider": s.provider_name, "key_var": s.key_var,
        "image_model": s.image_model if (s.image_api_key or s.provider == "gemini") else ""})


@app.post("/kits/new")
def new_kit(request: Request, thema: str = Form(...), spieler: int = Form(6), lang: str = Form("de"),
            paper: str = Form("a4"), bilder: bool = Form(False), ohne_cache: bool = Form(False),
            variante: int = Form(1), design: str = Form("auto")):
    need_login(request)
    from ..pipeline import generate_kit, kit_name
    if design != "auto" and design not in THEMES:
        raise HTTPException(400, "Unbekanntes Design.")
    thema = thema.strip()[:200]
    if not thema:
        raise HTTPException(400, "Bitte ein Thema angeben.")
    if not 3 <= spieler <= 12 or lang not in ("de", "en") or paper not in ("a4", "letter"):
        raise HTTPException(400, "Ungültige Eingabe.")
    variante = max(1, min(variante, 99))
    name = kit_name(thema, spieler, lang, variante)
    kit_dir = out_dir() / name

    def task(job: Job):
        res = generate_kit(thema, spieler, lang, paper, images=bilder, use_cache=not ohne_cache,
                           variante=variante, progress=job.progress, kit_dir=kit_dir, design=design)
        u = res["usage"]
        job.progress(f"KI: {u['api_calls']} API-Aufrufe, {u['cache_hits']} aus dem Cache, "
                     f"{u['total_tokens']} Tokens")
        return res["warnings"]

    start_job(name, kit_dir, "Generierung", task)
    return RedirectResponse(f"/kits/{name}", status_code=303)


@app.post("/kits/{name}/retry")
def kit_retry(request: Request, name: str):
    """Abgebrochene Generierung ab dem letzten gesicherten Schritt fortsetzen."""
    need_login(request)
    d = kit_path(name)
    from ..pipeline import resume_kit
    if not (d / "params.json").exists():
        raise HTTPException(400, "Für dieses Kit gibt es keinen fortsetzbaren Lauf.")

    def task(job: Job):
        res = resume_kit(d, progress=job.progress)
        u = res["usage"]
        job.progress(f"KI: {u['api_calls']} API-Aufrufe, {u['cache_hits']} aus dem Cache, "
                     f"{u['total_tokens']} Tokens")
        return res["warnings"]

    start_job(name, d, "Generierung (fortgesetzt)", task)
    return RedirectResponse(f"/kits/{name}", status_code=303)


@app.post("/demo")
def demo(request: Request, paper: str = Form("a4")):
    need_login(request)
    from ..pipeline import create_demo
    name = "demo-silvester-im-schneechalet"
    kit_dir = out_dir() / name

    def task(job: Job):
        job.progress("Demo-Story wird kopiert und geprüft …")
        job.progress("PDFs werden gesetzt …")
        _, _, warn = create_demo(kit_dir, paper if paper in ("a4", "letter") else "a4")
        return warn

    start_job(name, kit_dir, "Demo", task)
    return RedirectResponse(f"/kits/{name}", status_code=303)


# --------------------------------------------------------------------------
# Kit-Detail
# --------------------------------------------------------------------------

@app.get("/kits/{name}", response_class=HTMLResponse)
def kit_detail(request: Request, name: str):
    need_login(request)
    d = kit_path(name)
    files = [(f, FILE_LABELS[f]) for f in FILE_LABELS if (d / f).exists()]
    hefte = sorted((d / "charakterhefte").glob("*.pdf")) if (d / "charakterhefte").is_dir() else []
    story = read_json(d / "story.json")
    from ..pipeline import Zwischenstand
    summary = kit_summary(d)
    can_retry = ((d / "params.json").exists() and name not in _running
                 and summary["status"] in ("fehler", "abgebrochen"))
    return templates.TemplateResponse(request, "kit.html", {
        "can_retry": can_retry, "gesichert": Zwischenstand(d).summary(),
        "kit": summary, "status": read_json(d / "status.json", {}) or {},
        "report": read_json(d / "report.json"), "usage": read_json(d / "usage.json"),
        "files": files, "hefte": [h.name for h in hefte], "story": story,
        "running": name in _running, "has_key": bool(get_settings().api_key),
        "provider": get_settings().provider_name})


@app.get("/api/kits/{name}")
def kit_status(request: Request, name: str):
    if not logged_in(request):
        raise HTTPException(401, "Nicht angemeldet")
    d = kit_path(name)
    st = read_json(d / "status.json", {}) or {}
    st["running"] = name in _running
    return st


@app.get("/kits/{name}/files/{file_path:path}")
def kit_file(request: Request, name: str, file_path: str, download: bool = False):
    need_login(request)
    d = kit_path(name).resolve()
    f = (d / file_path).resolve()
    if d not in f.parents or not f.is_file() or f.suffix.lower() not in (".pdf", ".zip", ".json", ".png", ".jpg"):
        raise HTTPException(404)
    disp = "attachment" if download or f.suffix in (".zip", ".json") else "inline"
    return FileResponse(f, filename=f"{name}-{f.name}" if f.suffix == ".zip" else f.name,
                        content_disposition_type=disp)


@app.post("/kits/{name}/render")
def kit_render(request: Request, name: str, paper: str = Form("a4"), design: str = Form("")):
    need_login(request)
    d = kit_path(name)
    from ..pipeline import render_existing
    if design and design not in THEMES:
        raise HTTPException(400, "Unbekanntes Design.")

    def task(job: Job):
        label = f", Design „{THEMES[design].label}“" if design else ""
        job.progress(f"PDFs werden neu gesetzt ({paper.upper()}{label}) …")
        files, warn = render_existing(d, paper if paper in ("a4", "letter") else "a4", design or None)
        job.progress(f"{len(files)} Dateien erzeugt")
        return warn

    start_job(name, d, "Rendern", task)
    return RedirectResponse(f"/kits/{name}", status_code=303)


@app.post("/kits/{name}/validate")
def kit_validate(request: Request, name: str, gegencheck: bool = Form(False)):
    need_login(request)
    d = kit_path(name)
    from ..pipeline import validate_kit

    def task(job: Job):
        job.progress("Logikprüfung" + (" mit KI-Gegencheck" if gegencheck else "") + " …")
        r = validate_kit(d / "story.json", gegencheck=gegencheck)
        if r.ermittlung:
            job.progress(f"Gegencheck: {r.ermittlung.taeter_id} (Sicherheit {r.ermittlung.sicherheit:.2f})")
        job.progress("Bestanden ✔" if r.ok else f"{len(r.fehler)} Fehler gefunden")
        if not r.ok:
            raise RuntimeError("Logikprüfung nicht bestanden – Details siehe Prüfbericht.")
        return r.warnungen

    start_job(name, d, "Prüfung", task)
    return RedirectResponse(f"/kits/{name}", status_code=303)


@app.post("/kits/{name}/delete")
def kit_delete(request: Request, name: str):
    need_login(request)
    d = kit_path(name)
    if name in _running:
        raise HTTPException(409, "Aufgabe läuft noch.")
    shutil.rmtree(d)
    return RedirectResponse("/", status_code=303)


# --------------------------------------------------------------------------
# story.json bearbeiten
# --------------------------------------------------------------------------

@app.get("/kits/{name}/edit", response_class=HTMLResponse)
def kit_edit(request: Request, name: str):
    need_login(request)
    d = kit_path(name)
    text = (d / "story.json").read_text(encoding="utf-8") if (d / "story.json").exists() else ""
    return templates.TemplateResponse(request, "edit.html", {"kit": kit_summary(d), "text": text, "errors": None})


@app.post("/kits/{name}/edit", response_class=HTMLResponse)
def kit_save(request: Request, name: str, text: str = Form(...), danach: str = Form("speichern")):
    need_login(request)
    d = kit_path(name)
    errors = None
    try:
        story = Story.model_validate_json(text)
    except ValidationError as exc:
        errors = [f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors()][:30]
    except ValueError as exc:
        errors = [f"Kein gültiges JSON: {exc}"]
    if errors:
        return templates.TemplateResponse(request, "edit.html", {"kit": kit_summary(d), "text": text,
                                                                 "errors": errors}, status_code=422)
    if (d / "story.json").exists():
        shutil.copy(d / "story.json", d / "story.backup.json")
    (d / "story.json").write_text(json.dumps(story.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    if danach == "rendern":
        return kit_render(request, name, paper="a4", design="")
    if danach == "pruefen":
        return kit_validate(request, name, gegencheck=False)
    return RedirectResponse(f"/kits/{name}", status_code=303)
