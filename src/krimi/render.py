"""HTML -> PDF mit Jinja2 + WeasyPrint.

Erzeugt im Kit-Ordner:
  01_gastgeber.pdf, 02_einladungen.pdf, 03_charakterhefte.pdf (+ charakterhefte/<name>.pdf),
  04_hinweiskarten.pdf, 05_beweisstuecke.pdf, 06_aufloesung.pdf, 07_namensschilder.pdf,
  08_notizblaetter.pdf und kit.zip
"""
from __future__ import annotations

import logging
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import puzzles, themes
from .config import TEMPLATES_DIR
from .models import Hinweis, Story

log = logging.getLogger("krimi.render")

PAPER = {"a4": (210.0, 297.0), "letter": (215.9, 279.4)}
CARD_W, CARD_H, CARD_GAP = 90.0, 80.0, 6.0
BLEED = 2.0  # Rückseiten-Farbe ragt so weit über die Schnittkante (Toleranz beim Duplexdruck)

LABELS = {
    "de": {
        "gastgeber": "Gastgeber-Anleitung", "einladung": "Einladung", "rolle": "Deine Rolle",
        "kostuem": "Kostümtipp", "charakterheft": "Charakterheft", "profil": "Was alle über dich wissen",
        "geheimnis": "Dein Geheimnis", "motiv": "Dein Motiv", "alibi": "Dein Alibi",
        "beziehungen": "Deine Beziehungen", "darf_sagen": "Das darfst du erzählen",
        "darf_nicht": "Das musst du verbergen", "taeter_box": "Du bist die Täterin / der Täter!",
        "taeter_text": "Nur du weißt es. Du darfst lügen, ablenken und andere verdächtigen – aber gib dich niemals zu erkennen.",
        "unschuldig_text": "Du bist unschuldig – aber du hast etwas zu verbergen. Du darfst über dein Geheimnis schweigen oder flunkern, aber nicht über den Mord lügen.",
        "runde": "Runde", "fuer": "Für", "hinweiskarten": "Hinweiskarten", "beweisstueck": "Beweisstück",
        "aufloesung": "Die Auflösung", "erst_am_ende": "Erst am Ende öffnen!",
        "versiegelt": "Streng vertraulich – nur für die Spielleitung",
        "notizblatt": "Detektiv-Notizblatt", "verdaechtige": "Verdächtige",
        "spalte_motiv": "Motiv", "spalte_alibi": "Alibi", "spalte_gelegenheit": "Gelegenheit",
        "spalte_verdacht": "Verdacht", "zeitnotizen": "Wer war wann wo?", "mein_tipp": "Mein Tipp",
        "taeter_ist": "Der Täter / die Täterin ist", "weil": "weil",
        "vorbereitung": "Vorbereitung", "ablauf": "Ablauf", "vorlesen": "Zum Vorlesen",
        "verteilen": "Zu verteilen", "tipps": "Tipps für die Spielleitung", "menue": "Menüvorschlag",
        "einkauf": "Einkaufsliste", "deko": "Deko-Ideen", "figuren": "Die Figuren",
        "raetselloesungen": "Rätsel-Lösungen", "schritte": "So kommt man auf die Lösung",
        "tathergang": "Was wirklich geschah", "zeitleiste": "Die Zeitleiste der Tatnacht",
        "code": "Code", "botschaft": "Botschaft", "inhalt": "Inhalt (erst nach Lösung herausgeben)",
        "verschiebung": "Verschiebung", "bonus": "Bonusrätsel: Wer saß wo beim Dinner?",
        "platz": "Platz", "sitzordnung": "Sitzordnung", "spieler": "Spieler", "dauer": "ca. 2 Stunden",
        "caesar_hilfe": "Jeder Buchstabe wurde um dieselbe Anzahl Stellen im Alphabet verschoben.",
        "subst_hilfe": "Jeder Buchstabe steht für einen anderen. Bekannt:",
        "lock_hilfe": "Das Schloss hat {n} Stellen.",
        "ws_hilfe": "Streiche alle Wörter (waagerecht, senkrecht, diagonal, auch rückwärts). Die ersten {n} übrigen Buchstaben ergeben – zeilenweise gelesen – eine Botschaft.",
        "gesucht": "Gesucht", "ziffer": ["Erste", "Zweite", "Dritte", "Vierte"], "stelle": "Ziffer",
        "ort": "Ort", "zeit": "Zeit", "wer": "Wer", "was": "Was",
        "uebersicht_hinweise": "Hinweise je Runde", "opfer": "Das Opfer", "tatort": "Fundort",
        "abend": "Ein Krimidinner für", "sitzhinweis": "Die Plätze sind in einer Reihe von links (1) nach rechts nummeriert.",
        "beweis_hinweis": "Beweisstück – an die genannte Person aushändigen", "schneiden": "Entlang der Marken ausschneiden",
        "inhalt_titel": "Für die Spielleitung", "erst_bei_code": "Erst herausgeben bei Code",
        "inhalt_von": "Inhalt", "inhalt_seite": "Inhalt liegt als Beweisstück",
        "hinweis_label": "Hinweis",
        "rueckseiten": "Rückseiten · beidseitig drucken, an der langen Kante wenden",
    },
    "en": {
        "gastgeber": "Host Guide", "einladung": "Invitation", "rolle": "Your role",
        "kostuem": "Costume tip", "charakterheft": "Character Booklet", "profil": "What everyone knows about you",
        "geheimnis": "Your secret", "motiv": "Your motive", "alibi": "Your alibi",
        "beziehungen": "Your relationships", "darf_sagen": "You may say",
        "darf_nicht": "You must hide", "taeter_box": "You are the murderer!",
        "taeter_text": "Only you know it. You may lie, deflect and accuse others – but never give yourself away.",
        "unschuldig_text": "You are innocent – but you have something to hide. You may keep quiet or fib about your secret, but do not lie about the murder.",
        "runde": "Round", "fuer": "For", "hinweiskarten": "Clue Cards", "beweisstueck": "Evidence",
        "aufloesung": "The Solution", "erst_am_ende": "Do not open until the end!",
        "versiegelt": "Strictly confidential – for the host only",
        "notizblatt": "Detective Notes", "verdaechtige": "Suspects",
        "spalte_motiv": "Motive", "spalte_alibi": "Alibi", "spalte_gelegenheit": "Opportunity",
        "spalte_verdacht": "Suspicion", "zeitnotizen": "Who was where, when?", "mein_tipp": "My guess",
        "taeter_ist": "The murderer is", "weil": "because",
        "vorbereitung": "Preparation", "ablauf": "Running the game", "vorlesen": "Read aloud",
        "verteilen": "Hand out", "tipps": "Tips for the host", "menue": "Menu suggestion",
        "einkauf": "Shopping list", "deko": "Decoration ideas", "figuren": "The characters",
        "raetselloesungen": "Puzzle solutions", "schritte": "How to deduce the solution",
        "tathergang": "What really happened", "zeitleiste": "Timeline of the night",
        "code": "Code", "botschaft": "Message", "inhalt": "Content (hand out after solving)",
        "verschiebung": "Shift", "bonus": "Bonus puzzle: who sat where at dinner?",
        "platz": "Seat", "sitzordnung": "Seating", "spieler": "players", "dauer": "approx. 2 hours",
        "caesar_hilfe": "Every letter has been shifted by the same number of places in the alphabet.",
        "subst_hilfe": "Every letter stands for another one. Known:",
        "lock_hilfe": "The lock has {n} digits.",
        "ws_hilfe": "Cross out all words (horizontal, vertical, diagonal, also backwards). The first {n} remaining letters, read row by row, form a message.",
        "gesucht": "Find", "ziffer": ["First", "Second", "Third", "Fourth"], "stelle": "digit",
        "ort": "Place", "zeit": "Time", "wer": "Who", "was": "What",
        "uebersicht_hinweise": "Clues per round", "opfer": "The victim", "tatort": "Found in",
        "abend": "A murder mystery dinner for", "sitzhinweis": "Seats are in a row, numbered from left (1) to right.",
        "beweis_hinweis": "Evidence – hand to the named player", "schneiden": "Cut along the marks",
        "inhalt_titel": "For the host", "erst_bei_code": "Hand out only for code",
        "inhalt_von": "Contents", "inhalt_seite": "Contents are evidence",
        "hinweis_label": "Clue",
        "rueckseiten": "Card backs · print double-sided, flip on long edge",
    },
}


