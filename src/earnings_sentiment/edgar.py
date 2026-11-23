"""Thin, polite client for the SEC EDGAR public APIs.

Docs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
Fair access policy: https://www.sec.gov/os/accessing-edgar-data
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

from . import config

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
ARCHIVE_BASE = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}"


class EdgarError(RuntimeError):
    pass


@dataclass(frozen=True)
class Filing:
    form: str
    accession: str
    filing_date: date
    report_date: date | None
    primary_document: str
    items: str
    cik: str

    @property
    def acc_nodash(self) -> str:
        return self.accession.replace("-", "")

    @property
    def folder_url(self) -> str:
        return ARCHIVE_BASE.format(cik_int=int(self.cik), acc_nodash=self.acc_nodash)

    @property
    def document_url(self) -> str:
        return f"{self.folder_url}/{self.primary_document}"

    @property
    def index_url(self) -> str:
        return f"{self.folder_url}/{self.accession}-index.htm"


@dataclass(frozen=True)
class Company:
    cik: str  # zero-padded to 10 digits
    ticker: str
    name: str


class EdgarClient:
    def __init__(self, user_agent: str | None = None, cache_dir: Path | None = None):
        ua = (user_agent or config.SEC_USER_AGENT).strip()
        if not config.valid_user_agent(ua):
            raise EdgarError(
                "SEC requires a User-Agent with your name and contact e-mail, "
                "e.g. 'Jane Doe jane@example.com'. Set SEC_USER_AGENT in .env "
                "or enter it in the dashboard sidebar."
            )
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": ua, "Accept-Encoding": "gzip, deflate"})
        self.cache_dir = Path(cache_dir or config.CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._last_request = 0.0

    # ------------------------------------------------------------------ http
    def _throttle(self) -> None:
        with self._lock:
            wait = config.SEC_MIN_INTERVAL_SECONDS - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()

    def _cache_path(self, url: str) -> Path:
        h = hashlib.sha1(url.encode()).hexdigest()[:20]
        suffix = ".json" if url.endswith(".json") else ".html"
        return self.cache_dir / "http" / f"{h}{suffix}"

    def get(self, url: str, ttl_hours: float | None = None) -> str:
        """GET with disk cache. ttl_hours=None means cache forever."""
        path = self._cache_path(url)
        if path.exists():
            age_h = (time.time() - path.stat().st_mtime) / 3600
            if ttl_hours is None or age_h < ttl_hours:
                return path.read_text(encoding="utf-8")
        last_err: Exception | None = None
        for attempt in range(4):
            self._throttle()
            try:
                resp = self.session.get(url, timeout=30)
                if resp.status_code == 404:
                    raise EdgarError(f"Not found on SEC: {url}")
                if resp.status_code in (403, 429, 503):
                    last_err = EdgarError(f"SEC returned {resp.status_code} for {url}")
                    time.sleep(1.5 * (attempt + 1))
                    continue
                resp.raise_for_status()
                text = resp.content.decode(resp.encoding or "utf-8", errors="replace")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
                return text
            except requests.RequestException as exc:
                last_err = exc
                time.sleep(1.5 * (attempt + 1))
        if path.exists():  # stale cache beats nothing
            return path.read_text(encoding="utf-8")
        raise EdgarError(f"Could not fetch {url}: {last_err}")

    def get_json(self, url: str, ttl_hours: float | None = None) -> dict:
        return json.loads(self.get(url, ttl_hours))

    # ----------------------------------------------------------- endpoints
    def company_list(self) -> list[Company]:
        data = self.get_json(TICKERS_URL, ttl_hours=24 * 7)
        out = [
            Company(cik=str(v["cik_str"]).zfill(10), ticker=v["ticker"].upper(), name=v["title"])
            for v in data.values()
        ]
        return out

    def lookup(self, ticker: str) -> Company:
        t = ticker.strip().upper().replace(".", "-")
        for c in self.company_list():
            if c.ticker == t:
                return c
        raise EdgarError(
            f"Ticker '{ticker}' not found in SEC's company list. Only companies that "
            "file with the US SEC are supported."
        )

    def submissions(self, cik: str) -> dict:
        return self.get_json(SUBMISSIONS_URL.format(cik=cik), ttl_hours=config.COMPANY_DATA_TTL_HOURS)

    def company_facts(self, cik: str) -> dict:
        return self.get_json(FACTS_URL.format(cik=cik), ttl_hours=config.COMPANY_DATA_TTL_HOURS)

    def filings(self, cik: str, forms: tuple[str, ...] = ("10-Q", "10-K", "8-K"),
                min_periodic: int = 0) -> list[Filing]:
        """Filings of the given forms, newest first.

        The submissions endpoint holds roughly the latest 1,000 filings; busy
        filers spill older ones into extra pages, which are read only when
        fewer than `min_periodic` 10-Q/10-K filings were found.
        """
        sub = self.submissions(cik)
        out = _parse_filings(sub["filings"]["recent"], cik, forms)
        pages = sub["filings"].get("files", [])
        for page in pages:
            if sum(f.form in ("10-Q", "10-K") for f in out) >= min_periodic:
                break
            older = self.get_json(f"https://data.sec.gov/submissions/{page['name']}", ttl_hours=24 * 30)
            out.extend(_parse_filings(older, cik, forms))
        out.sort(key=lambda f: f.filing_date, reverse=True)
        return out

    def filing_index(self, filing: Filing) -> list[str]:
        data = self.get_json(f"{filing.folder_url}/index.json")
        return [item["name"] for item in data["directory"]["item"]]

    def press_release_url(self, filing: Filing) -> str | None:
        """Find Exhibit 99.1 (the earnings press release) in an Item 2.02 8-K."""
        names = self.filing_index(filing)
        candidates = [
            n for n in names
            if n.lower().endswith((".htm", ".html"))
            and any(k in n.lower() for k in ("ex99", "ex-99", "exhibit99", "ex_99", "pressrelease"))
        ]
        if not candidates:
            return None
        # Prefer 99.1 over 99.2 (CFO commentary etc.)
        candidates.sort(key=lambda n: (("991" not in n.replace(".", "").replace("-", "").replace("_", "")), len(n)))
        return f"{filing.folder_url}/{candidates[0]}"


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _parse_filings(block: dict, cik: str, forms: tuple[str, ...]) -> list[Filing]:
    out: list[Filing] = []
    n = len(block.get("form", []))
    items = block.get("items") or [""] * n
    for i, form in enumerate(block.get("form", [])):
        if form not in forms:
            continue
        rd = block["reportDate"][i]
        out.append(
            Filing(
                form=form,
                accession=block["accessionNumber"][i],
                filing_date=_d(block["filingDate"][i]),
                report_date=_d(rd) if rd else None,
                primary_document=block["primaryDocument"][i],
                items=items[i] or "",
                cik=cik,
            )
        )
    return out


def match_press_release(period_end: date, eight_ks: list[Filing], max_days: int = 70) -> Filing | None:
    """Earnings 8-K (Item 2.02) filed soonest after the quarter ended."""
    window = [
        f for f in eight_ks
        if "2.02" in f.items and period_end < f.filing_date <= period_end + timedelta(days=max_days)
    ]
    return min(window, key=lambda f: f.filing_date) if window else None
