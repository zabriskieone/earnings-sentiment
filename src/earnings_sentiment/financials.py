"""Turn SEC XBRL 'company facts' into a clean quarterly financial table.

Source: https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json

Key subtleties handled here:
* Income-statement items appear both as 3-month values and as year-to-date
  values; cash-flow items are usually *only* year-to-date. Quarterly values are
  derived by differencing consecutive cumulative values that share a start date.
* Fourth-quarter figures are rarely reported directly (the 10-K covers the full
  year), so Q4 = full year minus nine months.
* Companies switch XBRL tags over time (e.g. SalesRevenueNet ->
  RevenueFromContractWithCustomerExcludingAssessedTax), so each metric lists
  fallback tags and the first tag with a value for a period wins.
* When a figure is restated, the most recently filed value is used.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

import numpy as np
import pandas as pd

from .periods import FiscalQuarter, fiscal_quarter

# metric -> (kind, [tags in priority order]); kind: flow | instant | average
METRICS: dict[str, tuple[str, list[str]]] = {
    "revenue": ("flow", [
        "RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueGoodsNet",
    ]),
    "cost_of_revenue": ("flow", ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold"]),
    "gross_profit": ("flow", ["GrossProfit"]),
    "rnd": ("flow", ["ResearchAndDevelopmentExpense"]),
    "sga": ("flow", ["SellingGeneralAndAdministrativeExpense"]),
    "operating_income": ("flow", ["OperatingIncomeLoss"]),
    "net_income": ("flow", ["NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"]),
    "eps_diluted": ("flow", ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"]),
    "ocf": ("flow", [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ]),
    "capex": ("flow", ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"]),
    "buybacks": ("flow", ["PaymentsForRepurchaseOfCommonStock"]),
    "dividends": ("flow", ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock"]),
    "diluted_shares": ("average", ["WeightedAverageNumberOfDilutedSharesOutstanding"]),
    "cash": ("instant", [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ]),
    "securities_current": ("instant", ["MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesCurrent", "ShortTermInvestments"]),
    "securities_noncurrent": ("instant", ["MarketableSecuritiesNoncurrent", "AvailableForSaleSecuritiesDebtSecuritiesNoncurrent"]),
    "assets_current": ("instant", ["AssetsCurrent"]),
    "liabilities_current": ("instant", ["LiabilitiesCurrent"]),
    "assets": ("instant", ["Assets"]),
    "liabilities": ("instant", ["Liabilities"]),
    "equity": ("instant", ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]),
    "debt_noncurrent": ("instant", ["LongTermDebtNoncurrent", "LongTermDebt"]),
    "debt_current": ("instant", ["LongTermDebtCurrent", "DebtCurrent"]),
    "commercial_paper": ("instant", ["CommercialPaper", "ShortTermBorrowings"]),
    "shares_outstanding": ("instant", ["CommonStockSharesOutstanding"]),
}

QUARTER_DAYS = (80, 100)

# Human-readable names, used by charts, tables and reports
LABELS = {
    "revenue": "Revenue", "gross_profit": "Gross profit", "operating_income": "Operating income",
    "net_income": "Net income", "eps_diluted": "Diluted EPS", "ocf": "Operating cash flow",
    "capex": "Capital expenditure", "fcf": "Free cash flow", "buybacks": "Share buybacks",
    "dividends": "Dividends paid", "rnd": "R&D expense", "cash": "Cash & equivalents",
    "total_debt": "Total debt", "net_cash": "Net cash (cash + securities - debt)",
    "gross_margin": "Gross margin", "operating_margin": "Operating margin", "net_margin": "Net margin",
    "fcf_margin": "FCF margin", "current_ratio": "Current ratio", "debt_to_equity": "Debt / equity",
    "rnd_intensity": "R&D % of revenue", "revenue_yoy": "Revenue growth (YoY)",
    "revenue_qoq": "Revenue growth (QoQ)", "eps_yoy": "EPS growth (YoY)", "net_income_yoy": "Net income growth (YoY)",
}


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _latest(entries: list[dict], key) -> dict:
    best: dict = {}
    for e in entries:
        k = key(e)
        if k not in best or e.get("filed", "") > best[k].get("filed", ""):
            best[k] = e
    return best


def flow_quarterly(entries: list[dict], additive: bool = True) -> dict[date, float]:
    """Quarterly values for a duration concept, keyed by period end date."""
    dur = [e for e in entries if e.get("start") and e.get("end")]
    best = _latest(dur, lambda e: (e["start"], e["end"]))
    out: dict[date, float] = {}
    groups: dict[date, list[tuple[date, float]]] = defaultdict(list)
    for (s, e), rec in best.items():
        sd, ed = _d(s), _d(e)
        days = (ed - sd).days
        if QUARTER_DAYS[0] <= days <= QUARTER_DAYS[1]:
            out[ed] = float(rec["val"])
        groups[sd].append((ed, float(rec["val"])))
    if not additive:
        return out
    for start, items in groups.items():
        items.sort()
        prev: tuple[date, float] | None = None
        for end, val in items:
            if prev is not None:
                gap = (end - prev[0]).days
                if QUARTER_DAYS[0] <= gap <= QUARTER_DAYS[1] and end not in out:
                    out[end] = val - prev[1]
            prev = (end, val)
    return out


def instant_values(entries: list[dict]) -> dict[date, float]:
    inst = [e for e in entries if e.get("end") and not e.get("start")]
    best = _latest(inst, lambda e: e["end"])
    return {_d(k): float(v["val"]) for k, v in best.items()}


def _concept_entries(facts: dict, tag: str) -> list[dict]:
    for taxonomy in ("us-gaap", "dei", "ifrs-full"):
        node = facts.get("facts", {}).get(taxonomy, {}).get(tag)
        if node:
            units = node.get("units", {})
            for unit in ("USD", "USD/shares", "shares"):
                if unit in units:
                    return units[unit]
            return next(iter(units.values()), [])
    return []


def extract_series(facts: dict) -> dict[str, dict[date, float]]:
    series: dict[str, dict[date, float]] = {}
    for metric, (kind, tags) in METRICS.items():
        merged: dict[date, float] = {}
        for tag in tags:
            entries = _concept_entries(facts, tag)
            if not entries:
                continue
            if kind == "instant":
                vals = instant_values(entries)
            else:
                vals = flow_quarterly(entries, additive=(kind == "flow"))
            for k, v in vals.items():
                merged.setdefault(k, v)
        series[metric] = merged
    return series


def _match_end(target: date, values: dict[date, float], tolerance: int = 7) -> float | None:
    if target in values:
        return values[target]
    near = [d for d in values if abs((d - target).days) <= tolerance]
    return values[min(near, key=lambda d: abs((d - target).days))] if near else None


def quarterly_table(facts: dict, fiscal_year_end: str, period_ends: list[date] | None = None) -> pd.DataFrame:
    """One row per fiscal quarter, oldest first, with raw and derived metrics."""
    series = extract_series(facts)
    if period_ends is None:
        period_ends = sorted(set(series["revenue"]) | set(series["net_income"]))
    rows: dict[FiscalQuarter, dict] = {}
    for end in sorted(period_ends):
        fq = fiscal_quarter(end, fiscal_year_end)
        row = {"fiscal_quarter": fq, "label": fq.label, "period_end": end}
        for metric in METRICS:
            row[metric] = _match_end(end, series[metric])
        rows[fq] = row  # later period end for the same label wins
    df = pd.DataFrame(sorted(rows.values(), key=lambda r: r["fiscal_quarter"]))
    if df.empty:
        return df
    df = df.set_index("label", drop=False)
    return add_derived(df)


def _safe_div(a, b):
    a = pd.to_numeric(a, errors="coerce")
    b = pd.to_numeric(b, errors="coerce")
    with np.errstate(divide="ignore", invalid="ignore"):
        r = a / b
    return r.replace([np.inf, -np.inf], np.nan)


def _lag(df: pd.DataFrame, col: str, quarters: int) -> pd.Series:
    """Value from N quarters earlier, aligned by fiscal quarter (not row position)."""
    lookup = dict(zip(df["fiscal_quarter"], df[col]))
    out = []
    for fq in df["fiscal_quarter"]:
        target = fq
        for _ in range(quarters):
            target = target.prev()
        out.append(lookup.get(target, np.nan))
    return pd.Series(out, index=df.index, dtype="float64")


def _ttm(df: pd.DataFrame, col: str) -> pd.Series:
    vals = [df[col].astype(float)] + [_lag(df, col, k) for k in (1, 2, 3)]
    return pd.concat(vals, axis=1).sum(axis=1, min_count=4)


def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    num = lambda c: pd.to_numeric(df[c], errors="coerce")  # noqa: E731
    if df["gross_profit"].isna().any():
        df["gross_profit"] = num("gross_profit").fillna(num("revenue") - num("cost_of_revenue"))
    df["fcf"] = num("ocf") - num("capex").fillna(0)
    df["total_debt"] = num("debt_noncurrent").fillna(0) + num("debt_current").fillna(0) + num("commercial_paper").fillna(0)
    df.loc[num("debt_noncurrent").isna() & num("debt_current").isna(), "total_debt"] = np.nan
    df["net_cash"] = (
        num("cash").fillna(0) + num("securities_current").fillna(0)
        + num("securities_noncurrent").fillna(0) - df["total_debt"].fillna(0)
    )
    df["gross_margin"] = _safe_div(df["gross_profit"], df["revenue"])
    df["operating_margin"] = _safe_div(df["operating_income"], df["revenue"])
    df["net_margin"] = _safe_div(df["net_income"], df["revenue"])
    df["fcf_margin"] = _safe_div(df["fcf"], df["revenue"])
    df["rnd_intensity"] = _safe_div(df["rnd"], df["revenue"])
    df["current_ratio"] = _safe_div(df["assets_current"], df["liabilities_current"])
    df["debt_to_equity"] = _safe_div(df["total_debt"], df["equity"])
    for col in ("revenue", "net_income", "eps_diluted", "gross_profit", "operating_income", "fcf"):
        df[f"{col}_yoy"] = _safe_div(num(col) - _lag(df, col, 4), _lag(df, col, 4).abs())
        df[f"{col}_qoq"] = _safe_div(num(col) - _lag(df, col, 1), _lag(df, col, 1).abs())
    for col in ("revenue", "net_income", "ocf", "fcf", "gross_profit", "operating_income", "eps_diluted"):
        df[f"{col}_ttm"] = _ttm(df, col)
    return df