def short_name(name: str) -> str:
    m = re.search(r"[„\"“'‚](.+?)[“\"”'‘]", name)
    if m:
        return m.group(1)
    parts = name.split()
    if len(parts) > 1 and (parts[0].endswith(".") or parts[0] in {"Gräfin", "Graf", "Baron", "Baronin",
                                                                   "Lady", "Lord", "Sir", "Fürst", "Fürstin"}):
        return f"{parts[0]} {parts[1] if parts[0] in ('Gräfin','Graf','Baron','Baronin','Fürst','Fürstin') else parts[-1]}"
    return parts[0] if parts else name


def slug(text: str) -> str:
    t = puzzles.normalize(text).lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:60] or "kit"


# --------------------------------------------------------------------------
# Rätsel aus der Story ableiten
# --------------------------------------------------------------------------

@dataclass
class PuzzleView:
    typ: str
    hilfe: str
    geheimtext: str = ""
    loesung: str = ""
    code: str = ""
    lock_hinweise: list[str] | None = None
    grid: list[list[str]] | None = None
    woerter: list[str] | None = None
    detail: str = ""


def build_puzzles(story: Story) -> dict[str, PuzzleView]:
    L = LABELS.get(story.sprache, LABELS["de"])
    result = {}
    for i, h in enumerate(story.hinweise):
        rs = h.raetsel
        if not rs:
            continue
        seed = story.seed * 100 + i
        if rs.typ == "caesar":
            c = puzzles.caesar(rs.klartext, seed=seed)
            result[h.id] = PuzzleView("caesar", L["caesar_hilfe"], c.geheimtext, c.klartext,
                                      detail=f"{L['verschiebung']}: {c.verschiebung}")
        elif rs.typ == "substitution":
            c = puzzles.substitution(rs.klartext, seed=seed)
            known = c.hilfe.split(":", 1)[1].strip()
            result[h.id] = PuzzleView("substitution", f"{L['subst_hilfe']} {known}", c.geheimtext, c.klartext)
        elif rs.typ == "zahlenschloss":
            lock = puzzles.number_lock([(z.ziffer, z.herkunft) for z in rs.ziffern])
            hints = [f"{L['ziffer'][j]} {L['stelle']}: {puzzles._raetselhaft(z.herkunft)}"
                     for j, z in enumerate(rs.ziffern)]
            result[h.id] = PuzzleView("zahlenschloss", L["lock_hilfe"].format(n=len(lock.code)),
                                      code=lock.code, lock_hinweise=hints, loesung=rs.klartext)
        elif rs.typ == "wortsuche":
            ws = puzzles.word_search(rs.woerter, rs.klartext, seed=seed)
            result[h.id] = PuzzleView("wortsuche", L["ws_hilfe"].format(n=len(ws.botschaft)),
                                      grid=ws.grid, woerter=ws.woerter, loesung=rs.klartext)
    return result


