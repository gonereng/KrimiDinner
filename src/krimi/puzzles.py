"""Deterministische Rätsel-Generatoren (ohne KI, ohne Abhängigkeit von der Story).

Alle Generatoren sind über `seed` reproduzierbar und liefern Rätsel + Lösung.
Das Modul ist bewusst eigenständig und kann z. B. für Logikrätsel-Hefte
wiederverwendet werden.
"""
from __future__ import annotations

import itertools
import random
import string
import unicodedata
from dataclasses import dataclass, field

ALPHABET = string.ascii_uppercase


def normalize(text: str) -> str:
    """Großbuchstaben, Umlaute -> AE/OE/UE/SS, sonstige Akzente entfernt."""
    text = text.upper()
    for a, b in (("Ä", "AE"), ("Ö", "OE"), ("Ü", "UE"), ("ß", "SS"), ("ẞ", "SS")):
        text = text.replace(a, b)
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def letters_only(text: str) -> str:
    return "".join(ch for ch in normalize(text) if ch in ALPHABET)


# --------------------------------------------------------------------------
# Chiffren
# --------------------------------------------------------------------------

@dataclass
class Cipher:
    typ: str
    klartext: str           # normalisierter Klartext
    geheimtext: str
    schluessel: dict[str, str]  # Klartext-Buchstabe -> Geheimbuchstabe
    hilfe: str              # Tipp für die Spieler
    verschiebung: int | None = None


def caesar(text: str, shift: int | None = None, seed: int = 0) -> Cipher:
    if shift is None:
        shift = random.Random(seed).randint(3, 23)
    shift %= 26
    key = {a: ALPHABET[(i + shift) % 26] for i, a in enumerate(ALPHABET)}
    plain = normalize(text)
    enc = "".join(key.get(ch, ch) for ch in plain)
    return Cipher("caesar", plain, enc, key,
                  f"Jeder Buchstabe wurde um dieselbe Anzahl Stellen im Alphabet verschoben.",
                  verschiebung=shift)


def caesar_decode(geheimtext: str, shift: int) -> str:
    return "".join(ALPHABET[(ALPHABET.index(c) - shift) % 26] if c in ALPHABET else c
                   for c in geheimtext)


def substitution(text: str, seed: int = 0, hinweise: int = 3) -> Cipher:
    """Monoalphabetische Substitution. `hinweise` Buchstabenpaare werden verraten."""
    rnd = random.Random(seed)
    perm = list(ALPHABET)
    while True:  # kein Buchstabe auf sich selbst
        rnd.shuffle(perm)
        if all(a != b for a, b in zip(ALPHABET, perm)):
            break
    key = dict(zip(ALPHABET, perm))
    plain = normalize(text)
    enc = "".join(key.get(ch, ch) for ch in plain)
    used = sorted({c for c in plain if c in ALPHABET}, key=lambda c: -plain.count(c))
    verraten = used[:hinweise]
    hilfe = "Jeder Buchstabe steht für einen anderen. Bekannt: " + ", ".join(
        f"{key[p]} = {p}" for p in verraten)
    return Cipher("substitution", plain, enc, key, hilfe)


def substitution_decode(geheimtext: str, key: dict[str, str]) -> str:
    inv = {v: k for k, v in key.items()}
    return "".join(inv.get(c, c) for c in geheimtext)


# --------------------------------------------------------------------------
# Zahlenschloss
# --------------------------------------------------------------------------

@dataclass
class Lock:
    code: str
    hinweise: list[str]  # ein Hinweis pro Stelle, in Reihenfolge


def number_lock(quellen: list[tuple[int, str]]) -> Lock:
    """quellen: [(ziffer, herkunft), …] -> Code + Spieler-Hinweise je Stelle."""
    if not 3 <= len(quellen) <= 4:
        raise ValueError("Zahlenschloss braucht 3–4 Ziffern")
    ordinal = ["Erste", "Zweite", "Dritte", "Vierte"]
    code = "".join(str(int(z) % 10) for z, _ in quellen)
    hinweise = [f"{ordinal[i]} Ziffer: {_raetselhaft(h)}" for i, (_, h) in enumerate(quellen)]
    return Lock(code, hinweise)


def _raetselhaft(herkunft: str) -> str:
    """Entfernt eine in Klammern verratene Ziffer, z. B. 'Zimmer der Gräfin (7)'."""
    import re
    return re.sub(r"\s*\(\s*\d\s*\)\s*$", "", herkunft).strip()


# --------------------------------------------------------------------------
# Wortsuche mit versteckter Botschaft
# --------------------------------------------------------------------------

DIRECTIONS = [(0, 1), (1, 0), (1, 1), (-1, 1), (0, -1), (-1, 0), (-1, -1), (1, -1)]


@dataclass
class WordSearch:
    grid: list[list[str]]
    woerter: list[str]
    positionen: dict[str, list[tuple[int, int]]]
    botschaft: str           # versteckte Botschaft (Buchstaben)
    botschaft_zellen: list[tuple[int, int]]
    hilfe: str

    def rows(self) -> list[str]:
        return ["".join(r) for r in self.grid]


