import json
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "geheim")
    monkeypatch.setenv("KRIMI_OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    from krimi.web.app import app
    return TestClient(app)


def login(c, pw="geheim"):
    return c.post("/login", data={"password": pw}, follow_redirects=False)


def wait(c, name, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        s = c.get(f"/api/kits/{name}").json()
        if not s.get("running"):
            return s
        time.sleep(0.3)
    raise TimeoutError


def test_requires_login(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert client.get("/api/kits/x").status_code == 401


def test_wrong_password(client):
    r = login(client, "falsch")
    assert r.status_code == 401
    assert "Falsches Passwort" in r.text


def test_no_password_configured(client, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "")
    assert "kein Passwort gesetzt" in client.get("/login").text
    assert login(client, "").status_code == 401


def test_demo_flow(client):
    assert login(client).status_code == 303
    page = client.get("/")
    assert "Kein <code>DEEPSEEK_API_KEY</code>" in page.text
    r = client.post("/demo", data={"paper": "a4"}, follow_redirects=False)
    name = r.headers["location"].split("/")[-1]
    st = wait(client, name)
    assert st["status"] == "fertig", st
    detail = client.get(f"/kits/{name}").text
    assert "Mord im Chalet Edelweiß" in detail and "bestanden" in detail
    pdf = client.get(f"/kits/{name}/files/04_hinweiskarten.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    z = client.get(f"/kits/{name}/files/kit.zip?download=1")
    assert z.headers["content-disposition"].startswith("attachment")
    # Pfad-Ausbruch
    assert client.get(f"/kits/{name}/files/../../etc/passwd").status_code == 404
    assert client.get("/kits/..%2F..%2Fetc/files/passwd").status_code == 404

    # Bearbeiten: kaputtes JSON wird abgelehnt
    r = client.post(f"/kits/{name}/edit", data={"text": "{kaputt", "danach": "speichern"})
    assert r.status_code == 422 and "Nicht gespeichert" in r.text
    # gültige Änderung + Neu-Rendern
    story = json.loads(client.get(f"/kits/{name}/files/story.json").text)
    story["titel"] = "Mord im Chalet Enzian"
    r = client.post(f"/kits/{name}/edit", data={"text": json.dumps(story), "danach": "rendern"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert wait(client, name)["status"] == "fertig"
    assert "Mord im Chalet Enzian" in client.get(f"/kits/{name}").text

    # Prüfen (ohne Gegencheck)
    client.post(f"/kits/{name}/validate", data={})
    assert wait(client, name)["status"] == "fertig"

    # Löschen
    client.post(f"/kits/{name}/delete")
    assert client.get(f"/kits/{name}").status_code == 404


def test_new_kit_without_key_fails_cleanly(client):
    login(client)
    r = client.post("/kits/new", data={"thema": "Test", "spieler": 6, "lang": "de", "paper": "a4"},
                    follow_redirects=False)
    name = r.headers["location"].split("/")[-1]
    st = wait(client, name)
    assert st["status"] == "fehler" and "DEEPSEEK_API_KEY" in st["fehler"]


def test_new_kit_rejects_bad_input(client):
    login(client)
    r = client.post("/kits/new", data={"thema": "X", "spieler": 50})
    assert r.status_code == 400


def test_retry_button_after_failure(client, monkeypatch, tmp_path):
    login(client)
    r = client.post("/kits/new", data={"thema": "Quota", "spieler": 6}, follow_redirects=False)
    name = r.headers["location"].split("/")[-1]
    assert wait(client, name)["status"] == "fehler"
    page = client.get(f"/kits/{name}").text
    assert "Wiederholen" in page and "/retry" in page

    # Retry mit simulierter KI: Gerüst lag schon vor
    from krimi import pipeline
    calls = []

    def fake_resume(kit_dir, progress=lambda m: None, **kw):
        calls.append(kit_dir.name)
        progress("Fortsetzen – bereits gesichert: Gerüst")
        return {"warnings": [], "usage": {"api_calls": 1, "cache_hits": 0, "total_tokens": 5}}

    monkeypatch.setattr(pipeline, "resume_kit", fake_resume)
    client.post(f"/kits/{name}/retry")
    st = wait(client, name)
    assert st["status"] == "fertig" and calls == [name]
    assert any("bereits gesichert" in line for line in st["log"])
    assert "/retry" not in client.get(f"/kits/{name}").text  # fertig: kein Button mehr


def test_retry_without_params_rejected(client):
    login(client)
    client.post("/demo")
    wait(client, "demo-silvester-im-schneechalet")
    assert client.post("/kits/demo-silvester-im-schneechalet/retry").status_code == 400


def test_design_picker_and_rerender(client):
    login(client)
    page = client.get("/").text
    assert 'name="design" value="auto"' in page and 'value="viktorianisch"' in page
    css = client.get("/themes.css")
    assert css.status_code == 200 and "Mountains of Christmas" in css.text
    assert client.get("/fonts/rye-latin-400-normal.woff").status_code == 200
    client.post("/demo")
    name = "demo-silvester-im-schneechalet"
    wait(client, name)
    assert 'value="chalet" checked' in client.get(f"/kits/{name}").text
    assert client.post(f"/kits/{name}/render", data={"paper": "a4", "design": "disco"}).status_code == 400
    client.post(f"/kits/{name}/render", data={"paper": "letter", "design": "riviera"})
    assert wait(client, name)["status"] == "fertig"
    detail = client.get(f"/kits/{name}").text
    assert "Design: Riviera" in detail and 'value="riviera" checked' in detail
    assert client.post("/kits/new", data={"thema": "X", "design": "disco"}).status_code == 400