def build_seating(story: Story):
    names = [short_name(c.name) for c in story.charaktere][:7]
    if len(names) < 3:
        return None
    return puzzles.seating_puzzle(names, seed=story.seed)


# --------------------------------------------------------------------------
# Kartenraster mit Schnittmarken
# --------------------------------------------------------------------------

def card_layout(paper: str) -> list[dict]:
    pw, ph = PAPER[paper]
    cols, rows = 2, 3
    gw = cols * CARD_W + (cols - 1) * CARD_GAP
    gh = rows * CARD_H + (rows - 1) * CARD_GAP
    x0, y0 = (pw - gw) / 2, (ph - gh) / 2
    slots = []
    for r in range(rows):
        for c in range(cols):
            slots.append({"x": round(x0 + c * (CARD_W + CARD_GAP), 2),
                          "y": round(y0 + r * (CARD_H + CARD_GAP), 2)})
    return slots


def crop_marks(slots: list[dict], length: float = 4.0, offset: float = 1.0) -> list[dict]:
    """Kurze Linien an allen Kartenecken, außerhalb der Karte."""
    marks = []
    for s in slots:
        for cx in (s["x"], s["x"] + CARD_W):
            for cy in (s["y"], s["y"] + CARD_H):
                sx = -1 if cx == s["x"] else 1
                sy = -1 if cy == s["y"] else 1
                # horizontale Marke
                hx = cx + offset if sx > 0 else cx - offset - length
                marks.append({"x": round(hx, 2), "y": round(cy, 2), "w": length, "h": 0})
                # vertikale Marke
                vy = cy + offset if sy > 0 else cy - offset - length
                marks.append({"x": round(cx, 2), "y": round(vy, 2), "w": 0, "h": length})
    return marks


