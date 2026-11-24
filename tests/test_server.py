"""Engine API tests (offline: no SEC calls)."""

import pytest
from fastapi.testclient import TestClient

from earnings_sentiment import config, models, server


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(server, "TOKEN", "secret-token")
    monkeypatch.setattr(models, "fetch_manifest", lambda force=False: [])
    return TestClient(server.app)


H = {"X-EP-Token": "secret-token"}


def test_health_needs_no_token(client):
    assert client.get("/api/health").json()["ok"] is True


def test_token_is_required(client):
    assert client.get("/api/settings").status_code == 401
    assert client.get("/api/settings", headers={"X-EP-Token": "wrong"}).status_code == 401
    assert client.get("/api/settings", headers=H).status_code == 200


def test_settings_validate_sec_identity(client):
    assert client.put("/api/settings", json={"sec_user_agent": "just-an-email@example.com"}, headers=H).status_code == 400
    r = client.put("/api/settings", json={"sec_user_agent": "Jane Doe jane@example.com", "theme": "dark"}, headers=H)
    assert r.status_code == 200
    body = r.json()
    assert body["sec_user_agent_valid"] and body["theme"] == "dark"


def test_analysis_requires_sec_identity(client):
    r = client.post("/api/analyses", json={"ticker": "AAPL"}, headers=H)
    assert r.status_code == 400 and "e-mail" in r.json()["detail"]


def test_models_listing_and_errors(client):
    body = client.get("/api/models", headers=H).json()
    ids = [m["id"] for m in body["models"]]
    assert ids[:3] == ["finbert", "finbert-tone", "distilroberta-fin"]
    assert body["active"] is None and not any(m["installed"] for m in body["models"])
    r = client.post("/api/models/finbert/activate", headers=H)
    assert r.status_code == 400  # not downloaded yet


def test_unknown_analysis_is_404(client):
    assert client.get("/api/analyses/nope", headers=H).status_code == 404


def test_guide_has_charts_and_glossary(client):
    g = client.get("/api/guide", headers=H).json()
    assert "tone" in g["charts"] and "TTM" in g["glossary"]


def test_identity_is_split_into_name_and_email(client):
    r = client.put("/api/settings", json={"sec_name": "Jane  Doe", "sec_email": "jane@example.com"}, headers=H)
    body = r.json()
    assert r.status_code == 200 and body["sec_user_agent"] == "Jane Doe jane@example.com"
    assert body["sec_name"] == "Jane Doe" and body["sec_email"] == "jane@example.com" and body["sec_user_agent_valid"]
    assert client.put("/api/settings", json={"sec_name": "Jane", "sec_email": "not-an-email"}, headers=H).status_code == 400
    assert client.put("/api/settings", json={"sec_name": "", "sec_email": "jane@example.com"}, headers=H).status_code == 400


def test_storage_sizes_clear_and_move(client, tmp_path):
    (tmp_path / "cache" / "http").mkdir(parents=True)
    (tmp_path / "cache" / "http" / "a.json").write_text("x" * 100)
    (tmp_path / "models" / "finbert").mkdir(parents=True)
    (tmp_path / "models" / "finbert" / "model.onnx").write_text("y" * 50)
    (tmp_path / "settings.json").write_text("{}")
    st = client.get("/api/storage", headers=H).json()
    assert st["sizes"]["filings"] == 100 and st["sizes"]["models"] == 50

    target = tmp_path.parent / (tmp_path.name + "-elsewhere")
    target.mkdir()
    r = client.post("/api/storage/move", json={"target": str(target)}, headers=H).json()
    dest = target / "EarningsPulse"
    assert r["data_dir"] == str(dest) and r["moved"]
    assert (dest / "models" / "finbert" / "model.onnx").exists() and (dest / "cache" / "http" / "a.json").exists()
    assert not (tmp_path / "models").exists()  # old copy removed

    assert client.post("/api/storage/move", json={"target": "/no/such/folder"}, headers=H).status_code == 400


def test_clear_cache_keeps_models(client, tmp_path):
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "f").write_text("z")
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "m").write_text("m")
    client.post("/api/storage/clear-cache", headers=H)
    assert not (tmp_path / "cache").exists() and (tmp_path / "models" / "m").exists()
