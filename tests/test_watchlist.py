"""Watchlist alerts, offline: a fake SEC filing list stands in for EDGAR."""

from datetime import date, timedelta

import pytest

from earnings_sentiment import config, watchlist
from earnings_sentiment.edgar import Company


def _block(rows):
    keys = ("form", "accessionNumber", "filingDate", "reportDate", "primaryDocument", "items")
    return {"filings": {"recent": {k: [r[i] for r in rows] for i, k in enumerate(keys)}}}


class FakeClient:
    def __init__(self):
        d = (date.today() - timedelta(days=20)).isoformat()
        self.rows = [("10-Q", "0001-1", d, d, "q.htm", ""), ("8-K", "0001-2", d, "", "e.htm", "2.02,9.01"),
                     ("8-K", "0001-3", d, "", "o.htm", "5.07")]
        self.calls = 0

    def lookup(self, ticker):
        return Company("0000320193", ticker.upper(), "Apple Inc.")

    def get_json(self, url, ttl_hours=None):
        self.calls += 1
        return _block(self.rows)


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)


def test_adding_remembers_existing_filings_without_alerting():
    c = FakeClient()
    item = watchlist.add(c, "aapl")
    assert item["ticker"] == "AAPL" and item["last_filing"]["form"] == "10-Q"
    assert set(item["seen"]) == {"0001-1", "0001-2"}  # the non-earnings 8-K is ignored
    assert watchlist.check(c) == [] and watchlist.alerts() == []


def test_new_report_and_results_alert_and_trigger_analysis():
    c = FakeClient()
    watchlist.add(c, "AAPL")
    today = date.today().isoformat()
    c.rows = [("10-K", "0001-9", today, today, "k.htm", ""), ("8-K", "0001-8", today, "", "r.htm", "2.02")] + c.rows
    started = []
    new = watchlist.check(c, on_report=lambda item: started.append(item["ticker"]) or "job123")
    assert started == ["AAPL"]
    kinds = {a["form"]: a for a in new}
    assert kinds["10-K"]["kind"] == "report" and kinds["10-K"]["job_id"] == "job123"
    assert kinds["8-K"]["kind"] == "results" and kinds["8-K"]["job_id"] is None
    assert len(watchlist.alerts()) == 2 and not any(a["read"] for a in watchlist.alerts())
    assert watchlist.check(c) == []  # nothing new the second time
    watchlist.mark_read()
    assert all(a["read"] for a in watchlist.alerts())
    assert watchlist.load()[0]["last_filing"]["form"] == "10-K"


def test_old_filings_never_alert_and_remove_works():
    c = FakeClient()
    watchlist.add(c, "AAPL")
    old = (date.today() - timedelta(days=400)).isoformat()
    c.rows = [("10-Q", "0000-1", old, old, "x.htm", "")] + c.rows
    assert watchlist.check(c) == []
    watchlist.remove("aapl")
    assert watchlist.load() == []
