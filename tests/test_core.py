"""Offline unit tests (no network, no model download)."""

from datetime import date

import pandas as pd
import pytest

from earnings_sentiment.edgar import Filing, match_press_release
from earnings_sentiment.financials import add_derived, flow_quarterly, instant_values
from earnings_sentiment.health import scale, scorecard
from earnings_sentiment.periods import FiscalQuarter, fiscal_quarter
from earnings_sentiment.sentiment import lm_score
from earnings_sentiment.textextract import extract_section, sentences


# ------------------------------------------------------------------ periods
@pytest.mark.parametrize(
    "end, fye, expected",
    [
        (date(2025, 12, 27), "0925", FiscalQuarter(2026, 1)),  # Apple Q1
        (date(2026, 3, 28), "0925", FiscalQuarter(2026, 2)),
        (date(2023, 7, 1), "0930", FiscalQuarter(2023, 3)),    # 52/53-week drift into July
        (date(2026, 9, 26), "0925", FiscalQuarter(2026, 4)),
        (date(2026, 3, 31), "1231", FiscalQuarter(2026, 1)),   # calendar-year company
        (date(2026, 12, 31), "1231", FiscalQuarter(2026, 4)),
        (date(2026, 6, 30), "0630", FiscalQuarter(2026, 4)),   # June FYE (e.g. Microsoft)
        (date(2026, 9, 30), "0630", FiscalQuarter(2027, 1)),
    ],
)
def test_fiscal_quarter(end, fye, expected):
    assert fiscal_quarter(end, fye) == expected


def test_quarter_navigation():
    assert FiscalQuarter(2026, 1).prev() == FiscalQuarter(2025, 4)
    assert FiscalQuarter(2026, 3).year_ago() == FiscalQuarter(2025, 3)


# ------------------------------------------------------------------ financials
def _e(start, end, val, filed="2026-01-01"):
    return {"start": start, "end": end, "val": val, "filed": filed}


def test_flow_quarterly_derives_q4_and_ytd_cash_flow():
    entries = [
        _e("2024-09-29", "2024-12-28", 30),   # Q1 (3 months)
        _e("2024-09-29", "2025-03-29", 54),   # 6-month YTD -> Q2 = 24
        _e("2024-09-29", "2025-06-28", 82),   # 9-month YTD -> Q3 = 28
        _e("2024-09-29", "2025-09-27", 112),  # full year -> Q4 = 30
    ]
    q = flow_quarterly(entries)
    assert q[date(2024, 12, 28)] == 30
    assert q[date(2025, 3, 29)] == 24
    assert q[date(2025, 6, 28)] == 28
    assert q[date(2025, 9, 27)] == 30


def test_flow_quarterly_prefers_direct_and_latest_restatement():
    entries = [
        _e("2025-03-30", "2025-06-28", 10, filed="2025-08-01"),
        _e("2025-03-30", "2025-06-28", 11, filed="2026-08-01"),  # restated later
    ]
    assert flow_quarterly(entries)[date(2025, 6, 28)] == 11


def test_instant_values():
    entries = [{"end": "2025-06-28", "val": 5, "filed": "2025-08-01"}, {"end": "2025-06-28", "val": 6, "filed": "2025-11-01"}]
    assert instant_values(entries) == {date(2025, 6, 28): 6}


def test_add_derived_yoy_uses_fiscal_quarter_not_row_position():
    rows = []
    for i, fq in enumerate([FiscalQuarter(2025, q) for q in (1, 2, 3, 4)] + [FiscalQuarter(2026, 1)]):
        rows.append({"fiscal_quarter": fq, "label": fq.label, "revenue": 100 + i * 10, "net_income": 10,
                     "gross_profit": 40, "operating_income": 20, "eps_diluted": 1.0, "ocf": 15, "capex": 5,
                     "cost_of_revenue": None, "debt_noncurrent": 50, "debt_current": 0, "commercial_paper": 0,
                     "cash": 30, "securities_current": 0, "securities_noncurrent": 0, "equity": 100,
                     "assets_current": 60, "liabilities_current": 40, "rnd": 5})
    df = add_derived(pd.DataFrame(rows).set_index("label", drop=False))
    assert df.loc["FY2026 Q1", "revenue_yoy"] == pytest.approx((140 - 100) / 100)
    assert pd.isna(df.loc["FY2025 Q4", "revenue_yoy"])
    assert df.loc["FY2026 Q1", "revenue_ttm"] == 120 + 130 + 110 + 140 - 0  # Q2..Q4 2025 + Q1 2026
    assert df.loc["FY2026 Q1", "fcf"] == 10


# ------------------------------------------------------------------ sentiment
def test_lm_score_counts_and_negation():
    s = lm_score("Profit improved strongly. We did not achieve gains. Litigation and uncertainty increased losses.")
    assert s.positive >= 1           # "improved" counts
    assert s.negative >= 2           # "litigation"/"losses"
    assert s.uncertainty >= 1
    negated = lm_score("not improved")
    assert negated.positive == 0     # negation within three words cancels a positive word


def test_lm_net_tone_bounds():
    assert lm_score("strong excellent gains").net_tone == 1.0
    assert lm_score("loss decline impairment").net_tone == -1.0
    assert lm_score("the quarter").net_tone is None


def test_sentences_filters_fragments():
    text = "Item 2.\nTotal 1,234 5,678\nRevenue increased due to higher iPhone sales in all regions. Ok."
    assert sentences(text) == ["Revenue increased due to higher iPhone sales in all regions."]


# ------------------------------------------------------------------ text extraction
def test_extract_section_skips_table_of_contents():
    body = "x " * 400
    text = (
        "Item 2. Management's Discussion and Analysis 13 Item 3. Quantitative and Qualitative 19 "
        f"... Item 2. Management's Discussion and Analysis The Company grew. {body} "
        "Item 3. Quantitative and Qualitative Disclosures About Market Risk none"
    )
    sec = extract_section(text, "10-Q", "mdna")
    assert sec.startswith("and Analysis The Company grew.")
    assert "Market Risk" not in sec


# ------------------------------------------------------------------ health & filings
def test_scale_clamps_and_inverts():
    assert scale(0.15, -0.10, 0.15) == 100
    assert scale(-0.5, -0.10, 0.15) == 0
    assert scale(1.65, 3.0, 0.3) == 50  # inverted metric (lower is better)
    assert scale(None, 0, 1) is None


def test_scorecard_handles_missing_values():
    sc = scorecard(pd.Series({"revenue_yoy": 0.05}))
    assert sc.pillars["Growth"] is not None
    assert sc.pillars["Leverage"] is None
    assert sc.overall == sc.pillars["Growth"]


def test_match_press_release_picks_first_202_after_quarter():
    mk = lambda d, items: Filing("8-K", f"acc-{d}", d, d, "x.htm", items, "0000000001")  # noqa: E731
    eight_ks = [mk(date(2026, 1, 29), "2.02,9.01"), mk(date(2026, 1, 15), "5.02"), mk(date(2026, 4, 30), "2.02,9.01")]
    assert match_press_release(date(2025, 12, 27), eight_ks).filing_date == date(2026, 1, 29)
    assert match_press_release(date(2025, 6, 28), eight_ks) is None
