"""Watchlist: notice new SEC filings for companies the user follows.

The desktop engine checks while the app is open (on launch, then every 30
minutes). A new 10-Q/10-K is a "report" event and is analysed automatically;
a new earnings 8-K (Item 2.02) is a "results" event: the press release is out,
and the full analysis follows when the 10-Q/10-K is filed.

Everything is stored locally in the data folder (watchlist.json, alerts.json).
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import date, timedelta
from typing import Callable

from . import config
from .edgar import SUBMISSIONS_URL, EdgarClient, Filing, _parse_filings

CHECK_EVERY_SECONDS = 30 * 60
RECENT_DAYS = 120          # only filings this recent can raise an alert
FRESH_HOURS = 0.25         # re-download SEC's filing list if older than 15 minutes
MAX_ALERTS = 100

_lock = threading.RLock()


def _path(name: str):
    return config.DATA_DIR / name


def _read(name: str) -> list[dict]:
    try:
        return json.loads(_path(name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _write(name: str, data: list[dict]) -> None:
    p = _path(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")
    tmp.replace(p)


def load() -> list[dict]:
    with _lock:
        return _read("watchlist.json")


def alerts() -> list[dict]:
    with _lock:
        return _read("alerts.json")


def _relevant(client: EdgarClient, cik: str, max_age_hours: float) -> list[Filing]:
    sub = client.get_json(SUBMISSIONS_URL.format(cik=cik), ttl_hours=max_age_hours)
    cutoff = date.today() - timedelta(days=RECENT_DAYS)
    out = [f for f in _parse_filings(sub["filings"]["recent"], cik, ("10-Q", "10-K", "8-K"))
           if f.filing_date >= cutoff and (f.form != "8-K" or "2.02" in f.items)]
    return sorted(out, key=lambda f: f.filing_date, reverse=True)


def _describe(f: Filing) -> dict:
    return {"form": f.form, "accession": f.accession, "filed": f.filing_date.isoformat(),
            "period": f.report_date.isoformat() if f.report_date else None, "url": f.document_url,
            "kind": "results" if f.form == "8-K" else "report"}


def add(client: EdgarClient, ticker: str) -> dict:
    """Follow a company. Filings already out are remembered, so only later ones alert."""
    company = client.lookup(ticker)
    with _lock:
        items = _read("watchlist.json")
        if any(i["ticker"] == company.ticker for i in items):
            return next(i for i in items if i["ticker"] == company.ticker)
    recent = _relevant(client, company.cik, FRESH_HOURS)
    item = {"ticker": company.ticker, "name": company.name, "cik": company.cik, "added_at": time.time(),
            "seen": [f.accession for f in recent], "last_checked": time.time(),
            "last_filing": _describe(recent[0]) if recent else None}
    with _lock:
        items = [i for i in _read("watchlist.json") if i["ticker"] != company.ticker]
        items.append(item)
        _write("watchlist.json", items)
    return item


def remove(ticker: str) -> None:
    with _lock:
        _write("watchlist.json", [i for i in _read("watchlist.json") if i["ticker"] != ticker.upper()])


def check(client: EdgarClient, on_report: Callable[[dict], str | None] | None = None,
          max_age_hours: float = FRESH_HOURS) -> list[dict]:
    """Look for new filings. Returns the new alerts (also saved to alerts.json).

    on_report(item) is called for each company with a new 10-Q/10-K; it may start an
    analysis and return its job id, which is stored on the alert.
    """
    new_alerts: list[dict] = []
    for item in load():
        try:
            recent = _relevant(client, item["cik"], max_age_hours)
        except Exception as exc:  # one company failing must not stop the rest
            item["error"] = str(exc)
            _save_item(item)
            continue
        seen = set(item.get("seen", []))
        fresh = [f for f in recent if f.accession not in seen]
        item.pop("error", None)
        item["last_checked"] = time.time()
        if recent:
            item["last_filing"] = _describe(recent[0])
        item["seen"] = ([f.accession for f in fresh] + item.get("seen", []))[:40]
        job_id = None
        if any(f.form in ("10-Q", "10-K") for f in fresh) and on_report:
            job_id = on_report(item)
        for f in reversed(fresh):  # oldest first, so the newest ends up on top
            a = _describe(f) | {"id": uuid.uuid4().hex[:10], "ticker": item["ticker"], "name": item["name"],
                                "created_at": time.time(), "read": False,
                                "job_id": job_id if f.form in ("10-Q", "10-K") else None}
            new_alerts.insert(0, a)
        _save_item(item)
    if new_alerts:
        with _lock:
            _write("alerts.json", (new_alerts + _read("alerts.json"))[:MAX_ALERTS])
    return new_alerts


def _save_item(item: dict) -> None:
    with _lock:
        items = _read("watchlist.json")
        items = [item if i["ticker"] == item["ticker"] else i for i in items]
        _write("watchlist.json", items)


def mark_read(alert_id: str | None = None) -> None:
    with _lock:
        data = _read("alerts.json")
        for a in data:
            if alert_id is None or a["id"] == alert_id:
                a["read"] = True
        _write("alerts.json", data)


def clear_alerts() -> None:
    with _lock:
        _write("alerts.json", [])


class Checker:
    """Background loop: check on start, then every CHECK_EVERY_SECONDS while the engine runs."""

    def __init__(self, make_client: Callable[[], EdgarClient | None], on_report: Callable[[dict], str | None]):
        self.make_client, self.on_report = make_client, on_report
        self.wake = threading.Event()
        self.running = False
        self.last_run: float | None = None
        self.last_error = ""

    def start(self) -> None:
        threading.Thread(target=self._loop, daemon=True, name="watchlist").start()

    def run_now(self) -> list[dict]:
        client = self.make_client()
        if client is None:
            return []
        self.running = True
        try:
            out = check(client, self.on_report, max_age_hours=0)
            self.last_error = ""
            return out
        except Exception as exc:
            self.last_error = str(exc)
            return []
        finally:
            self.running, self.last_run = False, time.time()

    def _loop(self) -> None:
        time.sleep(5)  # let the app finish starting
        while True:
            if load():
                self.run_now()
            self.wake.wait(CHECK_EVERY_SECONDS)
            self.wake.clear()
