import pytest

from krimi import puzzles as p


def test_normalize():
    assert p.normalize("Größe Übel") == "GROESSE UEBEL"
    assert p.letters_only("Café, 1985!") == "CAFE"


def test_caesar_roundtrip_and_seed():
    c = p.caesar("Treffpunkt Zimmer sieben", seed=42)
    assert c.geheimtext != c.klartext
    assert p.caesar_decode(c.geheimtext, c.verschiebung) == c.klartext
    assert p.caesar("Treffpunkt Zimmer sieben", seed=42).geheimtext == c.geheimtext
    assert p.caesar("ABC", shift=3).geheimtext == "DEF"
    assert p.caesar("XYZ", shift=3).geheimtext == "ABC"


def test_caesar_keeps_punctuation():
    assert p.caesar("A, B.", shift=1).geheimtext == "B, C."


def test_substitution_roundtrip():
    c = p.substitution("Die Diebin ist unter uns", seed=7)
    assert p.substitution_decode(c.geheimtext, c.schluessel) == c.klartext
    assert all(k != v for k, v in c.schluessel.items())
    assert sorted(c.schluessel.values()) == list(p.ALPHABET)
    assert p.substitution("Die Diebin ist unter uns", seed=7).geheimtext == c.geheimtext
    assert p.substitution("Die Diebin ist unter uns", seed=8).geheimtext != c.geheimtext


def test_number_lock():
    lock = p.number_lock([(7, "Zimmer der Gräfin (7)"), (3, "Gämsen im Wappen"), (5, "Startnummer")])
    assert lock.code == "735"
    assert len(lock.hinweise) == 3
    assert "(7)" not in lock.hinweise[0]
    with pytest.raises(ValueError):
        p.number_lock([(1, "a"), (2, "b")])


WORDS = ["Schnee", "Sekt", "Rakete", "Blei", "Piste", "Gondel", "Kamin", "Fondue"]


def test_word_search_contains_words():
    ws = p.word_search(WORDS, "Ich entlarve die Diebin", seed=1)
    n = len(ws.grid)
    assert all(len(r) == n for r in ws.grid)
    for w in ws.woerter:
        cells = ws.positionen[w]
        assert "".join(ws.grid[y][x] for y, x in cells) == w
        # gerade Linie
        dy, dx = cells[1][0] - cells[0][0], cells[1][1] - cells[0][1]
        assert all(cells[i + 1][0] - cells[i][0] == dy and cells[i + 1][1] - cells[i][1] == dx
                   for i in range(len(cells) - 1))


def test_word_search_hidden_message():
    ws = p.word_search(WORDS, "Ich entlarve die Diebin", seed=1)
    used = {c for cells in ws.positionen.values() for c in cells}
    leftovers = [ws.grid[y][x] for y in range(len(ws.grid)) for x in range(len(ws.grid))
                 if (y, x) not in used]
    assert "".join(leftovers).startswith("ICHENTLARVEDIEDIEBIN")


def test_word_search_reproducible():
    a = p.word_search(WORDS, "Botschaft", seed=9).rows()
    assert a == p.word_search(WORDS, "Botschaft", seed=9).rows()
    assert a != p.word_search(WORDS, "Botschaft", seed=10).rows()


@pytest.mark.parametrize("seed", range(10))
def test_seating_puzzle_unique(seed):
    names = ["Vroni", "Ferdl", "Gräfin", "Hagen", "Monika", "Rocco"]
    sp = p.seating_puzzle(names, seed=seed)
    solutions = p.solve_seating(names, sp.hinweise)
    assert solutions == [tuple(sp.loesung)]
    assert len(sp.texte) == len(sp.hinweise)
    # minimal: jeder Hinweis ist nötig
    for c in sp.hinweise:
        rest = [x for x in sp.hinweise if x is not c]
        assert len(p.solve_seating(names, rest)) > 1
