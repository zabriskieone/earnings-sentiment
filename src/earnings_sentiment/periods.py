"""Map a period-end date to a fiscal quarter label (e.g. FY2026 Q1).

Many companies (Apple included) use 52/53-week years ending on a Saturday, so
period ends drift a few days around month boundaries (e.g. 2023-07-01 is really
the June quarter). We snap to the nearest month end before computing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True, order=True)
class FiscalQuarter:
    year: int
    quarter: int

    @property
    def label(self) -> str:
        return f"FY{self.year} Q{self.quarter}"

    @property
    def slug(self) -> str:
        return f"FY{self.year}-Q{self.quarter}"

    def prev(self) -> "FiscalQuarter":
        return FiscalQuarter(self.year - 1, 4) if self.quarter == 1 else FiscalQuarter(self.year, self.quarter - 1)

    def year_ago(self) -> "FiscalQuarter":
        return FiscalQuarter(self.year - 1, self.quarter)


def snap_month(d: date) -> tuple[int, int]:
    """Return (year, month) of the month this period end belongs to."""
    if d.day <= 7:  # e.g. 2023-07-01 -> June
        d = d.replace(day=1) - timedelta(days=1)
    return d.year, d.month


def fiscal_quarter(period_end: date, fiscal_year_end: str) -> FiscalQuarter:
    """fiscal_year_end is SEC's 'MMDD' string, e.g. '0925' for Apple, '1231' for calendar."""
    fye_month = int(fiscal_year_end[:2]) if fiscal_year_end else 12
    # A Sept-26 style FYE whose day is early in the month really means the prior month
    if fiscal_year_end and int(fiscal_year_end[2:]) <= 7:
        fye_month = fye_month - 1 or 12
    y, m = snap_month(period_end)
    months_after = (m - fye_month) % 12
    # Irregular period ends are rounded to the nearest quarter boundary
    shift = round(months_after / 3) * 3 - months_after
    idx = y * 12 + (m - 1) + shift
    ya, ma = divmod(idx, 12)
    ma += 1
    q = ((ma - fye_month) % 12) // 3 or 4
    fy = ya + (1 if ma > fye_month else 0)
    return FiscalQuarter(fy, q)
