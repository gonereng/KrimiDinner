from pathlib import Path

import pytest

from krimi.story import load_story

DEMO = Path(__file__).resolve().parents[1] / "src/krimi/demo/silvester_schneechalet.json"


@pytest.fixture
def story():
    return load_story(DEMO)
