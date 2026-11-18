"""Pydantic-Datenmodelle für ein Krimidinner-Kit.

Die Modelle dienen gleichzeitig als JSON-Schema für Geminis strukturierte
Ausgabe. Deshalb: nur einfache Typen (str, int, bool, Listen, verschachtelte
Modelle), keine dicts mit freien Schlüsseln.

IDs: Charaktere, Fakten und Hinweise haben kurze, sprechende IDs
(z. B. "c_baron", "f_uhr_stehen", "h1_03"), auf die andere Teile verweisen.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------
# Bausteine
# --------------------------------------------------------------------------


class Setting(BaseModel):
    ort: str = Field(description="Schauplatz, z. B. 'Chalet Edelweiß, Arlberg'")
    zeit: str = Field(description="Datum/Epoche, z. B. '31. Dezember 1985'")
    atmosphaere: str = Field(description="Stimmung in 2-3 Sätzen")
    raeume: list[str] = Field(description="Wichtige Orte/Räume am Schauplatz")


class Opfer(BaseModel):
    name: str
    hintergrund: str
    todesart: str
    todeszeitpunkt: str = Field(description="Uhrzeit HH:MM")
    fundort: str


class Beziehung(BaseModel):
    zu: str = Field(description="ID des anderen Charakters")
    beschreibung: str


class Charakter(BaseModel):
    id: str
    name: str
    rolle: str = Field(description="Beruf/Funktion, z. B. 'Skilehrer'")
    kostuemtipp: str = ""
    oeffentliches_profil: str = Field("", description="Was alle über die Figur wissen")
    geheimnis: str
    motiv: str
    alibi: str = Field(description="Was die Figur über ihren Aufenthalt zur Tatzeit behauptet")
    beziehungen: list[Beziehung] = []
    darf_sagen: list[str] = Field([], description="Was die Figur ruhig erzählen darf")
    darf_nicht_sagen: list[str] = Field([], description="Was die Figur verbergen muss")
    ist_taeter: bool = False


class Fakt(BaseModel):
    id: str
    text: str = Field(description="Eine objektive Tatsache aus der 'Wahrheit' der Geschichte")


class ZeitEintrag(BaseModel):
    von: str = Field(description="Uhrzeit HH:MM")
    bis: str = Field("", description="Uhrzeit HH:MM, leer = Zeitpunkt")
    ort: str
    personen: list[str] = Field(description="Charakter-IDs, die zu dieser Zeit an diesem Ort sind")
    ereignis: str


RaetselTyp = Literal["caesar", "substitution", "zahlenschloss", "wortsuche"]


class ZiffernQuelle(BaseModel):
    """Eine Ziffer des Zahlenschlosses und woher die Spieler sie kennen."""
    ziffer: int = Field(ge=0, le=9)
    herkunft: str = Field(description="Story-Fakt, aus dem die Ziffer folgt, z. B. 'Zimmernummer der Gräfin (7)'")


class RaetselSpec(BaseModel):
    """Vorgabe für ein Rätsel. Gemini liefert den Klartext, der Code verschlüsselt."""
    typ: RaetselTyp
    klartext: str = Field(description="Botschaft/Inhalt, der nach dem Lösen sichtbar wird")
    ziffern: list[ZiffernQuelle] = Field([], description="Nur für zahlenschloss: 3-4 Ziffern")
    woerter: list[str] = Field([], description="Nur für wortsuche: 6-10 thematische Wörter")


BeweisTyp = Literal["karte", "brief", "zeitung", "notiz", "telegramm"]


class Hinweis(BaseModel):
    id: str
    runde: int = Field(ge=1, le=3)
    empfaenger: str = Field(description="Charakter-ID, die den Hinweis erhält")
    titel: str
    text: str = Field(description="Text auf der Karte/dem Beweisstück, max. ca. 450 Zeichen")
    art: BeweisTyp = "karte"
    fakten: list[str] = Field(description="IDs der Fakten, auf die der Hinweis verweist")
    belastet: list[str] = []
    entlastet: list[str] = []
    raetsel: Optional[RaetselSpec] = None


class Runde(BaseModel):
    nummer: int = Field(ge=1, le=3)
    titel: str
    ablauf: str = Field(description="Was passiert in dieser Runde (für den Gastgeber)")
    vorlesetext: str = Field("", description="Text, den der Gastgeber zu Beginn vorliest")
    hinweis_ids: list[str]


class Aufloesung(BaseModel):
    taeter_id: str
    zusammenfassung: str
    schritte: list[str] = Field(description="Logische Schlusskette, die zum Täter führt")
    tathergang: str


class Gang(BaseModel):
    gang: str
    gericht: str


class Gastgeber(BaseModel):
    vorbereitung: list[str]
    tipps: list[str]
    menue: list[Gang]
    einkaufsliste: list[str]
    deko: list[str] = []


# --------------------------------------------------------------------------
# Vollständige Story
# --------------------------------------------------------------------------


class Story(BaseModel):
    titel: str
    untertitel: str = ""
    thema: str
    sprache: str = "de"
    spieler: int
    design: Literal["chalet", "klassisch", "noir"] = "klassisch"
    seed: int = 1985
    einleitung: str = Field(description="Atmosphärischer Einstieg, wird zu Beginn vorgelesen")
    setting: Setting
    opfer: Opfer
    charaktere: list[Charakter]
    fakten: list[Fakt]
    zeitleiste: list[ZeitEintrag]
    hinweise: list[Hinweis]
    runden: list[Runde]
    aufloesung: Aufloesung
    gastgeber: Gastgeber

    # Hilfsfunktionen ------------------------------------------------------
    def charakter(self, cid: str) -> Charakter | None:
        return next((c for c in self.charaktere if c.id == cid), None)

    def taeter(self) -> list[Charakter]:
        return [c for c in self.charaktere if c.ist_taeter]

    def hinweise_fuer(self, cid: str, runde: int | None = None) -> list[Hinweis]:
        return [h for h in self.hinweise
                if h.empfaenger == cid and (runde is None or h.runde == runde)]


# --------------------------------------------------------------------------
# Zwischenschritte der Generierung (Gemini-Ausgabeschemata)
# --------------------------------------------------------------------------


class GeruestCharakter(BaseModel):
    id: str
    name: str
    rolle: str
    geheimnis: str
    motiv: str
    alibi: str
    ist_taeter: bool


class Geruest(BaseModel):
    """Schritt 1: nur die logische Wahrheit des Falls."""
    titel: str
    untertitel: str
    design: Literal["chalet", "klassisch", "noir"]
    setting: Setting
    opfer: Opfer
    charaktere: list[GeruestCharakter]
    tathergang: str
    fakten: list[Fakt]
    zeitleiste: list[ZeitEintrag]


class CharakterDetails(BaseModel):
    id: str
    kostuemtipp: str
    oeffentliches_profil: str
    beziehungen: list[Beziehung]
    darf_sagen: list[str]
    darf_nicht_sagen: list[str]


class Ausarbeitung(BaseModel):
    """Schritt 2: Texte, Hinweise und Runden auf Basis des Gerüsts."""
    einleitung: str
    charaktere: list[CharakterDetails]
    hinweise: list[Hinweis]
    runden: list[Runde]
    aufloesung: Aufloesung
    gastgeber: Gastgeber


class Ermittlung(BaseModel):
    """Antwort des Gegenchecks: wen hält das Prüfmodell für den Täter?"""
    taeter_id: str
    sicherheit: float = Field(ge=0, le=1, description="0 = geraten, 1 = zwingend")
    begruendung: str
    alternative_verdaechtige: list[str] = []
