"""End-to-end analysis for one ticker: filings -> financials -> sentiment -> health."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Callable

import pandas as pd

from . import config
from .edgar import Company, EdgarClient, EdgarError, Filing, match_press_release
from .financials import quarterly_table
from .health import health_band, piotroski, scorecard
from .periods import FiscalQuarter, fiscal_quarter
from .sentiment import FinBertUnavailable, finbert_available, load_lm_dictionary, score_document
from .textextract import clean_press_release, extract_section, html_to_text

ProgressFn = Callable[[float, str], None]

SECTIONS = {
    "mdna": "MD&A (10-Q/10-K)",
    "risk": "Risk factors (10-Q/10-K)",
    "press": "Earnings press release (8-K Ex. 99.1)",
}


@dataclass
class QuarterResult:
    fq: FiscalQuarter
    period_end: date
    filing: Filing
    press_filing: Filing | None
    press_url: str | None
    docs: dict[str, dict] = field(default_factory=dict)
    health: dict | None = None
    fscore: dict | None = None


@dataclass
class Analysis:
    company: Company
    fiscal_year_end: str
    financials: pd.DataFrame
    quarters: list[QuarterResult]
    used_finbert: bool  # True when a neural model (FinBERT or another) scored the text
    dictionary_source: str
    generated_at: str
    warnings: list[str] = field(default_factory=list)
    model_id: str | None = None

    @property
    def model_name(self) -> str:
        """Display name of the tone method, e.g. 'FinBERT' or 'Loughran-McDonald'."""
        from .models import display_name

        return display_name(self.model_id) if self.used_finbert else "Loughran-McDonald"

    @property
    def latest(self) -> QuarterResult:
        return self.quarters[-1]

    def quarter(self, fq: FiscalQuarter) -> QuarterResult | None:
        return next((q for q in self.quarters if q.fq == fq), None)

    # ---------------------------------------------------------------- tables
    def sentiment_table(self) -> pd.DataFrame:
        rows = []
        for q in self.quarters:
            row: dict = {"label": q.fq.label, "fiscal_quarter": q.fq, "period_end": q.period_end, "form": q.filing.form}
            for sec, d in q.docs.items():
                lm = d["lm"]
                row[f"{sec}_lm_tone"] = lm.get("net_tone")
                row[f"{sec}_neg_pct"] = lm.get("negative_pct")
                row[f"{sec}_pos_pct"] = lm.get("positive_pct")
                row[f"{sec}_unc_pct"] = lm.get("uncertainty_pct")
                row[f"{sec}_lit_pct"] = lm.get("litigious_pct")
                row[f"{sec}_words"] = lm.get("words")
                if d.get("finbert"):
                    row[f"{sec}_finbert"] = d["finbert"]["score"]
                    row[f"{sec}_fb_pos"] = d["finbert"]["positive_share"]
                    row[f"{sec}_fb_neg"] = d["finbert"]["negative_share"]
            row["tone_index"] = tone_index(q.docs, self.used_finbert)
            rows.append(row)
        df = pd.DataFrame(rows)
        return df.set_index("label", drop=False) if not df.empty else df

    def health_table(self) -> pd.DataFrame:
        rows = []
        for q in self.quarters:
            if not q.health:
                continue
            row = {"label": q.fq.label, "fiscal_quarter": q.fq, "overall": q.health["overall"]}
            row.update(q.health["pillars"])
            row["fscore"] = q.fscore["score"] if q.fscore else None
            row["fscore_available"] = q.fscore["available"] if q.fscore else None
            rows.append(row)
        df = pd.DataFrame(rows)
        return df.set_index("label", drop=False) if not df.empty else df

    def sources(self) -> list[dict]:
        out = [
            {"what": "XBRL company facts (all financial figures)",
             "url": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{self.company.cik}.json"},
            {"what": "Filing history", "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={self.company.cik}&type=10-&dateb=&owner=include&count=40"},
        ]
        for q in reversed(self.quarters):
            out.append({"what": f"{q.fq.label} {q.filing.form} filed {q.filing.filing_date}", "url": q.filing.document_url})
            if q.press_url and q.press_filing:
                out.append({"what": f"{q.fq.label} earnings press release (8-K) filed {q.press_filing.filing_date}", "url": q.press_url})
        return out

    def to_summary(self) -> dict:
        """JSON-serialisable summary (used for snapshots committed to git)."""
        fin_cols = ["period_end", "revenue", "gross_profit", "operating_income", "net_income", "eps_diluted",
                    "ocf", "capex", "fcf", "cash", "total_debt", "net_cash", "gross_margin", "operating_margin",
                    "net_margin", "revenue_yoy", "eps_diluted_yoy", "current_ratio", "debt_to_equity"]
        labels = [q.fq.label for q in self.quarters]
        fin = self.financials.loc[[lbl for lbl in labels if lbl in self.financials.index], fin_cols]
        return {
            "ticker": self.company.ticker,
            "company": self.company.name,
            "cik": self.company.cik,
            "generated_at": self.generated_at,
            "used_finbert": self.used_finbert,
            "model_id": self.model_id,
            "model_name": self.model_name,
            "dictionary_source": self.dictionary_source,
            "latest_quarter": self.latest.fq.label,
            "quarters": [
                {
                    "label": q.fq.label,
                    "period_end": q.period_end.isoformat(),
                    "form": q.filing.form,
                    "filing_url": q.filing.document_url,
                    "press_release_url": q.press_url,
                    "sentiment": q.docs,
                    "health": q.health,
                    "piotroski": q.fscore,
                }
                for q in self.quarters
            ],
            "financials": json.loads(fin.to_json(orient="index", date_format="iso")),
            "warnings": self.warnings,
        }


def tone_index(docs: dict[str, dict], used_finbert: bool) -> float | None:
    """Headline management tone: mean of MD&A and press-release scores.

    FinBERT score (P(positive) - P(negative), averaged over sentences) when
    available, otherwise LM net tone. Both range from -1 to +1.
    """
    vals = []
    for sec in ("mdna", "press"):
        d = docs.get(sec)
        if not d:
            continue
        if used_finbert and d.get("finbert"):
            vals.append(d["finbert"]["score"])
        elif d["lm"].get("net_tone") is not None:
            vals.append(d["lm"]["net_tone"])
    return sum(vals) / len(vals) if vals else None


def _cached_doc(client: EdgarClient, key: str) -> dict | None:
    path = client.cache_dir / "sentiment" / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _store_doc(client: EdgarClient, key: str, data: dict) -> None:
    path = client.cache_dir / "sentiment" / f"{key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def analyze(ticker: str, n_quarters: int = 8, use_finbert: bool = True,
            user_agent: str | None = None, progress: ProgressFn | None = None,
            client: EdgarClient | None = None, model_id: str | None = None) -> Analysis:
    """use_finbert=False scores with the dictionary only; otherwise model_id (default:
    the active model chosen on the Models screen) scores the MD&A and press release."""
    from . import models
    say = progress or (lambda p, m: None)
    client = client or EdgarClient(user_agent)
    warnings: list[str] = []

    say(0.02, f"Looking up {ticker.upper()} on SEC EDGAR")
    company = client.lookup(ticker)
    sub = client.submissions(company.cik)
    fye = sub.get("fiscalYearEnd") or "1231"

    if use_finbert:
        model_id = model_id or models.active_model()
        if not model_id or not finbert_available(model_id):
            warnings.append("No sentiment model is downloaded (see the Models screen); used dictionary scores only.")
            use_finbert, model_id = False, None
    else:
        model_id = None

    say(0.06, "Downloading financial data (XBRL company facts)")
    facts = client.company_facts(company.cik)
    fin = quarterly_table(facts, fye)
    if fin.empty:
        raise EdgarError(f"No quarterly XBRL financial data found for {company.ticker}.")

    filings = client.filings(company.cik, min_periodic=n_quarters + 1)
    periodic = [f for f in filings if f.form in ("10-Q", "10-K") and f.report_date]
    eight_ks = [f for f in filings if f.form == "8-K"]
    if not periodic:
        raise EdgarError(
            f"{company.ticker} has no 10-Q/10-K filings. Foreign private issuers file 20-F/6-K, "
            "which this tool does not support yet."
        )

    # newest filing per fiscal quarter, then keep the latest n quarters
    by_fq: dict[FiscalQuarter, Filing] = {}
    for f in sorted(periodic, key=lambda f: f.filing_date):
        by_fq[fiscal_quarter(f.report_date, fye)] = f
    selected = sorted(by_fq)[-n_quarters:]

    quarters: list[QuarterResult] = []
    total = len(selected)
    for i, fq in enumerate(selected):
        filing = by_fq[fq]
        base = 0.10 + 0.85 * i / total
        step = 0.85 / total
        say(base, f"{fq.label}: reading {filing.form} filed {filing.filing_date}")
        q = QuarterResult(fq=fq, period_end=filing.report_date, filing=filing, press_filing=None, press_url=None)

        # ---- 10-Q / 10-K sections
        try:
            text = None
            for sec in ("mdna", "risk"):
                key = f"{filing.acc_nodash}_{sec}_{model_id or 'lm'}_v{config.SENTIMENT_VERSION}"
                doc = _cached_doc(client, key)
                if doc is None:
                    if text is None:
                        text = html_to_text(client.get(filing.document_url))
                    section_text = extract_section(text, filing.form, sec)
                    if len(section_text) < (150 if sec == "risk" else 500):
                        warnings.append(f"{fq.label}: could not locate the {SECTIONS[sec]} section.")
                        continue
                    say(base + step * (0.2 if sec == "mdna" else 0.5), f"{fq.label}: scoring {SECTIONS[sec]}")
                    # FinBERT on risk factors adds little (they are negative by design), so LM only
                    doc = score_document(section_text, sec, filing.document_url,
                                         model_id if sec == "mdna" else None).to_dict()
                    _store_doc(client, key, doc)
                q.docs[sec] = doc
        except (EdgarError, FinBertUnavailable) as exc:
            warnings.append(f"{fq.label}: {exc}")
            if isinstance(exc, FinBertUnavailable):
                use_finbert, model_id = False, None

        # ---- earnings press release
        pr = match_press_release(filing.report_date, eight_ks)
        if pr:
            try:
                q.press_filing = pr
                url = client.press_release_url(pr)
                q.press_url = url
                if url:
                    key = f"{pr.acc_nodash}_press_{model_id or 'lm'}_v{config.SENTIMENT_VERSION}"
                    doc = _cached_doc(client, key)
                    if doc is None:
                        say(base + step * 0.75, f"{fq.label}: scoring earnings press release")
                        text = clean_press_release(html_to_text(client.get(url)))
                        doc = score_document(text, "press", url, model_id).to_dict()
                        _store_doc(client, key, doc)
                    q.docs["press"] = doc
            except (EdgarError, FinBertUnavailable) as exc:
                warnings.append(f"{fq.label} press release: {exc}")
        else:
            warnings.append(f"{fq.label}: no Item 2.02 earnings 8-K found.")

        # ---- health
        if fq.label in fin.index:
            row = fin.loc[fq.label]
            sc = scorecard(row)
            q.health = sc.to_dict() | {"band": health_band(sc.overall)}
            fs = piotroski(fin, fq)
            q.fscore = fs.to_dict() if fs else None
        else:
            warnings.append(f"{fq.label}: financial data not yet available in XBRL facts.")
        quarters.append(q)

    say(1.0, "Done")
    return Analysis(
        company=company,
        fiscal_year_end=fye,
        financials=fin,
        quarters=quarters,
        used_finbert=use_finbert,
        model_id=model_id,
        dictionary_source=load_lm_dictionary()[1],
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        warnings=warnings,
    )
