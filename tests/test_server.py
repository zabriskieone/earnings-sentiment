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


def test_changes_endpoint_compares_filings_offline(client, monkeypatch):
    from datetime import date

    from earnings_sentiment import changes
    from earnings_sentiment.analysis import Analysis, QuarterResult
    from earnings_sentiment.edgar import Company, Filing
    from earnings_sentiment.periods import FiscalQuarter

    def filing(acc, form, day):
        return Filing(form, acc, day, day, f"{acc}.htm", "", "320193")

    qs = [QuarterResult(FiscalQuarter(y, 1), date(y - 1, 12, 28), filing(f"000-{y}", "10-Q", date(y, 1, 30)), None, None)
          for y in (2025, 2026)]
    a = Analysis(Company("0000320193", "AAPL", "Apple Inc."), "0925", None, qs, False, "test", "now")
    texts = {
        "000-2025.htm": ["Net sales rose 5% on strong iPhone demand across every region we serve.",
                         "Gross margin was hurt by the weaker yen during the quarter overall.",
                         "The Company repurchased shares under its existing buyback program."],
        "000-2026.htm": ["Net sales rose 9% on strong iPhone demand across every region we serve.",
                         "The Company is experiencing supply constraints and rising memory costs.",
                         "The Company repurchased shares under its existing buyback programs."],
    }
    monkeypatch.setattr(changes, "_section_sentences", lambda url, form, sec, ua: tuple(texts[url.rsplit("/", 1)[1]]))
    job = server.Job(server.AnalysisIn(ticker="AAPL"))
    job.status, job.analysis = "done", a
    server._jobs[job.id] = job
    monkeypatch.setattr(server, "sec_user_agent", lambda: "Jane Doe jane@example.com")

    body = client.get(f"/api/analyses/{job.id}/changes?quarter=FY2026 Q1&vs=yoy&section=mdna", headers=H).json()
    assert body["available"] and body["old_filing"]["label"] == "FY2025 Q1"
    assert body["counts"]["unchanged"] == 1 and body["counts"]["added"] == 1 and body["counts"]["removed"] == 1
    new = body["added"][0]
    assert "constraints" in new["text"] and "constraining" in new["tags"] and new["notable"]
    assert body["reworded"][0]["minor"] is True  # "program" -> "programs"
    assert [o["quarter"] for o in body["options"]] == ["FY2026 Q1", "FY2025 Q1"]

    prev = client.get(f"/api/analyses/{job.id}/changes?quarter=FY2026 Q1&vs=prev", headers=H).json()
    assert prev["available"] is False and "more quarters" in prev["note"]
    assert client.get(f"/api/analyses/{job.id}/changes?quarter=FY2019 Q1", headers=H).status_code == 404


def test_watchlist_endpoints_need_identity_and_list_alerts(client):
    assert client.post("/api/watchlist", json={"ticker": "AAPL"}, headers=H).status_code == 400
    body = client.get("/api/watchlist", headers=H).json()
    assert body["items"] == [] and body["unread"] == 0
    assert client.get("/api/alerts", headers=H).json() == []
    assert client.post("/api/alerts/read", json={}, headers=H).json()["ok"]
