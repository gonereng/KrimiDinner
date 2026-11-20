from krimi.models import Ermittlung, ZeitEintrag
from krimi.validate import check_story, full_check, to_minutes


def has(report, fragment):
    return any(fragment in f for f in report.fehler)


def test_demo_story_is_valid(story):
    r = check_story(story)
    assert r.ok, r.fehler


def test_exactly_one_culprit(story):
    story.charaktere[0].ist_taeter = True
    assert has(check_story(story), "genau einen Täter")
    for c in story.charaktere:
        c.ist_taeter = False
    assert has(check_story(story), "genau einen Täter")


def test_aufloesung_must_match_culprit(story):
    story.aufloesung.taeter_id = "c_vroni"
    assert has(check_story(story), "Auflösung nennt")


def test_missing_motive(story):
    story.charaktere[1].motiv = " "
    assert has(check_story(story), "kein(e) motiv")


def test_unknown_references(story):
    story.hinweise[0].fakten.append("f_gibtsnicht")
    story.hinweise[1].empfaenger = "c_niemand"
    story.hinweise[2].belastet.append("c_phantom")
    r = check_story(story)
    assert has(r, "unbekannter Fakt 'f_gibtsnicht'")
    assert has(r, "unbekannter Empfänger 'c_niemand'")
    assert has(r, "unbekannter Charakter 'c_phantom'")


def test_innocent_must_be_cleared(story):
    for h in story.hinweise:
        if "c_rocco" in h.entlastet:
            h.entlastet.remove("c_rocco")
    assert has(check_story(story), "c_rocco (Rocco Bellini) wird durch keinen Hinweis entlastet")


def test_culprit_needs_three_independent_clues(story):
    keep = 0
    for h in story.hinweise:
        if "c_moni" in h.belastet:
            keep += 1
            if keep > 2:
                h.belastet.remove("c_moni")
    assert has(check_story(story), "nur durch 2 unabhängige Hinweise")


def test_same_fact_is_not_independent(story):
    belastend = [h for h in story.hinweise if "c_moni" in h.belastet]
    for h in belastend:
        h.fakten = ["f_ohrclip"]
    assert has(check_story(story), "nur durch 1 unabhängige Hinweise")


def test_culprit_must_not_be_cleared(story):
    story.hinweise[0].entlastet.append("c_moni")
    assert has(check_story(story), "Der Täter c_moni wird durch Hinweis")


def test_every_player_needs_clue_per_round(story):
    for h in story.hinweise:
        if h.empfaenger == "c_hagen" and h.runde == 2:
            h.empfaenger = "c_vroni"
    assert has(check_story(story), "c_hagen bekommt in Runde 2 keinen Hinweis")


def test_round_assignment(story):
    story.runden[0].hinweis_ids.remove("h1_01")
    story.runden[1].hinweis_ids.append("h1_01")
    r = check_story(story)
    assert has(r, "der aber zu Runde 1 gehört")


def test_timeline_conflict(story):
    story.zeitleiste.append(ZeitEintrag(von="23:40", bis="23:45", ort="Küche",
                                        personen=["c_rocco"], ereignis="Snack"))
    assert has(check_story(story), "c_rocco ist gleichzeitig")


def test_timeline_over_midnight():
    assert to_minutes("00:05") > to_minutes("23:58")
    assert to_minutes("19:30") < to_minutes("23:00")


def test_timeline_adjacent_slots_ok(story):
    # 23:33-23:51 Terrasse und 23:51-23:58 Speisesaal grenzen nur aneinander
    assert check_story(story).ok


def test_invalid_time(story):
    story.zeitleiste[0].von = "25:99"
    assert has(check_story(story), "ungültige Uhrzeit")


class FakeClient:
    def __init__(self, antwort):
        self.antwort = antwort
        self.prompts = []

    def generate_json(self, prompt, schema, model, label="", temperature=0):
        self.prompts.append(prompt)
        return self.antwort


def test_cross_check_correct(story):
    c = FakeClient(Ermittlung(taeter_id="c_moni", sicherheit=0.95, begruendung="Ohrclip"))
    r = full_check(story, c, "m")
    assert r.ok
    # Der Prüfer bekommt die Lösung nicht zu sehen
    assert "ist_taeter" not in c.prompts[0]
    assert story.aufloesung.tathergang[:40] not in c.prompts[0]


def test_cross_check_wrong_culprit(story):
    c = FakeClient(Ermittlung(taeter_id="c_rocco", sicherheit=0.9, begruendung="Gage"))
    assert has(full_check(story, c, "m"), "Mehrdeutig")


def test_cross_check_unsure(story):
    c = FakeClient(Ermittlung(taeter_id="c_moni", sicherheit=0.4, begruendung="?"))
    assert has(full_check(story, c, "m"), "unsicher")


def _lock(story):
    return next(h for h in story.hinweise if h.raetsel and h.raetsel.typ == "zahlenschloss")


def test_lock_hint_must_not_reveal_code(story):
    h = _lock(story)
    h.raetsel.ziffern[0].herkunft = "Erste Ziffer des Codes 735"
    assert has(check_story(story), "verrät die Lösung")


def test_lock_hint_must_not_contain_digit(story):
    h = _lock(story)
    h.raetsel.ziffern[1].herkunft = "Gämsen im Wappen (3)"
    assert has(check_story(story), "verrät die Lösung")


def test_lock_hint_may_contain_unrelated_numbers(story):
    # "Startnummer bei der Abfahrt 1976" -> Ziffer 5, 1976 verrät nichts
    assert check_story(story).ok


def test_lock_content_must_be_full_text(story):
    _lock(story).raetsel.klartext = "Kaufvertrag für das Gasthaus und eine Kündigung"
    assert has(check_story(story), "nur eine Kurzbeschreibung")
