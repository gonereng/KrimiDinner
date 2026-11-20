import json
from pathlib import Path

import pytest

from krimi import themes
from krimi.render import Renderer, card_layout, crop_marks


def test_registry_complete():
    assert len(themes.THEMES) >= 10
    fonts_dir = Path(__file__).resolve().parents[1] / "templates/fonts"
    for _, file, _, _ in themes.FONT_FACES:
        assert (fonts_dir / file).exists(), file
    families = {fam for fam, *_ in themes.FONT_FACES}
    for t in themes.THEMES.values():
        assert set(t.colors) >= {"primary", "accent", "gold", "red", "ink", "paper", "cover_bg", "cover_ink"}
        first_head = t.head.split(",")[0].strip('" ')
        assert first_head in families, (t.name, first_head)
        assert t.bildstil and t.masthead and t.beschreibung


def test_normalize_and_prompt():
    assert themes.normalize("Western") == "western"
    assert themes.normalize("disco-inferno") == themes.DEFAULT_THEME
    assert '"gothic"' in themes.prompt_list()


@pytest.mark.parametrize("name", list(themes.THEMES))
def test_every_theme_renders_cards_without_overflow(tmp_path, story, name):
    story.design = name
    r = Renderer(story, tmp_path, "a4")
    assert r.theme.name == name
    slots = card_layout("a4")
    hs = [h for h in r.card_hints() if h.runde == 1][:6]
    out = r._pdf("hinweiskarten.html", tmp_path / "k.pdf", pages=[{"runde": 1, "cards": list(zip(slots, hs))}],
                 marks=crop_marks(slots))
    assert out.exists() and r.warnings == []
    assert themes.THEMES[name].ornament in r._css()


def test_render_existing_switches_and_saves_design(tmp_path, story):
    from krimi.pipeline import render_existing
    from krimi.story import save_story
    save_story(story, tmp_path / "story.json")
    render_existing(tmp_path, "a4", "gothic")
    assert json.loads((tmp_path / "story.json").read_text())["design"] == "gothic"
    render_existing(tmp_path, "letter")  # ohne Design: bleibt
    assert json.loads((tmp_path / "story.json").read_text())["design"] == "gothic"