def mirror_slot(slot: dict, paper: str) -> dict:
    """Position der Rückseite beim Duplexdruck (Wenden an der langen Kante): horizontal gespiegelt."""
    pw, _ = PAPER[paper]
    return {"x": round(pw - slot["x"] - CARD_W, 2), "y": slot["y"]}


def card_sheets(hints: list, paper: str, backs: bool = True) -> list[dict]:
    """Bögen für die Hinweiskarten; mit backs=True folgt auf jeden Vorderseiten-Bogen sein Rückseiten-Bogen."""
    slots = card_layout(paper)
    pages = []
    for runde in (1, 2, 3):
        hs = sorted([h for h in hints if h.runde == runde], key=lambda h: h.id)
        for group in chunk(hs, len(slots)):
            pages.append({"runde": runde, "side": "front", "cards": list(zip(slots, group))})
            if backs:
                pages.append({"runde": runde, "side": "back",
                              "cards": [(mirror_slot(sl, paper), h) for sl, h in zip(slots, group)]})
    return pages


def chunk(items: list, n: int) -> list[list]:
    return [items[i:i + n] for i in range(0, len(items), n)]


# --------------------------------------------------------------------------
# Überlauf-Erkennung
# --------------------------------------------------------------------------

WIDTH_WATCH = {"ev", "box", "invite", "content-slip", "tip-box", "read"}


def find_wide_boxes(document) -> list[str]:
    """Boxen (Beweisstücke, Kästen, Einladungen …), die rechts über den Satzspiegel hinausragen."""
    wide: list[str] = []

    def walk(box, limit):
        el = getattr(box, "element", None)
        if el is not None and getattr(box, "element_tag", None):
            classes = set((el.get("class") or "").split())
            if classes & WIDTH_WATCH:
                right = box.border_box_x() + box.border_width()
                if right > limit + 1:  # 1 px Toleranz
                    wide.append(f"{'.'.join(sorted(classes & WIDTH_WATCH))} "
                                f"({(right - limit) * 25.4 / 96:.1f} mm zu breit)")
                    return
        for child in getattr(box, "children", []) or []:
            walk(child, limit)

    for page in document.pages:
        pb = page._page_box
        walk(pb, pb.content_box_x() + pb.width)
    return wide


def find_overflows(document) -> list[str]:
    """Liefert data-fit-IDs aller Boxen mit class 'fit', deren Inhalt über den Rand ragt."""
    over: list[str] = []

    def bottom(box) -> float:
        b = box.position_y + box.margin_height()
        for child in getattr(box, "children", []) or []:
            b = max(b, bottom(child))
        return b

    def walk(box):
        el = getattr(box, "element", None)
        if el is not None and getattr(box, "element_tag", None) and "fit" in (el.get("class") or "").split():
            limit = box.content_box_y() + box.height
            content = max((bottom(c) for c in box.children or []), default=0)
            if content > limit + 0.5:
                over.append(el.get("data-fit") or "?")
            return
        for child in getattr(box, "children", []) or []:
            walk(child)

    for page in document.pages:
        walk(page._page_box)
    return over


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

