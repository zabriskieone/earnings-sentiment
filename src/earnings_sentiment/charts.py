"""Plotly figures shared by the dashboard and the HTML report.

Design rules (from the project's data-viz guidelines):
* one y-axis per chart - measures with different units get separate charts
* fixed categorical color order, never cycled; legend whenever >= 2 series
* polarity (tone above/below zero) uses a blue <-> red diverging pair
* thin marks, recessive gridlines, hover tooltips on every chart
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from .analysis import Analysis
from .health import PILLARS

# Validated categorical palette (light-mode steps; first three are all-pairs CVD safe)
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
POSITIVE = "#2a78d6"   # diverging pole (blue)
NEGATIVE = "#e34948"   # diverging pole (red)
NEUTRAL = "#898781"
GRID = "rgba(137,135,129,0.25)"


def _layout(fig: go.Figure, title: str, y_title: str = "", y_format: str | None = None, height: int = 360) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, x=0, xanchor="left", y=0.98, yanchor="top", yref="container", font=dict(size=15)),
        height=height,
        autosize=True,
        margin=dict(l=10, r=10, t=78, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified",
        font=dict(family='system-ui, -apple-system, "Segoe UI", sans-serif', size=12),
        bargap=0.25,
        bargroupgap=0.08,
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID, type="category")
    fig.update_yaxes(gridcolor=GRID, zerolinecolor="rgba(137,135,129,0.6)", title_text=y_title,
                     tickformat=y_format)
    return fig


def _labels(a: Analysis) -> list[str]:
    return [q.fq.label for q in a.quarters]


def _fin(a: Analysis) -> pd.DataFrame:
    labels = [lbl for lbl in _labels(a) if lbl in a.financials.index]
    return a.financials.loc[labels]


def revenue_income_chart(a: Analysis) -> go.Figure:
    df = _fin(a)
    fig = go.Figure()
    for i, (col, name) in enumerate((("revenue", "Revenue"), ("net_income", "Net income"))):
        fig.add_bar(x=df.index, y=df[col] / 1e9, name=name, marker_color=SERIES[i],
                    marker_line_width=0, hovertemplate="%{y:$,.1f}B")
    return _layout(fig, "Revenue and net income per quarter", "US$ billions")


def growth_chart(a: Analysis) -> go.Figure:
    df = _fin(a)
    fig = go.Figure()
    for i, (col, name) in enumerate((("revenue_yoy", "Revenue YoY"), ("eps_diluted_yoy", "Diluted EPS YoY"))):
        fig.add_scatter(x=df.index, y=df[col], name=name, mode="lines+markers",
                        line=dict(color=SERIES[i], width=2), marker=dict(size=8), hovertemplate="%{y:+.1%}")
    fig.add_hline(y=0, line_color=NEUTRAL, line_width=1)
    return _layout(fig, "Year-on-year growth", "", ".0%")


def margins_chart(a: Analysis) -> go.Figure:
    df = _fin(a)
    fig = go.Figure()
    for i, (col, name) in enumerate((("gross_margin", "Gross"), ("operating_margin", "Operating"), ("net_margin", "Net"))):
        fig.add_scatter(x=df.index, y=df[col], name=name, mode="lines+markers",
                        line=dict(color=SERIES[i], width=2), marker=dict(size=8), hovertemplate="%{y:.1%}")
    return _layout(fig, "Margins", "", ".0%")


def cash_chart(a: Analysis) -> go.Figure:
    df = _fin(a)
    fig = go.Figure()
    for i, (col, name) in enumerate((("ocf", "Operating cash flow"), ("fcf", "Free cash flow"), ("buybacks", "Buybacks"))):
        fig.add_bar(x=df.index, y=df[col] / 1e9, name=name, marker_color=SERIES[i],
                    marker_line_width=0, hovertemplate="%{y:$,.1f}B")
    return _layout(fig, "Cash generation and buybacks", "US$ billions")


def balance_chart(a: Analysis) -> go.Figure:
    df = _fin(a)
    fig = go.Figure()
    fig.add_scatter(x=df.index, y=df["net_cash"] / 1e9, name="Net cash", mode="lines+markers",
                    line=dict(color=SERIES[0], width=2), marker=dict(size=8), hovertemplate="%{y:$,.1f}B")
    fig.add_scatter(x=df.index, y=df["total_debt"] / 1e9, name="Total debt", mode="lines+markers",
                    line=dict(color=SERIES[1], width=2), marker=dict(size=8), hovertemplate="%{y:$,.1f}B")
    fig.add_hline(y=0, line_color=NEUTRAL, line_width=1)
    return _layout(fig, "Balance sheet: net cash and debt", "US$ billions")


def tone_index_chart(a: Analysis) -> go.Figure:
    st = a.sentiment_table()
    vals = st["tone_index"]
    colors = [POSITIVE if (v or 0) >= 0 else NEGATIVE for v in vals.fillna(0)]
    fig = go.Figure(go.Bar(x=st.index, y=vals, marker_color=colors, marker_line_width=0,
                           name="Tone index", hovertemplate="%{y:+.3f}<extra>Tone index</extra>"))
    fig.add_hline(y=0, line_color=NEUTRAL, line_width=1)
    method = "FinBERT" if a.used_finbert else "Loughran-McDonald net tone"
    return _layout(fig, f"Management tone index ({method}; MD&A + press release, -1 to +1)", "", "+.2f")


def tone_sources_chart(a: Analysis) -> go.Figure:
    st = a.sentiment_table()
    fig = go.Figure()
    series = []
    if a.used_finbert:
        series += [("mdna_finbert", "MD&A - FinBERT"), ("press_finbert", "Press release - FinBERT")]
    series += [("mdna_lm_tone", "MD&A - LM net tone")]
    if not a.used_finbert:
        series += [("press_lm_tone", "Press release - LM net tone")]
    for i, (col, name) in enumerate(series):
        if col in st:
            fig.add_scatter(x=st.index, y=st[col], name=name, mode="lines+markers",
                            line=dict(color=SERIES[i], width=2), marker=dict(size=8), hovertemplate="%{y:+.3f}")
    fig.add_hline(y=0, line_color=NEUTRAL, line_width=1)
    return _layout(fig, "Tone by document and method (-1 to +1)", "", "+.2f")


def lm_categories_chart(a: Analysis, section: str = "mdna") -> go.Figure:
    st = a.sentiment_table()
    fig = go.Figure()
    for i, (suffix, name) in enumerate((("neg_pct", "Negative"), ("unc_pct", "Uncertainty"), ("lit_pct", "Litigious"))):
        col = f"{section}_{suffix}"
        if col in st:
            fig.add_scatter(x=st.index, y=st[col], name=name, mode="lines+markers",
                            line=dict(color=SERIES[i], width=2), marker=dict(size=8), hovertemplate="%{y:.2f}%")
    where = {"mdna": "MD&A", "risk": "risk factors", "press": "press release"}[section]
    return _layout(fig, f"Loughran-McDonald word categories in {where} (% of words)", "% of words")


def risk_length_chart(a: Analysis) -> go.Figure:
    st = a.sentiment_table()
    fig = go.Figure(go.Bar(x=st.index, y=st.get("risk_words"), marker_color=SERIES[0], marker_line_width=0,
                           name="Words", hovertemplate="%{y:,.0f} words<extra></extra>"))
    return _layout(fig, "Risk-factor length (10-K: full list, 10-Q: changes)", "words")


def health_trend_chart(a: Analysis) -> go.Figure:
    ht = a.health_table()
    fig = go.Figure()
    fig.add_scatter(x=ht.index, y=ht["overall"], name="Overall", mode="lines+markers",
                    line=dict(color=SERIES[0], width=2), marker=dict(size=8), hovertemplate="%{y:.0f}/100")
    for i, p in enumerate(PILLARS, start=1):
        fig.add_scatter(x=ht.index, y=ht[p], name=p, mode="lines", visible="legendonly",
                        line=dict(color=SERIES[i % len(SERIES)], width=2), hovertemplate="%{y:.0f}")
    fig.update_yaxes(range=[0, 100])
    return _layout(fig, "Financial health score (0-100; click legend to add pillars)", "score")


def pillars_chart(a: Analysis) -> go.Figure:
    h = a.latest.health or {"pillars": {}}
    names = list(h["pillars"].keys())
    vals = [h["pillars"][n] for n in names]
    fig = go.Figure(go.Bar(x=vals, y=names, orientation="h", marker_color=SERIES[0], marker_line_width=0,
                           text=[f"{v:.0f}" if v is not None else "n/a" for v in vals], textposition="outside",
                           hovertemplate="%{y}: %{x:.0f}/100<extra></extra>"))
    fig = _layout(fig, f"Health pillars - {a.latest.fq.label}", "", height=300)
    fig.update_xaxes(range=[0, 110], type="linear", showgrid=True, gridcolor=GRID)
    fig.update_yaxes(autorange="reversed", gridcolor="rgba(0,0,0,0)")
    fig.update_layout(hovermode="closest")
    return fig


def fscore_chart(a: Analysis) -> go.Figure:
    ht = a.health_table()
    fig = go.Figure(go.Bar(x=ht.index, y=ht["fscore"], marker_color=SERIES[0], marker_line_width=0, name="F-Score",
                           hovertemplate="%{y}/9<extra>Piotroski F-Score</extra>"))
    fig.update_yaxes(range=[0, 9], dtick=1)
    return _layout(fig, "Piotroski F-Score (0-9, higher = stronger fundamentals)", "")


def all_charts(a: Analysis) -> dict[str, go.Figure]:
    return {
        "revenue": revenue_income_chart(a),
        "growth": growth_chart(a),
        "margins": margins_chart(a),
        "cash": cash_chart(a),
        "balance": balance_chart(a),
        "tone": tone_index_chart(a),
        "tone_sources": tone_sources_chart(a),
        "lm_mdna": lm_categories_chart(a, "mdna"),
        "risk_length": risk_length_chart(a),
        "health": health_trend_chart(a),
        "pillars": pillars_chart(a),
        "fscore": fscore_chart(a),
    }
