"""Compare 2-3 companies side by side, lined up by calendar quarter.

Fiscal years differ (Apple's ends in September, Microsoft's in June), so
"FY2026 Q4" means different months for different companies. Each quarter is
placed in the calendar quarter that contains its midpoint (45 days before it
ended), e.g. NVIDIA's quarter ending 26 July (May–July) counts as "Apr–Jun",
and Walmart's ending 31 January (Nov–Jan) as "Oct–Dec".
"""

from __future__ import annotations

import math
from datetime import timedelta

import plotly.graph_objects as go

from .analysis import Analysis
from .charts import _layout, _pal, _rgba

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def calendar_quarter(d) -> tuple[int, str]:
    """(sort key, label) of the calendar quarter holding the fiscal quarter's midpoint, e.g. "Jul–Sep '26"."""
    mid = d - timedelta(days=45)
    y, m = mid.year, mid.month
    q = (m - 1) // 3
    return y * 4 + q, f"{MONTHS[q * 3]}–{MONTHS[q * 3 + 2]} '{y % 100:02d}"


def _num(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) or math.isinf(v) else v


def _series(a: Analysis, getter) -> dict[int, float | None]:
    out = {}
    for q in a.quarters:
        key, _ = calendar_quarter(q.period_end)
        out[key] = getter(a, q)
    return out


def _fin(col):
    return lambda a, q: _num(a.financials.loc[q.fq.label, col]) if q.fq.label in a.financials.index else None


def _fcf_margin_ttm(a, q):
    f = a.financials
    if q.fq.label not in f.index:
        return None
    fcf, rev = _num(f.loc[q.fq.label, "fcf_ttm"]), _num(f.loc[q.fq.label, "revenue_ttm"])
    return fcf / rev if fcf is not None and rev else None


def _health(a, q):
    return _num((q.health or {}).get("overall"))


def _tone(a, q):
    st = a.sentiment_table()
    return _num(st.loc[q.fq.label, "tone_index"]) if not st.empty and q.fq.label in st.index else None


CHARTS = {
    "growth": ("Revenue growth", "vs the same quarter a year earlier", _fin("revenue_yoy"), ".0%", "%{y:+.1%}"),
    "op_margin": ("Operating margin", "operating income as a share of revenue", _fin("operating_margin"), ".0%", "%{y:.1%}"),
    "gross_margin": ("Gross margin", "revenue left after the cost of what was sold", _fin("gross_margin"), ".0%", "%{y:.1%}"),
    "fcf_margin": ("Free cash flow margin", "trailing twelve months, cash left after investment", _fcf_margin_ttm, ".0%", "%{y:.1%}"),
    "health": ("Health score", "0–100 financial strength", _health, None, "%{y:.0f}/100"),
    "tone": ("Tone index", "how positive management's language is, −1 to +1", _tone, ".2f", "%{y:+.2f}"),
}


def chart(analyses: list[Analysis], key: str, mode: str) -> go.Figure:
    title, sub, getter, fmt, hover = CHARTS[key]
    p = _pal(mode)
    per = [_series(a, getter) for a in analyses]
    keys = sorted(set().union(*[s.keys() for s in per]))
    labels = {}
    for a in analyses:
        for q in a.quarters:
            k, lbl = calendar_quarter(q.period_end)
            labels[k] = lbl
    x = [labels[k].replace(" '", "<br>'") for k in keys]  # two-line ticks: "Jul–Sep" over "'26"
    fig = go.Figure()
    for i, (a, s) in enumerate(zip(analyses, per)):
        color = p["series"][i % len(p["series"])]
        y = [s.get(k) for k in keys]
        fig.add_scatter(x=x, y=y, name=a.company.ticker, mode="lines+markers", connectgaps=True,
                        line=dict(color=color, width=2.6, shape="spline", smoothing=0.8),
                        marker=dict(size=6, color=color, line=dict(width=1.5, color=p["card"])),
                        hovertemplate=f"<b>{hover}</b>")
        last = max((j for j, v in enumerate(y) if v is not None), default=None)
        if last is not None:
            fig.add_scatter(x=[x[last]], y=[y[last]], mode="markers", showlegend=False, hoverinfo="skip",
                            marker=dict(size=16, color=_rgba(color, 0.22)))
    if key in ("growth", "tone", "fcf_margin"):
        fig.add_hline(y=0, line_color=p["muted"], line_width=1, opacity=0.35)
    if key == "health":
        fig.update_yaxes(range=[0, 105])
    fig = _layout(fig, title, mode, sub, fmt)
    fig.update_xaxes(tickangle=0)
    return fig


