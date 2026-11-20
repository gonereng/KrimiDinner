"""End-to-End-Test der Pipeline mit simulierter KI (kein API-Key nötig)."""
import json
import zipfile
from types import SimpleNamespace

import pytest

from krimi.llm_client import LLMClient, LLMError
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
    """Simuliertes KI-Backend (gleiche Schnittstelle wie DeepSeekBackend/GeminiBackend)."""
    name = "fake"

    def __init__(self, story, broken_first=True, fail_times=0, quota_on=None):
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
        self.quota_on = quota_on  # Schema-Name, bei dem das Tageskontingent "erschöpft" ist

    def complete_json(self, prompt, schema, model, temperature):
        if self.fail_times:
            self.fail_times -= 1
            err = RuntimeError("rate limit")
            err.code = 429
            raise err
        name = schema.__name__
        if name == self.quota_on:
            err = RuntimeError("429 RESOURCE_EXHAUSTED: Quota exceeded for GenerateRequestsPerDay")
            err.code = 429
            raise err
        self.calls.append(name)
        payload = {
            "Geruest": lambda: self.geruest.model_dump_json(),
            "Ausarbeitung": lambda: self.aus_broken.model_dump_json(),
            "Story": lambda: self.story.model_dump_json(),
            "Ermittlung": lambda: json.dumps({"taeter_id": "c_moni", "sicherheit": 0.93,
                                              "begruendung": "Ohrclip, Tipp-Ex, leere Küche",
                                              "alternative_verdaechtige": []}),
        }[name]()
        return payload, {"prompt": 1000, "output": 500, "total": 1500}


def make_client(tmp_path, models, cache=True):
    return LLMClient(backend=models, use_cache=cache, cache_dir=tmp_path / "cache", sleep=lambda s: None)


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


@pytest.mark.parametrize("provider", ["deepseek", "gemini"])
def test_missing_key_is_clear_error(tmp_path, provider):
    c = LLMClient(provider=provider, api_key="", cache_dir=tmp_path)
    with pytest.raises(LLMError, match=f"{provider.upper()}_API_KEY"):
        c.generate_json("hallo", Geruest, "m")


def test_resume_after_quota_exhausted(tmp_path, story):
    from krimi.llm_client import QuotaError
    from krimi.pipeline import Zwischenstand, resume_kit
    models = FakeModels(story, quota_on="Ausarbeitung")
    sleeps = []
    client = LLMClient(backend=models, use_cache=False, cache_dir=tmp_path / "c", sleep=sleeps.append)
    kit = tmp_path / "kit"
    with pytest.raises(QuotaError, match="Fortschritt ist gespeichert"):
        generate_kit("Silvester", 6, client=client, kit_dir=kit, use_cache=False)
    assert sleeps == []  # Tageslimit: kein sinnloses Warten
    assert models.calls == ["Geruest"]
    assert Zwischenstand(kit).summary() == ["Gerüst"]

    # Später: Kontingent wieder da, aber Gerüst steht nur noch der Kontingent beim Prüfen im Weg
    models.quota_on = "Ermittlung"
    with pytest.raises(QuotaError):
        resume_kit(kit, client=client, use_cache=False)
    assert models.calls == ["Geruest", "Ausarbeitung", "Story"]  # Gerüst NICHT erneut
    zs = Zwischenstand(kit)
    assert zs.data["korrekturen"] == 1 and "Story + 1 Korrektur(en)" in zs.summary()

    # Nochmal: nur noch der Gegencheck fehlt, die Korrektur wird nicht wiederholt
    models.quota_on = None
    msgs = []
    vorher = client.usage.api_calls
    res = resume_kit(kit, client=client, use_cache=False, progress=msgs.append)
    assert models.calls == ["Geruest", "Ausarbeitung", "Story", "Ermittlung"]
    assert any("Fortsetzen – bereits gesichert" in m for m in msgs)
    assert (kit / "kit.zip").exists() and res["usage"]["api_calls"] - vorher == 1

    # Ein fertiges Kit erneut fortsetzen kostet nichts mehr
    res = resume_kit(kit, client=client, use_cache=False)
    assert models.calls[-1] == "Ermittlung" and len(models.calls) == 4


def test_new_run_discards_old_checkpoints(tmp_path, story):
    from krimi.pipeline import Zwischenstand
    models = FakeModels(story, broken_first=False)
    client = make_client(tmp_path, models, cache=False)
    generate_kit("A", 6, client=client, kit_dir=tmp_path / "kit", render=False)
    generate_kit("A", 6, client=client, kit_dir=tmp_path / "kit", render=False)  # ohne resume: neu
    assert models.calls.count("Geruest") == 2
    assert Zwischenstand(tmp_path / "kit").data["pruefung_ok"] is True


def test_short_rate_limit_becomes_quota_error_after_retries(tmp_path, story):
    from krimi.llm_client import QuotaError
    models = FakeModels(story, fail_times=99)
    client = make_client(tmp_path, models)
    with pytest.raises(QuotaError):
        generate_kit("Z", 6, client=client, kit_dir=tmp_path / "kit", render=False)
