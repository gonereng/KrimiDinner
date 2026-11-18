"""Logikprüfung eines Kits.

1. Deterministisch (check_story): Struktur, Verweise, Ent-/Belastung, Zeitleiste.
2. Per Gemini (cross_check): Ein Prüfmodell bekommt nur Verdächtige + Hinweise
   und soll den Täter ermitteln.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .models import Ermittlung, Story

MIN_TAETER_HINWEISE = 3
MIN_SICHERHEIT = 0.7


@dataclass
class Report:
    fehler: list[str] = field(default_factory=list)
    warnungen: list[str] = field(default_factory=list)
    ermittlung: Ermittlung | None = None

    @property
    def ok(self) -> bool:
        return not self.fehler

    def to_dict(self) -> dict:
        return {"ok": self.ok, "fehler": self.fehler, "warnungen": self.warnungen,
                "ermittlung": self.ermittlung.model_dump() if self.ermittlung else None}


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
            if rs.typ == "zahlenschloss" and not 3 <= len(rs.ziffern) <= 4:
                E(f"Hinweis {h.id}: Zahlenschloss braucht 3–4 Ziffern")
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
# Gegencheck per Gemini
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
    from .gemini_client import load_prompt
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
    """Deterministische Prüfung und – falls sie besteht und ein Client da ist – Gegencheck."""
    r = check_story(story)
    if r.ok and client is not None and model:
        erm = cross_check(story, client, model)
        r.ermittlung = erm
        taeter = story.taeter()[0]
        if erm.taeter_id != taeter.id:
            r.fehler.append(
                f"Mehrdeutig: Der Gegencheck hält '{erm.taeter_id}' für den Täter "
                f"(richtig wäre '{taeter.id}'). Begründung des Prüfers: {erm.begruendung}")
        elif erm.sicherheit < MIN_SICHERHEIT:
            r.fehler.append(
                f"Mehrdeutig: Der Gegencheck findet zwar '{taeter.id}', ist aber unsicher "
                f"(Sicherheit {erm.sicherheit:.2f}). Weitere Verdächtige: "
                f"{', '.join(erm.alternative_verdaechtige) or '–'}. Begründung: {erm.begruendung}")
    return r
