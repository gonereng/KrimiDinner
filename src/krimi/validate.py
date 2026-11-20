"""Logikprüfung eines Kits.

1. Deterministisch (check_story): Struktur, Verweise, Ent-/Belastung, Zeitleiste.
2. Per KI (cross_check): Ein Prüfmodell bekommt nur Verdächtige + Hinweise
   und soll den Täter ermitteln.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from .models import Ermittlung, Story

MIN_TAETER_HINWEISE = 3
MIN_SICHERHEIT = 0.7
MIN_INHALT_ZEICHEN = 150


@dataclass
class Report:
    fehler: list[str] = field(default_factory=list)
    warnungen: list[str] = field(default_factory=list)
    ermittlung: Ermittlung | None = None
    gegenchecks: list[dict] = field(default_factory=list)  # je geprüfter Besetzung: spieler + Ergebnis

    @property
    def ok(self) -> bool:
        return not self.fehler

    def to_dict(self) -> dict:
        return {"ok": self.ok, "fehler": self.fehler, "warnungen": self.warnungen,
                "ermittlung": self.ermittlung.model_dump() if self.ermittlung else None,
                "gegenchecks": self.gegenchecks}


# --------------------------------------------------------------------------
# Zeit-Hilfen
# --------------------------------------------------------------------------

def to_minutes(hhmm: str) -> int:
    """'23:40' -> 1420. Zeiten vor 12:00 gelten als nach Mitternacht (Abendspiel)."""
    h, m = hhmm.strip().split(":")
    total = int(h) * 60 + int(m)
    if not (0 <= int(h) < 24 and 0 <= int(m) < 60):
        raise ValueError(hhmm)
    return total + 24 * 60 if total < 12 * 60 else total


def _interval(von: str, bis: str) -> tuple[int, int]:
    start = to_minutes(von)
    end = to_minutes(bis) if bis else start + 1
    return start, max(end, start + 1)


# --------------------------------------------------------------------------
# Deterministische Prüfung
# --------------------------------------------------------------------------

def check_story(story: Story) -> Report:
    """Prüft ein Kit – bei variabler Spielerzahl für jede mögliche Besetzung einzeln."""
    if not story.variabel:
        return check_cast(story)
    return check_variabel(story)


def check_cast(story: Story) -> Report:
    """Prüft eine feste Besetzung (alle Charaktere spielen mit)."""
    r = Report()
    E, W = r.fehler.append, r.warnungen.append
    char_ids = [c.id for c in story.charaktere]
    chars = set(char_ids)
    fakten = {f.id for f in story.fakten}
    hint_ids = [h.id for h in story.hinweise]

    # --- Grundstruktur ---------------------------------------------------
    for label, ids in (("Charakter", char_ids), ("Fakt", [f.id for f in story.fakten]), ("Hinweis", hint_ids)):
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            E(f"Doppelte {label}-IDs: {', '.join(sorted(dup))}")

    if len(story.charaktere) != story.spieler:
        E(f"{len(story.charaktere)} Charaktere, aber {story.spieler} Spieler vorgesehen")

    taeter = story.taeter()
    if len(taeter) != 1:
        E(f"Es muss genau einen Täter geben, gefunden: {len(taeter)} "
          f"({', '.join(c.id for c in taeter) or 'keiner'})")
    elif story.aufloesung.taeter_id != taeter[0].id:
        E(f"Auflösung nennt '{story.aufloesung.taeter_id}', markiert ist aber '{taeter[0].id}'")
    taeter_id = taeter[0].id if len(taeter) == 1 else None

    for c in story.charaktere:
        for feld in ("motiv", "geheimnis", "alibi"):
            if not getattr(c, feld).strip():
                E(f"Charakter {c.id} hat kein(e) {feld}")
        for b in c.beziehungen:
            if b.zu not in chars:
                E(f"Charakter {c.id}: Beziehung zu unbekanntem Charakter '{b.zu}'")

    # --- Hinweise ----------------------------------------------------------
    for h in story.hinweise:
        if h.empfaenger not in chars:
            E(f"Hinweis {h.id}: unbekannter Empfänger '{h.empfaenger}'")
        if not h.fakten:
            E(f"Hinweis {h.id} verweist auf keinen Fakt")
        for f in h.fakten:
            if f not in fakten:
                E(f"Hinweis {h.id}: unbekannter Fakt '{f}'")
        for cid in h.belastet + h.entlastet:
            if cid not in chars:
                E(f"Hinweis {h.id}: unbekannter Charakter '{cid}' in belastet/entlastet")
        if set(h.belastet) & set(h.entlastet):
            E(f"Hinweis {h.id} belastet und entlastet dieselbe Person")
        if len(h.text) > 600:
            W(f"Hinweis {h.id} ist sehr lang ({len(h.text)} Zeichen) – passt evtl. nicht auf die Karte")
        if h.raetsel:
            rs = h.raetsel
            if rs.typ == "zahlenschloss":
                if not 3 <= len(rs.ziffern) <= 4:
                    E(f"Hinweis {h.id}: Zahlenschloss braucht 3–4 Ziffern")
                code = "".join(str(z.ziffer) for z in rs.ziffern)
                for z in rs.ziffern:
                    zahlen = re.findall(r"\d+", z.herkunft)
                    if code in z.herkunft or str(z.ziffer) in zahlen or any(code in n for n in zahlen):
                        E(f"Hinweis {h.id}: Ziffer-Hinweis „{z.herkunft}“ verrät die Lösung – "
                          f"er soll nur sagen, WO die Ziffer zu finden ist, die Zahl steht in einem anderen Hinweis")
                if len(rs.klartext.strip()) < MIN_INHALT_ZEICHEN:
                    E(f"Hinweis {h.id}: Der Inhalt hinter dem Zahlenschloss ist nur eine Kurzbeschreibung "
                      f"({len(rs.klartext.strip())} Zeichen) – nötig ist der vollständige Text des Dokuments, "
                      f"das der Gastgeber den Spielern zeigt")
            if rs.typ == "wortsuche" and len(rs.woerter) < 4:
                E(f"Hinweis {h.id}: Wortsuche braucht mindestens 4 Wörter")
            if not rs.klartext.strip():
                E(f"Hinweis {h.id}: Rätsel ohne Klartext")

    # jeder Unschuldige mindestens einmal entlastet
    entlastet = defaultdict(list)
    belastet = defaultdict(list)
    for h in story.hinweise:
        for cid in h.entlastet:
            entlastet[cid].append(h)
        for cid in h.belastet:
            belastet[cid].append(h)
    for c in story.charaktere:
        if c.id != taeter_id and not entlastet[c.id]:
            E(f"Unschuldiger Charakter {c.id} ({c.name}) wird durch keinen Hinweis entlastet")
    if taeter_id:
        if entlastet[taeter_id]:
            E(f"Der Täter {taeter_id} wird durch Hinweis(e) {', '.join(h.id for h in entlastet[taeter_id])} "
              f"entlastet – das macht den Fall widersprüchlich")
        # unabhängig = unterschiedliche Fakten-Mengen
        unabhaengig = {frozenset(h.fakten) for h in belastet[taeter_id] if h.fakten}
        verschiedene_fakten = {f for h in belastet[taeter_id] for f in h.fakten}
        n = min(len(unabhaengig), len(verschiedene_fakten))
        if n < MIN_TAETER_HINWEISE:
            E(f"Der Täter {taeter_id} wird nur durch {n} unabhängige Hinweise belastet "
              f"(mindestens {MIN_TAETER_HINWEISE} mit verschiedenen Fakten nötig)")

    # jeder Spieler pro Runde mindestens ein Hinweis
    for runde in (1, 2, 3):
        for c in story.charaktere:
            if not story.hinweise_fuer(c.id, runde):
                E(f"Charakter {c.id} bekommt in Runde {runde} keinen Hinweis")

    # --- Runden ------------------------------------------------------------
    nummern = sorted(r_.nummer for r_ in story.runden)
    if nummern != [1, 2, 3]:
        E(f"Es müssen genau die Runden 1, 2, 3 existieren (gefunden: {nummern})")
    by_id = {h.id: h for h in story.hinweise}
    zugeordnet = set()
    for rd in story.runden:
        for hid in rd.hinweis_ids:
            if hid not in by_id:
                E(f"Runde {rd.nummer}: unbekannter Hinweis '{hid}'")
            elif by_id[hid].runde != rd.nummer:
                E(f"Runde {rd.nummer} listet Hinweis {hid}, der aber zu Runde {by_id[hid].runde} gehört")
            zugeordnet.add(hid)
    for h in story.hinweise:
        if h.id not in zugeordnet:
            E(f"Hinweis {h.id} ist keiner Runde zugeordnet (runden[].hinweis_ids)")

    # --- Zeitleiste --------------------------------------------------------
    r.fehler.extend(check_timeline(story))

    if len(story.aufloesung.schritte) < 3:
        W("Die Auflösung hat weniger als 3 Schritte")
    return r


# --------------------------------------------------------------------------
# Variable Spielerzahl
# --------------------------------------------------------------------------

NAME_STOP = {"von", "van", "der", "den", "de", "la", "le", "zu", "und", "dr.", "prof.", "graf", "gräfin",
             "baron", "baronin", "fürst", "fürstin", "lady", "lord", "sir", "madame", "monsieur", "frau",
             "herr", "miss", "mister", "mrs.", "mr."}


def name_tokens(name: str) -> set[str]:
    """Wörter, an denen man eine Erwähnung der Figur erkennt (Vor-/Nachname, Spitzname)."""
    tokens = {name.strip()}
    tokens |= set(re.findall(r"[„\"“'‚](.+?)[“\"”'‘]", name))
    plain = re.sub(r"[„\"“'‚][^“\"”'‘]*[“\"”'‘]", " ", name)
    tokens |= {w for w in re.findall(r"[\wÄÖÜäöüß.-]+", plain) if len(w) >= 3 and w.lower() not in NAME_STOP}
    return {t for t in tokens if t}


def besetzung(story: Story, n: int) -> Story:
    """Das Kit, wie es bei n Spielern gespielt wird (optionale Figuren und ihre Hinweise entfallen)."""
    ids = {c.id for c in story.charaktere if story.stufe(c.id) <= n}
    hint_ids = {h.id for h in story.hinweise if story.hinweis_stufe(h) <= n}
    s = story.model_copy(deep=True)
    s.charaktere = [c for c in s.charaktere if c.id in ids]
    for c in s.charaktere:
        c.ab_spieler = 0
        c.beziehungen = [b for b in c.beziehungen if b.zu in ids]
    s.hinweise = [h for h in s.hinweise if h.id in hint_ids]
    for rd in s.runden:
        rd.hinweis_ids = [i for i in rd.hinweis_ids if i in hint_ids]
    for e in s.zeitleiste:
        e.personen = [p for p in e.personen if p in ids]
    s.spieler, s.spieler_min = n, 0
    return s


def _bereich(ns: list[int]) -> str:
    return f"{ns[0]} Spielern" if len(ns) == 1 else f"{ns[0]}–{ns[-1]} Spielern"


def mention_errors(story: Story) -> list[str]:
    """Kein Text darf eine Figur erwähnen, die bei seiner Spielerzahl fehlen kann."""
    fehler = []
    optional = [(c, story.stufe(c.id), name_tokens(c.name)) for c in story.charaktere
                if story.stufe(c.id) > story.min_spieler]
    if not optional:
        return fehler

    def check(label: str, stufe: int, texte: list[str]):
        text = "\n".join(t for t in texte if t)
        for c, c_stufe, tokens in optional:
            if c_stufe <= stufe:
                continue
            for t in tokens:
                if re.search(rf"(?<![\wÄÖÜäöüß]){re.escape(t)}(?![\wÄÖÜäöüß])", text):
                    fehler.append(f"{label} erwähnt „{c.name}“, die/der erst ab {c_stufe} Spielern dabei ist – "
                                  f"bei weniger Spielern fehlt diese Figur. Text so umschreiben, dass er ohne "
                                  f"sie funktioniert, oder den Hinweis der Figur selbst zuordnen")
                    break

    m = story.min_spieler
    a = story.aufloesung
    check("Die Einleitung/Spielleitung", m, [story.titel, story.untertitel, story.einleitung,
                                            story.setting.atmosphaere, story.opfer.hintergrund,
                                            *[f"{r.titel} {r.ablauf} {r.vorlesetext}" for r in story.runden],
                                            *story.gastgeber.vorbereitung, *story.gastgeber.tipps])
    check("Die Auflösung", m, [a.zusammenfassung, a.tathergang, *a.schritte])
    for c in story.charaktere:
        st = story.stufe(c.id)
        check(f"Das Charakterheft von {c.id} (ab {st} Spielern)", st,
              [c.rolle, c.kostuemtipp, c.oeffentliches_profil, c.geheimnis, c.motiv, c.alibi,
               *[b.beschreibung for b in c.beziehungen], *c.darf_sagen, *c.darf_nicht_sagen])
        for b in c.beziehungen:
            if story.stufe(b.zu) > st:
                fehler.append(f"{c.id} (ab {st} Spielern) hat eine Beziehung zu {b.zu}, die/der erst ab "
                              f"{story.stufe(b.zu)} Spielern dabei ist")
    for h in story.hinweise:
        st = story.hinweis_stufe(h)
        texte = [h.titel, h.text]
        if h.raetsel:
            texte += [h.raetsel.klartext, *[z.herkunft for z in h.raetsel.ziffern], *h.raetsel.woerter]
        check(f"Hinweis {h.id} (ab {st} Spielern)", st, texte)
    return fehler


def check_variabel(story: Story) -> Report:
    r = Report()
    E = r.fehler.append
    m, mx = story.min_spieler, story.spieler
    if not 3 <= m < mx:
        E(f"Ungültiger Spielerbereich {m}–{mx}")
        return r
    for c in story.charaktere:
        if c.ab_spieler and not m <= c.ab_spieler <= mx:
            E(f"{c.id}: ab_spieler={c.ab_spieler} liegt außerhalb von {m}–{mx}")
    for n in story.spielerzahlen():
        anzahl = sum(1 for c in story.charaktere if story.stufe(c.id) <= n)
        if anzahl != n:
            E(f"Bei {n} Spielern gibt es {anzahl} Figuren – nötig sind genau {n} "
              f"(Stammbesetzung: {m} Figuren, danach je genau eine optionale Figur pro Spielerzahl)")
    for t in story.taeter():
        if story.stufe(t.id) > m:
            E(f"Der Täter {t.id} ist eine optionale Figur (ab {story.stufe(t.id)} Spielern) – "
              f"er/sie muss zur Stammbesetzung gehören")
    for c in story.charaktere:
        if story.stufe(c.id) > m and not c.flexibel:
            r.warnungen.append(f"Optionale Figur {c.id} ist nicht als geschlechtsflexibel markiert")
    # Verweise auf unbekannte IDs fallen beim Aufteilen sonst unter den Tisch – vorher prüfen
    chars = {c.id for c in story.charaktere}
    hint_ids = {h.id for h in story.hinweise}
    for h in story.hinweise:
        if h.empfaenger not in chars:
            E(f"Hinweis {h.id}: unbekannter Empfänger '{h.empfaenger}'")
        for cid in h.belastet + h.entlastet:
            if cid not in chars:
                E(f"Hinweis {h.id}: unbekannter Charakter '{cid}' in belastet/entlastet")
    for rd in story.runden:
        for hid in rd.hinweis_ids:
            if hid not in hint_ids:
                E(f"Runde {rd.nummer}: unbekannter Hinweis '{hid}'")
    for e in story.zeitleiste:
        for p in e.personen:
            if p not in chars:
                E(f"Zeitleiste {e.von}: unbekannte Person '{p}'")
    r.fehler.extend(mention_errors(story))

    # jede Besetzung einzeln prüfen; gleiche Fehler zusammenfassen
    seen: dict[str, list[int]] = {}
    warn: dict[str, list[int]] = {}
    for n in story.spielerzahlen():
        sub = check_cast(besetzung(story, n))
        for f in sub.fehler:
            seen.setdefault(f, []).append(n)
        for w in sub.warnungen:
            warn.setdefault(w, []).append(n)
    r.fehler += [f"Bei {_bereich(ns)}: {f}" for f, ns in seen.items()]
    r.warnungen += [w for w in warn]
    return r


def check_timeline(story: Story) -> list[str]:
    fehler = []
    chars = {c.id for c in story.charaktere}
    pro_person: dict[str, list[tuple[int, int, str, str]]] = defaultdict(list)
    for e in story.zeitleiste:
        try:
            start, end = _interval(e.von, e.bis)
        except (ValueError, AttributeError):
            fehler.append(f"Zeitleiste: ungültige Uhrzeit in '{e.ereignis[:40]}' ({e.von}–{e.bis})")
            continue
        for p in e.personen:
            if p not in chars:
                fehler.append(f"Zeitleiste {e.von}: unbekannte Person '{p}'")
                continue
            pro_person[p].append((start, end, e.ort, e.von))
    for p, slots in pro_person.items():
        slots.sort()
        for i, a in enumerate(slots):
            for b in slots[i + 1:]:
                if b[0] >= a[1]:
                    break
                if a[2].strip().lower() != b[2].strip().lower():
                    fehler.append(f"Zeitleiste: {p} ist gleichzeitig in '{a[2]}' ({a[3]}) "
                                  f"und in '{b[2]}' ({b[3]})")
    return fehler


# --------------------------------------------------------------------------
# Gegencheck per KI
# --------------------------------------------------------------------------

def hinweise_als_text(story: Story) -> str:
    zeilen = []
    for h in sorted(story.hinweise, key=lambda h: (h.runde, h.id)):
        z = f"[Runde {h.runde}] {h.titel}: {h.text}"
        if h.raetsel:
            if h.raetsel.typ == "zahlenschloss":
                z += f" (Rätsel gelöst – Inhalt: {h.raetsel.klartext})"
            else:
                z += f" (Rätsel gelöst – Botschaft: {h.raetsel.klartext})"
        zeilen.append(z)
    return "\n".join(zeilen)


def cross_check(story: Story, client, model: str) -> Ermittlung:
    from .llm_client import load_prompt
    verdaechtige = "\n".join(
        f"- {c.id}: {c.name}, {c.rolle}. {c.oeffentliches_profil} Behauptetes Alibi: {c.alibi}"
        for c in story.charaktere)
    prompt = load_prompt(
        "ermittlung", titel=story.titel,
        opfer=f"{story.opfer.name} wurde um ca. {story.opfer.todeszeitpunkt} tot aufgefunden "
              f"({story.opfer.fundort}, {story.opfer.todesart}).",
        verdaechtige=verdaechtige, hinweise=hinweise_als_text(story))
    return client.generate_json(prompt, Ermittlung, model, label="Gegencheck", temperature=0.2)


def full_check(story: Story, client=None, model: str | None = None) -> Report:
    """Deterministische Prüfung und – falls sie besteht und ein Client da ist – Gegencheck.
    Bei variabler Spielerzahl ermittelt der Prüfer mit der kleinsten UND der größten Besetzung."""
    r = check_story(story)
    if not (r.ok and client is not None and model):
        return r
    faelle = [story] if not story.variabel else [besetzung(story, story.min_spieler),
                                                 besetzung(story, story.spieler)]
    taeter = story.taeter()[0]
    for i, fall in enumerate(faelle):
        erm = cross_check(fall, client, model)
        vor = f"Bei {fall.spieler} Spielern: " if story.variabel else ""
        if i == 0:
            r.ermittlung = erm
        r.gegenchecks.append({"spieler": fall.spieler, **erm.model_dump()})
        if erm.taeter_id != taeter.id:
            r.fehler.append(
                f"{vor}Mehrdeutig: Der Gegencheck hält '{erm.taeter_id}' für den Täter "
                f"(richtig wäre '{taeter.id}'). Begründung des Prüfers: {erm.begruendung}")
        elif erm.sicherheit < MIN_SICHERHEIT:
            r.fehler.append(
                f"{vor}Mehrdeutig: Der Gegencheck findet zwar '{taeter.id}', ist aber unsicher "
                f"(Sicherheit {erm.sicherheit:.2f}). Weitere Verdächtige: "
                f"{', '.join(erm.alternative_verdaechtige) or '–'}. Begründung: {erm.begruendung}")
    return r
