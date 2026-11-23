"""Financial health scoring.

Two views, both computed only from SEC-reported numbers:

1. Scorecard (0-100) - five transparent pillars: growth, profitability, cash
   generation, liquidity, leverage. Each metric is mapped linearly between a
   'weak' and a 'strong' threshold (see THRESHOLDS). These are generic, not
   industry-specific, rules of thumb: treat them as a starting point to tune.

2. Piotroski F-Score (0-9) - nine binary signals of improving fundamentals.
   Piotroski, J. (2000). "Value Investing: The Use of Historical Financial
   Statement Information to Separate Winners from Losers." Journal of
   Accounting Research 38, 1-41. https://doi.org/10.2307/2672906
   Applied here on a trailing-twelve-month (TTM) basis versus the same TTM a
   year earlier, so it can be refreshed every quarter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

from .periods import FiscalQuarter

# metric: (weak value -> score 0, strong value -> score 100)
THRESHOLDS = {
    "revenue_yoy": (-0.10, 0.15),
    "eps_yoy": (-0.20, 0.20),
    "operating_margin_ttm": (0.0, 0.30),
    "net_margin_ttm": (0.0, 0.25),
    "fcf_margin_ttm": (0.0, 0.25),
    "fcf_conversion_ttm": (0.5, 1.2),
    "current_ratio": (0.5, 2.0),
    "cash_to_current_liabilities": (0.2, 1.5),
    "debt_to_equity": (3.0, 0.3),
    "debt_to_ocf_ttm": (5.0, 0.5),
}

PILLARS = {
    "Growth": ["revenue_yoy", "eps_yoy"],
    "Profitability": ["operating_margin_ttm", "net_margin_ttm"],
    "Cash generation": ["fcf_margin_ttm", "fcf_conversion_ttm"],
    "Liquidity": ["current_ratio", "cash_to_current_liabilities"],
    "Leverage": ["debt_to_equity", "debt_to_ocf_ttm"],
}

METRIC_LABELS = {
    "revenue_yoy": "Revenue growth YoY",
    "eps_yoy": "Diluted EPS growth YoY",
    "operating_margin_ttm": "Operating margin (TTM)",
    "net_margin_ttm": "Net margin (TTM)",
    "fcf_margin_ttm": "Free-cash-flow margin (TTM)",
    "fcf_conversion_ttm": "FCF / net income (TTM)",
    "current_ratio": "Current ratio",
    "cash_to_current_liabilities": "Cash + all marketable securities / current liabilities",
    "debt_to_equity": "Total debt / equity",
    "debt_to_ocf_ttm": "Total debt / operating cash flow (TTM, years)",
}

PERCENT_METRICS = {"revenue_yoy", "eps_yoy", "operating_margin_ttm", "net_margin_ttm", "fcf_margin_ttm"}


def _f(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) or math.isinf(v) else v


def _ratio(a, b) -> float | None:
    a, b = _f(a), _f(b)
    if a is None or b is None or b == 0:
        return None
    return a / b


def scale(value: float | None, weak: float, strong: float) -> float | None:
    if value is None:
        return None
    t = (value - weak) / (strong - weak)
    return round(100 * min(1.0, max(0.0, t)), 1)


def health_metrics(row: pd.Series) -> dict[str, float | None]:
    op_ttm = _ttm_from_row(row, "operating_income")
    return {
        "revenue_yoy": _f(row.get("revenue_yoy")),
        "eps_yoy": _f(row.get("eps_diluted_yoy")),
        "operating_margin_ttm": _ratio(op_ttm, row.get("revenue_ttm")),
        "net_margin_ttm": _ratio(row.get("net_income_ttm"), row.get("revenue_ttm")),
        "fcf_margin_ttm": _ratio(row.get("fcf_ttm"), row.get("revenue_ttm")),
        "fcf_conversion_ttm": _ratio(row.get("fcf_ttm"), row.get("net_income_ttm")),
        "current_ratio": _f(row.get("current_ratio")),
        # Long-term marketable securities are included: for cash-rich companies they are
        # mostly highly liquid government and corporate bonds.
        "cash_to_current_liabilities": _ratio(
            (_f(row.get("cash")) or 0) + (_f(row.get("securities_current")) or 0)
            + (_f(row.get("securities_noncurrent")) or 0), row.get("liabilities_current")
        ),
        "debt_to_equity": _f(row.get("debt_to_equity")),
        "debt_to_ocf_ttm": _ratio(row.get("total_debt"), row.get("ocf_ttm")),
    }


def _ttm_from_row(row: pd.Series, col: str) -> float | None:
    return _f(row.get(f"{col}_ttm"))


@dataclass
class Scorecard:
    overall: float | None
    pillars: dict[str, float | None]
    metrics: dict[str, float | None]
    metric_scores: dict[str, float | None]

    def to_dict(self) -> dict:
        return {"overall": self.overall, "pillars": self.pillars, "metrics": self.metrics, "metric_scores": self.metric_scores}


def scorecard(row: pd.Series) -> Scorecard:
    metrics = health_metrics(row)
    mscores = {k: scale(v, *THRESHOLDS[k]) for k, v in metrics.items()}
    pillars: dict[str, float | None] = {}
    for name, keys in PILLARS.items():
        vals = [mscores[k] for k in keys if mscores[k] is not None]
        pillars[name] = round(sum(vals) / len(vals), 1) if vals else None
    pv = [v for v in pillars.values() if v is not None]
    overall = round(sum(pv) / len(pv), 1) if pv else None
    return Scorecard(overall, pillars, metrics, mscores)


def health_band(score: float | None) -> str:
    if score is None:
        return "n/a"
    if score >= 75:
        return "Strong"
    if score >= 55:
        return "Healthy"
    if score >= 40:
        return "Mixed"
    return "Weak"


# --------------------------------------------------------------------- Piotroski


@dataclass
class FScore:
    score: int
    available: int
    signals: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"score": self.score, "available": self.available, "signals": self.signals}


def piotroski(df: pd.DataFrame, fq: FiscalQuarter) -> FScore | None:
    rows = {r["fiscal_quarter"]: r for _, r in df.iterrows()}
    cur = rows.get(fq)
    prev = rows.get(fq.year_ago())
    prev2 = rows.get(fq.year_ago().year_ago())
    if cur is None or prev is None:
        return None
    g = lambda r, c: _f(r.get(c)) if r is not None else None  # noqa: E731

    roa = _ratio(g(cur, "net_income_ttm"), g(prev, "assets"))
    roa_prev = _ratio(g(prev, "net_income_ttm"), g(prev2, "assets") if prev2 is not None else g(prev, "assets"))
    lev = _ratio(g(cur, "debt_noncurrent"), g(cur, "assets"))
    lev_prev = _ratio(g(prev, "debt_noncurrent"), g(prev, "assets"))
    gm = _ratio(g(cur, "gross_profit_ttm"), g(cur, "revenue_ttm"))
    gm_prev = _ratio(g(prev, "gross_profit_ttm"), g(prev, "revenue_ttm"))
    at = _ratio(g(cur, "revenue_ttm"), g(prev, "assets"))
    at_prev = _ratio(g(prev, "revenue_ttm"), g(prev2, "assets") if prev2 is not None else g(prev, "assets"))
    shares = g(cur, "shares_outstanding") or g(cur, "diluted_shares")
    shares_prev = g(prev, "shares_outstanding") or g(prev, "diluted_shares")

    def cmp(a, b, op):
        if a is None or b is None:
            return None
        return op(a, b)

    signals = [
        ("Profitability", "Positive return on assets (TTM)", roa is not None and roa > 0 if roa is not None else None),
        ("Profitability", "Positive operating cash flow (TTM)", (g(cur, "ocf_ttm") or 0) > 0 if g(cur, "ocf_ttm") is not None else None),
        ("Profitability", "Return on assets improved vs a year ago", cmp(roa, roa_prev, lambda a, b: a > b)),
        ("Profitability", "Cash flow exceeds net income (earnings quality)", cmp(g(cur, "ocf_ttm"), g(cur, "net_income_ttm"), lambda a, b: a > b)),
        ("Leverage & liquidity", "Long-term debt / assets decreased", cmp(lev, lev_prev, lambda a, b: a < b)),
        ("Leverage & liquidity", "Current ratio improved", cmp(g(cur, "current_ratio"), g(prev, "current_ratio"), lambda a, b: a > b)),
        ("Leverage & liquidity", "No net new shares issued", cmp(shares, shares_prev, lambda a, b: a <= b)),
        ("Efficiency", "Gross margin improved (TTM)", cmp(gm, gm_prev, lambda a, b: a > b)),
        ("Efficiency", "Asset turnover improved (TTM)", cmp(at, at_prev, lambda a, b: a > b)),
    ]
    out = [{"group": grp, "signal": name, "pass": (None if ok is None else bool(ok))} for grp, name, ok in signals]
    available = sum(1 for s in out if s["pass"] is not None)
    return FScore(score=sum(1 for s in out if s["pass"]), available=available, signals=out)
