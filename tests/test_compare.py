from datetime import date

from earnings_sentiment.compare import _fmt, calendar_quarter


def test_calendar_quarter_uses_the_quarters_midpoint():
    # Apple's fiscal Q4 2026 ended Sat 26 Sep 2026; Microsoft's fiscal Q1 2027 ended 30 Sep 2026
    assert calendar_quarter(date(2026, 9, 26)) == calendar_quarter(date(2026, 9, 30))
    assert calendar_quarter(date(2026, 9, 30))[1] == "Jul–Sep '26"
    # 52/53-week year: a quarter ending 1 Jul 2023 is the June quarter
    assert calendar_quarter(date(2023, 7, 1))[1] == "Apr–Jun '23"
    # NVIDIA-style quarter ending late July covers May-July -> Apr-Jun; Walmart-style 31 Jan -> Oct-Dec
    assert calendar_quarter(date(2026, 7, 26))[1] == "Apr–Jun '26"
    assert calendar_quarter(date(2026, 1, 31))[1] == "Oct–Dec '25"
    assert calendar_quarter(date(2025, 12, 27))[0] < calendar_quarter(date(2026, 3, 28))[0]


def test_metric_formatting():
    assert _fmt(0.1172, "pct_signed") == "+11.7%" and _fmt(None, "pct") == "n/a" and _fmt(0.71, "x") == "0.71×"
