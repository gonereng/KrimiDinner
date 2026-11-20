"""DeepSeek-Backend gegen einen simulierten HTTP-Endpunkt (kein Netz, kein Key nötig)."""
import json

import httpx
import pytest

from krimi.llm_client import DeepSeekBackend, LLMClient, LLMError, QuotaError, extract_json
from krimi.models import Ermittlung

GOOD = {"taeter_id": "c_moni", "sicherheit": 0.9, "begruendung": "Ohrclip", "alternative_verdaechtige": []}


def make(tmp_path, handler, **kw):
    backend = DeepSeekBackend("sk-test", "https://api.deepseek.test", max_tokens=1234, **kw)
    backend._http = httpx.Client(transport=httpx.MockTransport(handler))
    return LLMClient(backend=backend, cache_dir=tmp_path, sleep=lambda s: None)


def reply(content, finish="stop", status=200):
    return httpx.Response(status, json={
        "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": finish}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}})


def test_request_format_and_parsing(tmp_path):
    seen = []

    def handler(req):
        seen.append(req)
        return reply("```json\n" + json.dumps(GOOD) + "\n```")  # Markdown-Zaun wird entfernt

    c = make(tmp_path, handler, thinking="disabled")
    erm = c.generate_json("Wer war es?", Ermittlung, "deepseek-v4-flash", temperature=0.2)
    assert erm.taeter_id == "c_moni"
    req = seen[0]
    assert str(req.url) == "https://api.deepseek.test/chat/completions"
    assert req.headers["authorization"] == "Bearer sk-test"
    body = json.loads(req.content)
    assert body["model"] == "deepseek-v4-flash" and body["max_tokens"] == 1234
    assert body["response_format"] == {"type": "json_object"}
    assert body["thinking"] == {"type": "disabled"}
    assert "taeter_id" in body["messages"][0]["content"]  # Schema steht im System-Prompt
    assert body["messages"][1]["content"] == "Wer war es?"
    assert c.usage.total_tokens == 150

    # zweiter Aufruf: Cache, kein HTTP
    c2 = make(tmp_path, handler)
    c2.generate_json("Wer war es?", Ermittlung, "deepseek-v4-flash", temperature=0.2)
    assert len(seen) == 1 and c2.usage.cache_hits == 1


def test_invalid_json_gets_fixed(tmp_path):
    answers = iter([reply('{"taeter_id": "c_moni"}'), reply(json.dumps(GOOD))])
    prompts = []

    def handler(req):
        prompts.append(json.loads(req.content)["messages"][1]["content"])
        return next(answers)

    c = make(tmp_path, handler)
    assert c.generate_json("Frage", Ermittlung, "m").sicherheit == 0.9
    assert "vorige Antwort war ungültig" in prompts[1] and "sicherheit" in prompts[1]
    assert c.usage.api_calls == 1 and c.usage.total_tokens == 300


def test_gives_up_after_fixes(tmp_path):
    c = make(tmp_path, lambda req: reply("kein json"))
    with pytest.raises(LLMError, match="Nachbesserungen"):
        c.generate_json("Frage", Ermittlung, "m")


def test_no_balance_is_quota_error_without_retry(tmp_path):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(402, json={"error": {"message": "Insufficient Balance"}})

    with pytest.raises(QuotaError, match="Guthaben"):
        make(tmp_path, handler).generate_json("x", Ermittlung, "m")
    assert len(calls) == 1


def test_rate_limit_retries_then_succeeds(tmp_path):
    answers = iter([httpx.Response(429, json={"error": {"message": "Rate limit"}}),
                    httpx.Response(503, text="busy"), reply(json.dumps(GOOD))])
    c = make(tmp_path, lambda req: next(answers))
    assert c.generate_json("x", Ermittlung, "m").taeter_id == "c_moni"


def test_truncated_answer_is_clear_error(tmp_path):
    c = make(tmp_path, lambda req: reply('{"taeter_id": "c_mo', finish="length"))
    with pytest.raises(LLMError, match="DEEPSEEK_MAX_TOKENS"):
        c.generate_json("x", Ermittlung, "m")


def test_extract_json():
    assert extract_json('Hier: {"a": 1} fertig') == '{"a": 1}'
    assert extract_json('```json\n{"a": {"b": 2}}\n```') == '{"a": {"b": 2}}'


def test_settings_default_to_deepseek(monkeypatch):
    from krimi.config import get_settings
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-1")
    monkeypatch.delenv("DEEPSEEK_TEXT_MODEL", raising=False)
    s = get_settings()
    assert s.provider == "deepseek" and s.api_key == "sk-1" and s.text_model == "deepseek-v4-flash"
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "g-1")
    assert get_settings().api_key == "g-1"
