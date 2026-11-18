"""End-to-End-Test der Pipeline mit simuliertem Gemini (kein API-Key nötig)."""
import json
import zipfile
from types import SimpleNamespace

import pytest

from krimi.gemini_client import GeminiClient, GeminiError
from krimi.models import Ausarbeitung, CharakterDetails, Geruest, GeruestCharakter
from krimi.pipeline import generate_kit


def parts_from_demo(story):
    geruest = Geruest(
        titel=story.titel, untertitel=story.untertitel, design=story.design, setting=story.setting,
        opfer=story.opfer, tathergang=story.aufloesung.tathergang, fakten=story.fakten,
        zeitleiste=story.zeitleiste,
        charaktere=[GeruestCharakter(**c.model_dump(include=set(GeruestCharakter.model_fields)))
                    for c in story.charaktere])
    aus = Ausarbeitung(
        einleitung=story.einleitung, hinweise=story.hinweise, runden=story.runden,
        aufloesung=story.aufloesung, gastgeber=story.gastgeber,
        charaktere=[CharakterDetails(**c.model_dump(include=set(CharakterDetails.model_fields)))
                    for c in story.charaktere])
    return geruest, aus


class FakeModels:
    """Imitiert client.models.generate_content des google-genai-SDK."""

    def __init__(self, story, broken_first=True, fail_times=0):
        self.story = story
        self.geruest, aus = parts_from_demo(story)
        self.aus_ok = aus
        self.aus_broken = aus.model_copy(deep=True)
        if broken_first:  # Rocco wird nirgends entlastet -> Prüfung schlägt fehl
            for h in self.aus_broken.hinweise:
                if "c_rocco" in h.entlastet:
                    h.entlastet.remove("c_rocco")
        self.calls = []
        self.fail_times = fail_times

    def generate_content(self, model, contents, config):
        if self.fail_times:
            self.fail_times -= 1
            err = RuntimeError("rate limit")
            err.code = 429
            raise err
        name = config.response_schema.__name__
        self.calls.append(name)
        payload = {
            "Geruest": lambda: self.geruest.model_dump_json(),
            "Ausarbeitung": lambda: self.aus_broken.model_dump_json(),
            "Story": lambda: self.story.model_dump_json(),
            "Ermittlung": lambda: json.dumps({"taeter_id": "c_moni", "sicherheit": 0.93,
                                              "begruendung": "Ohrclip, Tipp-Ex, leere Küche",
                                              "alternative_verdaechtige": []}),
        }[name]()
        usage = SimpleNamespace(prompt_token_count=1000, candidates_token_count=500, total_token_count=1500)
        return SimpleNamespace(text=payload, usage_metadata=usage)


def make_client(tmp_path, models, cache=True):
    c = GeminiClient(api_key="test", use_cache=cache, cache_dir=tmp_path / "cache", sleep=lambda s: None)
    c._client = SimpleNamespace(models=models)
    return c


def test_full_pipeline_with_repair_and_cache(tmp_path, story):
    models = FakeModels(story)
    client = make_client(tmp_path, models)
    msgs = []
    res = generate_kit("Silvester im Schneechalet", 6, "de", "a4", client=client,
                       kit_dir=tmp_path / "kit", progress=msgs.append)
    # Gerüst, Ausarbeitung, (Prüfung scheitert -> kein Gegencheck), Korrektur, Gegencheck
    assert models.calls == ["Geruest", "Ausarbeitung", "Story", "Ermittlung"]
    assert any("Korrektur 1/3" in m for m in msgs)
    kit = tmp_path / "kit"
    for f in ["story.json", "report.json", "usage.json", "01_gastgeber.pdf", "04_hinweiskarten.pdf",
              "06_aufloesung.pdf", "08_notizblaetter.pdf", "kit.zip"]:
        assert (kit / f).exists(), f
    report = json.loads((kit / "report.json").read_text())
    assert report["ok"] and report["ermittlung"]["taeter_id"] == "c_moni"
    assert res["usage"]["api_calls"] == 4 and res["usage"]["total_tokens"] == 6000
    with zipfile.ZipFile(kit / "kit.zip") as z:
        assert "05_beweisstuecke.pdf" in z.namelist()
    assert res["warnings"] == []

    # zweiter Lauf: alles aus dem Cache, keine API-Aufrufe
    client2 = make_client(tmp_path, models)
    res2 = generate_kit("Silvester im Schneechalet", 6, "de", "a4", client=client2,
                        kit_dir=tmp_path / "kit2", render=False)
    assert models.calls == ["Geruest", "Ausarbeitung", "Story", "Ermittlung"]
    assert res2["usage"]["api_calls"] == 0 and res2["usage"]["cache_hits"] == 4

    # --no-cache: wieder echte Aufrufe
    client3 = make_client(tmp_path, models, cache=False)
    generate_kit("Silvester im Schneechalet", 6, "de", client=client3, kit_dir=tmp_path / "kit3", render=False)
    assert client3.usage.api_calls == 4


def test_pipeline_gives_up_after_three_repairs(tmp_path, story):
    from krimi.pipeline import KitFailed
    models = FakeModels(story)
    broken = models.aus_broken
    models.story = story.model_copy(deep=True)
    for h in models.story.hinweise:  # auch die "Korrektur" bleibt kaputt
        h.entlastet = [c for c in h.entlastet if c != "c_rocco"]
    client = make_client(tmp_path, models)
    with pytest.raises(KitFailed) as exc:
        generate_kit("X", 6, client=client, kit_dir=tmp_path / "kit")
    assert "c_rocco" in str(exc.value)
    assert models.calls.count("Story") == 3
    assert broken is models.aus_broken


def test_retry_on_rate_limit(tmp_path, story):
    models = FakeModels(story, broken_first=False, fail_times=2)
    client = make_client(tmp_path, models)
    generate_kit("Y", 6, client=client, kit_dir=tmp_path / "kit", render=False)
    assert models.calls[0] == "Geruest"


def test_missing_key_is_clear_error(tmp_path):
    c = GeminiClient(api_key="", cache_dir=tmp_path)
    with pytest.raises(GeminiError, match="GEMINI_API_KEY"):
        c.generate_json("hallo", Geruest, "m")