class Renderer:
    def __init__(self, story: Story, kit_dir: Path, paper: str = "a4"):
        if paper not in PAPER:
            raise ValueError(f"Unbekanntes Papierformat '{paper}' (a4 oder letter)")
        self.story, self.kit_dir, self.paper = story, Path(kit_dir), paper
        self.theme = themes.get_theme(story.design)
        self.L = LABELS.get(story.sprache, LABELS["de"])
        self.env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)),
                               autoescape=select_autoescape(["html"]))
        self.env.filters["short"] = short_name
        self.env.globals["name_of"] = self.name_of
        self.puzzles = build_puzzles(story)
        self.seating = build_seating(story)
        self.images = self._find_images()
        self.warnings: list[str] = []

    def name_of(self, cid: str) -> str:
        c = self.story.charakter(cid)
        return c.name if c else cid

    def _find_images(self) -> dict[str, str]:
        img_dir = self.kit_dir / "images"
        found = {}
        if img_dir.is_dir():
            for f in img_dir.iterdir():
                if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                    found[f.stem] = f.resolve().as_uri()
        return found

    def _css(self) -> str:
        pw, ph = PAPER[self.paper]
        fonts = (TEMPLATES_DIR / "fonts").resolve().as_uri()
        base = (TEMPLATES_DIR / "base.css").read_text(encoding="utf-8")
        return (themes.font_face_css(fonts) + "\n" + base
                + "\n" + self.theme.css()
                + f"\n:root {{ --page-w: {pw}mm; --page-h: {ph}mm; }}"
                + f"\n@page {{ size: {pw}mm {ph}mm; }}"
                + f"\n@page sheet {{ size: {pw}mm {ph}mm; margin: 0; }}")

    def _ctx(self, **extra) -> dict:
        s = self.story
        return {"s": s, "L": self.L, "paper": self.paper, "pw": PAPER[self.paper][0],
                "ph": PAPER[self.paper][1], "puzzles": self.puzzles, "seating": self.seating,
                "images": self.images, "css": self._css(), "theme": self.theme, "card_w": CARD_W, "card_h": CARD_H, "bleed": BLEED,
                "taeter": s.taeter()[0] if s.taeter() else None, **extra}

    def _pdf(self, template: str, out: Path, fit_retries: int = 4, **extra) -> Path:
        from weasyprint import HTML
        shrink: dict[str, int] = {}
        tpl = self.env.get_template(template)
        for attempt in range(fit_retries + 1):
            html = tpl.render(**self._ctx(shrink=shrink, **extra))
            doc = HTML(string=html, base_url=str(TEMPLATES_DIR)).render()
            over = find_overflows(doc)
            if not over:
                for w in find_wide_boxes(doc):
                    self.warnings.append(f"{out.name}: Box ragt über den Seitenrand: {w}")
                    log.warning(self.warnings[-1])
                break
            if attempt == fit_retries:
                self.warnings.append(f"{out.name}: Text passt nicht in Box(en) {', '.join(over)}")
                log.warning(self.warnings[-1])
                break
            for fid in over:
                shrink[fid] = shrink.get(fid, 0) + 1
        out.parent.mkdir(parents=True, exist_ok=True)
        doc.write_pdf(str(out))
        return out

    # ------------------------------------------------------------------
    def card_hints(self) -> list[Hinweis]:
        return [h for h in self.story.hinweise if h.art == "karte" and not h.raetsel]

    def evidence_hints(self) -> list[Hinweis]:
        return [h for h in self.story.hinweise if h.art != "karte" or h.raetsel]

    def render_all(self) -> list[Path]:
        d = self.kit_dir
        files = []
        files.append(self._pdf("gastgeber.html", d / "01_gastgeber.pdf",
                               karten=self.card_hints(), beweise=self.evidence_hints()))
        files.append(self._pdf("einladungen.html", d / "02_einladungen.pdf"))
        files.append(self._pdf("charakterheft.html", d / "03_charakterhefte.pdf",
                               chars=self.story.charaktere))
        for c in self.story.charaktere:
            files.append(self._pdf("charakterheft.html", d / "charakterhefte" / f"{slug(c.name)}.pdf",
                                   chars=[c]))
        marks = crop_marks(card_layout(self.paper))
        files.append(self._pdf("hinweiskarten.html", d / "04_hinweiskarten.pdf", marks=marks,
                               pages=card_sheets(self.card_hints(), self.paper, backs=True)))
        files.append(self._pdf("hinweiskarten.html", d / "04_hinweiskarten_einseitig.pdf", marks=marks,
                               pages=card_sheets(self.card_hints(), self.paper, backs=False)))
        files.append(self._pdf("beweisstuecke.html", d / "05_beweisstuecke.pdf",
                               beweise=sorted(self.evidence_hints(), key=lambda h: (h.runde, h.id))))
        files.append(self._pdf("aufloesung.html", d / "06_aufloesung.pdf"))
        files.append(self._pdf("namensschilder.html", d / "07_namensschilder.pdf"))
        files.append(self._pdf("notizblatt.html", d / "08_notizblaetter.pdf"))
        files.append(self.make_zip(files))
        return files

    def make_zip(self, files: list[Path]) -> Path:
        zpath = self.kit_dir / "kit.zip"
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            for f in files:
                z.write(f, f.relative_to(self.kit_dir))
            sj = self.kit_dir / "story.json"
            if sj.exists():
                z.write(sj, "story.json")
        return zpath


def render_kit(story: Story, kit_dir: Path, paper: str = "a4") -> tuple[list[Path], list[str]]:
    r = Renderer(story, kit_dir, paper)
    files = r.render_all()
    return files, r.warnings
