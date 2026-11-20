"""Variable Spielerzahl (Demo: 6 Stammfiguren + 4 geschlechtsflexible optionale Figuren)."""
import pytest

from krimi.models import Beziehung, Ermittlung
from krimi.validate import besetzung, check_story, full_check, name_tokens


def has(report, *fragments):
    return any(all(f in e for f in fragments) for e in report.fehler)


def test_demo_is_variable_and_valid(story):
    assert story.variabel and story.spielerzahlen() == [6, 7, 8, 9, 10]
    r = check_story(story)
    assert r.ok, r.fehler
    assert [c.id for c in besetzung(story, 7).charaktere][-1] == "c_kim"
    assert len(besetzung(story, 8).charaktere) == 8
    b6 = besetzung(story, 6)
    assert not any(h.empfaenger == "c_kim" for h in b6.hinweise)
    assert all(i in {h.id for h in b6.hinweise} for rd in b6.runden for i in rd.hinweis_ids)
    assert story.hinweis_stufe(next(h for h in story.hinweise if h.id == "h3_r1")) == 10


def test_optional_characters_are_flexible(story):
    for c in story.charaktere:
        assert c.flexibel == (story.stufe(c.id) > 6)


def test_culprit_must_be_core(story):
    for c in story.charaktere:
        c.ist_taeter = c.id == "c_kim"
    story.aufloesung.taeter_id = "c_kim"
    assert has(check_story(story), "c_kim ist eine optionale Figur")


def test_each_count_needs_exactly_one_new_character(story):
    next(c for c in story.charaktere if c.id == "c_alex").ab_spieler = 7  # zwei Figuren ab 7, keine ab 8
    assert has(check_story(story), "Bei 7 Spielern gibt es 8 Figuren")


def test_optional_character_must_be_cleared(story):
    h = next(h for h in story.hinweise if h.id == "h3_k1")
    h.entlastet = []
    assert has(check_story(story), "Bei 7–10 Spielern", "c_kim", "durch keinen Hinweis entlastet")


def test_optional_character_needs_clue_each_round(story):
    next(h for h in story.hinweise if h.id == "h2_s1").empfaenger = "c_vroni"
    r = check_story(story)
    assert has(r, "Bei 9–10 Spielern", "c_sascha bekommt in Runde 2 keinen Hinweis")


def test_core_texts_must_not_mention_optional_characters(story):
    story.hinweise[0].text += " Kim hat alles fotografiert."
    story.aufloesung.schritte.append("Robin bestätigt das Video.")
    r = check_story(story)
    assert has(r, "Hinweis h1_01 (ab 6 Spielern)", "Kim Hofer")
    assert has(r, "Die Auflösung", "Robin Kessler")


def test_optional_may_mention_lower_but_not_higher(story):
    kim = next(h for h in story.hinweise if h.id == "h1_k1")
    kim.text += " Robin hat es auch gesehen."
    robin = next(h for h in story.hinweise if h.id == "h1_r1")
    robin.text += " Kim war dabei."
    r = check_story(story)
    assert has(r, "Hinweis h1_k1 (ab 7 Spielern)", "Robin Kessler")
    assert not has(r, "Hinweis h1_r1")


def test_core_relationship_to_optional_is_error(story):
    next(c for c in story.charaktere if c.id == "c_vroni").beziehungen.append(
        Beziehung(zu="c_sascha", beschreibung="Kennt sich von früher"))
    assert has(check_story(story), "c_vroni (ab 6 Spielern) hat eine Beziehung zu c_sascha")


def test_name_tokens():
    assert {"Kim Hofer", "Kim", "Hofer"} <= name_tokens("Kim Hofer")
    t = name_tokens("Gräfin Adelheid von Thurn-Wettstein")
    assert "Adelheid" in t and "von" not in t and "Gräfin" not in t
    assert "Konni" in name_tokens("Konrad „Konni“ Brandauer")


class FakeClient:
    def __init__(self):
        self.prompts = []

    def generate_json(self, prompt, schema, model, label="", temperature=0):
        self.prompts.append(prompt)
        return Ermittlung(taeter_id="c_moni", sicherheit=0.9, begruendung="Ohrclip")


def test_cross_check_with_smallest_and_largest_cast(story):
    c = FakeClient()
    r = full_check(story, c, "m")
    assert r.ok and len(c.prompts) == 2
    assert "Kim Hofer" not in c.prompts[0] and "Robin Kessler" in c.prompts[1]
    assert [g["spieler"] for g in r.gegenchecks] == [6, 10]