# metric key, label, getter, format, higher is better?
METRICS = [
    ("revenue_yoy", "Revenue growth (YoY)", _fin("revenue_yoy"), "pct_signed", True),
    ("eps_yoy", "EPS growth (YoY)", _fin("eps_diluted_yoy"), "pct_signed", True),
    ("gross_margin", "Gross margin", _fin("gross_margin"), "pct", True),
    ("operating_margin", "Operating margin", _fin("operating_margin"), "pct", True),
    ("net_margin", "Net margin", _fin("net_margin"), "pct", True),
    ("fcf_margin", "Free cash flow margin (TTM)", _fcf_margin_ttm, "pct", True),
    ("current_ratio", "Current ratio", _fin("current_ratio"), "x", True),
    ("debt_to_equity", "Debt to equity", _fin("debt_to_equity"), "x", False),
    ("health", "Health score", _health, "int", True),
    ("tone", "Tone index", _tone, "signed", True),
]


def _fmt(v, kind: str) -> str:
    if v is None:
        return "n/a"
    if kind == "pct_signed":
        return f"{v:+.1%}"
    if kind == "pct":
        return f"{v:.1%}"
    if kind == "x":
        return f"{v:.2f}×"
    if kind == "int":
        return f"{v:.0f}"
    return f"{v:+.2f}"


def table(analyses: list[Analysis]) -> list[dict]:
    rows = []
    for key, label, getter, kind, higher in METRICS:
        vals = [getter(a, a.latest) for a in analyses]
        known = [v for v in vals if v is not None]
        best = (max(known) if higher else min(known)) if len(known) > 1 else None
        if key == "debt_to_equity":  # negative equity makes the ratio meaningless
            best = min((v for v in known if v >= 0), default=None) if len(known) > 1 else None
        rows.append({"key": key, "label": label, "higher_is_better": higher,
                     "values": [{"value": v, "text": _fmt(v, kind), "best": v is not None and v == best} for v in vals]})
    fs = [(a.latest.fscore or {}).get("score") for a in analyses]
    known = [v for v in fs if v is not None]
    rows.insert(8, {"key": "fscore", "label": "Piotroski F-Score", "higher_is_better": True,
                    "values": [{"value": v, "text": "n/a" if v is None else f"{v}/9",
                                "best": len(known) > 1 and v == max(known)} for v in fs]})
    return rows


def build(analyses: list[Analysis], mode: str, snapshots: list[dict]) -> dict:
    companies = []
    for a, snap in zip(analyses, snapshots):
        _, cal = calendar_quarter(a.latest.period_end)
        companies.append(snap | {"calendar_quarter": cal, "fiscal_year_end": a.fiscal_year_end})
    models = {a.model_name for a in analyses}
    notes = []
    if len(models) > 1:
        notes.append("Tone was scored with different methods (" + ", ".join(sorted(models)) + "), so tone values are "
                     "not directly comparable. Re-run the analyses with the same model for a fair tone comparison.")
    latest = {c["calendar_quarter"] for c in companies}
    if len(latest) > 1:
        notes.append("The latest reported quarters differ (" + ", ".join(f"{c['ticker']} {c['calendar_quarter']}"
                     for c in companies) + "); the table compares each company's latest quarter.")
    return {"companies": companies, "charts": {k: chart(analyses, k, mode).to_plotly_json() for k in CHARTS},
            "table": table(analyses), "notes": notes}