def word_search(woerter: list[str], botschaft: str = "", seed: int = 0,
                size: int | None = None, max_tries: int = 200) -> WordSearch:
    """Platziert Wörter im Gitter; die übrigen Felder (zeilenweise gelesen)
    beginnen mit der versteckten Botschaft, danach Füllbuchstaben."""
    words = [letters_only(w) for w in woerter if letters_only(w)]
    msg = letters_only(botschaft)
    if not words:
        raise ValueError("Wortsuche braucht Wörter")
    longest = max(len(w) for w in words)
    letters = sum(len(w) for w in words)
    n = size or max(longest + 2, 10)
    while n * n < letters * 0.9 + len(msg) + 4:  # Platz grob abschätzen
        n += 1
    rnd = random.Random(seed)
    for attempt in range(max_tries):
        grid = [[""] * n for _ in range(n)]
        pos: dict[str, list[tuple[int, int]]] = {}
        ok = True
        for w in sorted(words, key=len, reverse=True):
            placed = False
            cand = [(r, c, d) for r in range(n) for c in range(n) for d in DIRECTIONS]
            rnd.shuffle(cand)
            for r, c, (dr, dc) in cand:
                cells = [(r + i * dr, c + i * dc) for i in range(len(w))]
                if not all(0 <= y < n and 0 <= x < n for y, x in cells):
                    continue
                if all(grid[y][x] in ("", w[i]) for i, (y, x) in enumerate(cells)):
                    for i, (y, x) in enumerate(cells):
                        grid[y][x] = w[i]
                    pos[w] = cells
                    placed = True
                    break
            if not placed:
                ok = False
                break
        free = [(y, x) for y in range(n) for x in range(n) if grid[y][x] == ""]
        if ok and len(free) >= len(msg):
            for (y, x), ch in zip(free, msg):
                grid[y][x] = ch
            for y, x in free[len(msg):]:
                grid[y][x] = rnd.choice(ALPHABET)
            hilfe = ("Streiche alle gesuchten Wörter (waagerecht, senkrecht, diagonal, auch rückwärts). "
                     + (f"Die ersten {len(msg)} übrig gebliebenen Buchstaben ergeben – zeilenweise gelesen – "
                        f"eine Botschaft." if msg else ""))
            return WordSearch(grid, words, pos, msg, free[:len(msg)], hilfe)
        if attempt % 20 == 19:
            n += 1
    raise ValueError("Wortsuche konnte nicht erzeugt werden")


# --------------------------------------------------------------------------
# Logikgitter: Wer saß wo?
# --------------------------------------------------------------------------

@dataclass
class Clue:
    art: str          # "platz", "nicht_platz", "links_von", "neben", "nicht_neben"
    a: str
    b: str | int | None = None

    def text(self) -> str:
        if self.art == "platz":
            return f"{self.a} saß auf Platz {self.b}."
        if self.art == "nicht_platz":
            return f"{self.a} saß nicht auf Platz {self.b}."
        if self.art == "links_von":
            return f"{self.a} saß direkt links von {self.b}."
        if self.art == "neben":
            return f"{self.a} saß neben {self.b}."
        return f"{self.a} saß nicht neben {self.b}."

    def holds(self, perm: tuple[str, ...]) -> bool:
        i = perm.index(self.a)  # Platz = Index+1, Reihe von links nach rechts
        if self.art == "platz":
            return i + 1 == self.b
        if self.art == "nicht_platz":
            return i + 1 != self.b
        j = perm.index(self.b)  # type: ignore[arg-type]
        if self.art == "links_von":
            return j == i + 1
        if self.art == "neben":
            return abs(i - j) == 1
        return abs(i - j) != 1


@dataclass
class SeatingPuzzle:
    personen: list[str]
    hinweise: list[Clue]
    loesung: list[str]  # Platz 1..n
    texte: list[str] = field(default_factory=list)


def seating_puzzle(personen: list[str], seed: int = 0) -> SeatingPuzzle:
    """Erzeugt ein Sitzordnungs-Rätsel (eine Reihe, Plätze 1..n) mit eindeutiger Lösung."""
    if not 3 <= len(personen) <= 7:
        raise ValueError("Logikgitter: 3–7 Personen")
    rnd = random.Random(seed)
    loesung = personen[:]
    rnd.shuffle(loesung)
    sol = tuple(loesung)
    n = len(personen)

    pool: list[Clue] = []
    for p in personen:
        pool.append(Clue("platz", p, sol.index(p) + 1))
        for k in range(1, n + 1):
            if sol.index(p) + 1 != k:
                pool.append(Clue("nicht_platz", p, k))
    for a, b in itertools.permutations(personen, 2):
        c_left = Clue("links_von", a, b)
        if c_left.holds(sol):
            pool.append(c_left)
        if personen.index(a) < personen.index(b):
            for art in ("neben", "nicht_neben"):
                c = Clue(art, a, b)
                if c.holds(sol):
                    pool.append(c)
    # Direkte Platzangaben seltener ziehen – das macht es spannender
    rnd.shuffle(pool)
    pool.sort(key=lambda c: c.art == "platz")

    alle = list(itertools.permutations(personen))
    chosen: list[Clue] = []
    remaining = alle
    for c in pool:
        nxt = [p for p in remaining if c.holds(p)]
        if len(nxt) < len(remaining):
            chosen.append(c)
            remaining = nxt
        if len(remaining) == 1:
            break
    # überflüssige Hinweise entfernen
    for c in chosen[:]:
        rest = [x for x in chosen if x is not c]
        if sum(all(x.holds(p) for x in rest) for p in alle) == 1:
            chosen = rest
    rnd.shuffle(chosen)
    return SeatingPuzzle(personen, chosen, list(sol), [c.text() for c in chosen])


def solve_seating(personen: list[str], hinweise: list[Clue]) -> list[tuple[str, ...]]:
    return [p for p in itertools.permutations(personen) if all(c.holds(p) for c in hinweise)]
