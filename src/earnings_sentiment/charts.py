"""Plotly figures shared by the dashboard and the HTML report.

Visual language (matches the EarningsPulse theme):
* smooth spline lines with soft vertical gradient fills
* capsule (fully rounded) bars, often on a faint "track" that shows the scale
* the latest quarter is highlighted and labelled with a pill
* ring gauge for the headline health score
* near-invisible axes, chip legends, one y-axis per chart

Colour rules: violet / amber / teal is the categorical order (validated for
colour-blind separation in both modes); violet vs rose encodes positive vs
negative tone. Every figure takes `mode` ("light" or "dark").
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from .analysis import Analysis
from .health import PILLARS

PALETTE = {
    "light": {
        "series": ["#7c3aed", "#f59e0b", "#0d9488"],
        "neg": "#e11d48",
        "text": "#1b1733", "muted": "#6b6788", "grid": "rgba(109,40,217,0.08)", "track": "#efecfa",
        "card": "#ffffff", "hover_bg": "#ffffff", "hover_border": "#dcd6f2",
    },
    "dark": {
        "series": ["#8b5cf6", "#d97706", "#0d9488"],
        "neg": "#f43f5e",
        "text": "#ecebf7", "muted": "#a9a4c7", "grid": "rgba(255,255,255,0.06)", "track": "#262240",
        "card": "#17142c", "hover_bg": "#221e3d", "hover_border": "#3a3463",
    },
}

# Kept for the PDF report (always light)
SERIES = PALETTE["light"]["series"]
POSITIVE = PALETTE["light"]["series"][0]
NEGATIVE = PALETTE["light"]["neg"]
NEUTRAL = "#8a85a6"

FONT = 'Inter, "SF Pro Display", system-ui, -apple-system, "Segoe UI", sans-serif'


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def _pal(mode: str) -> dict:
    return PALETTE["dark" if mode == "dark" else "light"]


def _short(label: str) -> str:
    """FY2026 Q4 -> Q4 '26 (compact, no rotation needed)."""
    try:
        fy, q = label.split()
        return f"{q} '{fy[-2:]}"
    except ValueError:
        return label


def _layout(fig: go.Figure, title: str, mode: str, subtitle: str = "", y_format: str | None = None,
            height: int = 330, legend: bool = True) -> go.Figure:
    p = _pal(mode)
    title_html = f"<b>{title}</b>" + (f"<br><span style='font-size:12px;color:{p['muted']}'>{subtitle}</span>"
                                      if subtitle else "")
    fig.update_layout(
        title=dict(text=title_html, x=0.01, xanchor="left", y=1, yref="container", yanchor="top",
                   pad=dict(t=18, l=4), font=dict(size=15, color=p["text"])),
        height=height + 14,
        margin=dict(l=8, r=22, t=100 if subtitle else 82, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1, font=dict(size=11, color=p["muted"]),
                    itemsizing="constant", bgcolor="rgba(0,0,0,0)"),
        hovermode="x unified",
        hoverlabel=dict(bgcolor=p["hover_bg"], bordercolor=p["hover_border"], namelength=-1,
                        font=dict(color=p["text"], family=FONT, size=12.5), align="left"),
        font=dict(family=FONT, size=12, color=p["muted"]),
        bargap=0.42,
        bargroupgap=0.18,
        barcornerradius="50%",
    )
    # Hover guide: a hairline in soft brand violet for line charts; bar charts get none (see _bars_hover)
    fig.update_xaxes(showspikes=True, spikemode="across", spikesnap="cursor", spikethickness=1, spikedash="solid",
                     spikecolor=_rgba(p["series"][0], 0.35))
    fig.update_yaxes(showspikes=False)
    if any(t.type == "bar" for t in fig.data):
        fig.update_xaxes(showspikes=False)
    fig.update_xaxes(showgrid=False, showline=False, zeroline=False, type="category", ticks="",
                     tickfont=dict(size=11, color=p["muted"]), automargin=True)
    fig.update_yaxes(showgrid=True, gridcolor=p["grid"], griddash="dot", zeroline=False, showline=False, ticks="",
                     tickfont=dict(size=11, color=p["muted"]), tickformat=y_format, automargin=True, nticks=5)
    return fig


def _spline(fig: go.Figure, x, y, name: str, color: str, fill: bool = True, dash: str | None = None,
            hover: str = "<b>%{y}</b>", width: float = 2.6) -> None:
    kw = {}
    if fill:
        kw = dict(fill="tozeroy", fillgradient=dict(type="vertical",
                                                    colorscale=[[0, _rgba(color, 0.0)], [1, _rgba(color, 0.28)]]))
    fig.add_scatter(x=x, y=y, name=name, mode="lines", line=dict(color=color, width=width, shape="spline",
                                                                 smoothing=1.0, dash=dash),
                    hovertemplate=hover, **kw)


def _highlight_last(fig: go.Figure, x, y, color: str, text: str, mode: str, yshift: int = 14) -> None:
    """Glowing end dot plus a pill label on the latest value."""
    if len(x) == 0 or pd.isna(y[-1]):
        return
    p = _pal(mode)
    fig.add_scatter(x=[x[-1]], y=[y[-1]], mode="markers", showlegend=False, hoverinfo="skip",
                    marker=dict(size=18, color=_rgba(color, 0.22), line=dict(width=0)))
    fig.add_scatter(x=[x[-1]], y=[y[-1]], mode="markers", showlegend=False, hoverinfo="skip",
                    marker=dict(size=9, color=color, line=dict(width=2.5, color=p["card"])))
    fig.add_annotation(x=x[-1], y=y[-1], text=f"<b>{text}</b>", showarrow=False, yshift=yshift + 8,
                       font=dict(size=11, color="#ffffff"), bgcolor=color, borderpad=5, bordercolor=color)


def _labels(a: Analysis) -> list[str]:
    return [q.fq.label for q in a.quarters]


def _fin(a: Analysis) -> pd.DataFrame:
    labels = [lbl for lbl in _labels(a) if lbl in a.financials.index]
    return a.financials.loc[labels]


# ------------------------------------------------------------------ financial charts
def revenue_income_chart(a: Analysis, mode: str = "light") -> go.Figure:
    """Net income drawn inside each revenue capsule: how much of every dollar is kept."""
    p = _pal(mode)
    df = _fin(a)
    x = [_short(i) for i in df.index]
    rev, ni = df["revenue"] / 1e9, df["net_income"] / 1e9
    fig = go.Figure()
    fig.add_bar(x=x, y=[rev.max() * 1.18] * len(x), marker_color=p["track"], width=0.56, hoverinfo="skip",
                showlegend=False)
    rev_colors = [_rgba(p["series"][0], 0.55)] * (len(x) - 1) + [p["series"][0]]
    fig.add_bar(x=x, y=rev, name="Revenue", marker_color=rev_colors, width=0.56, hovertemplate="<b>$%{y:,.1f}B</b>")
    fig.add_bar(x=x, y=ni, name="Net income", marker_color=p["series"][1], width=0.24, hovertemplate="<b>$%{y:,.1f}B</b>")
    fig.update_layout(barmode="overlay")
    fig.add_annotation(x=x[-1], y=rev.iloc[-1], text=f"<b>${rev.iloc[-1]:,.1f}B</b>", showarrow=False, yshift=16,
                       font=dict(size=11, color="#fff"), bgcolor=p["series"][0], borderpad=5)
    return _layout(fig, "Revenue & net income", mode, "US$ billions · net income shown inside revenue")


def growth_chart(a: Analysis, mode: str = "light") -> go.Figure:
    p = _pal(mode)
    df = _fin(a)
    x = [_short(i) for i in df.index]
    fig = go.Figure()
    _spline(fig, x, df["revenue_yoy"], "Revenue", p["series"][0], hover="<b>%{y:+.1%}</b>")
    _spline(fig, x, df["eps_diluted_yoy"], "Diluted EPS", p["series"][1], fill=False, hover="<b>%{y:+.1%}</b>")
    fig.add_hline(y=0, line_color=p["muted"], line_width=1, opacity=0.35)
    _highlight_last(fig, x, list(df["revenue_yoy"]), p["series"][0], f"{df['revenue_yoy'].iloc[-1]:+.1%}", mode)
    return _layout(fig, "Year-on-year growth", mode, "vs the same quarter a year earlier", ".0%")


def margins_chart(a: Analysis, mode: str = "light") -> go.Figure:
    p = _pal(mode)
    df = _fin(a)
    x = [_short(i) for i in df.index]
    fig = go.Figure()
    for i, (col, name) in enumerate((("gross_margin", "Gross"), ("operating_margin", "Operating"), ("net_margin", "Net"))):
        _spline(fig, x, df[col], name, p["series"][i], fill=(i == 0), hover="<b>%{y:.1%}</b>")
    _highlight_last(fig, x, list(df["gross_margin"]), p["series"][0], f"{df['gross_margin'].iloc[-1]:.1%}", mode)
    fig.update_yaxes(rangemode="tozero")
    return _layout(fig, "Margins", mode, "share of revenue kept at each level", ".0%")


def cash_chart(a: Analysis, mode: str = "light") -> go.Figure:
    p = _pal(mode)
    df = _fin(a)
    x = [_short(i) for i in df.index]
    fig = go.Figure()
    for i, (col, name) in enumerate((("ocf", "Operating cash flow"), ("fcf", "Free cash flow"), ("buybacks", "Buybacks"))):
        fig.add_bar(x=x, y=df[col] / 1e9, name=name, marker_color=p["series"][i], hovertemplate="<b>$%{y:,.1f}B</b>")
    fig.update_layout(barmode="group")
    return _layout(fig, "Cash generation & buybacks", mode, "US$ billions per quarter")


def balance_chart(a: Analysis, mode: str = "light") -> go.Figure:
    p = _pal(mode)
    df = _fin(a)
    x = [_short(i) for i in df.index]
    fig = go.Figure()
    _spline(fig, x, df["net_cash"] / 1e9, "Net cash", p["series"][2], hover="<b>$%{y:,.1f}B</b>")
    _spline(fig, x, df["total_debt"] / 1e9, "Total debt", p["series"][1], fill=False, dash="dot", hover="<b>$%{y:,.1f}B</b>")
    fig.add_hline(y=0, line_color=p["muted"], line_width=1, opacity=0.35)
    nc = (df["net_cash"] / 1e9).tolist()
    _highlight_last(fig, x, nc, p["series"][2], f"${nc[-1]:,.1f}B", mode)
    return _layout(fig, "Balance sheet", mode, "net cash (cash + securities − debt) vs total debt, US$ billions")


# ------------------------------------------------------------------ sentiment charts
def tone_index_chart(a: Analysis, mode: str = "light") -> go.Figure:
    p = _pal(mode)
    st = a.sentiment_table()
    x = [_short(i) for i in st.index]
    vals = st["tone_index"].astype(float)
    span = max(0.1, vals.abs().max() * 1.3)
    fig = go.Figure()
    fig.add_bar(x=x, y=[span] * len(x), marker_color=p["track"], width=0.32, hoverinfo="skip", showlegend=False)
    fig.add_bar(x=x, y=[-span] * len(x), marker_color=p["track"], width=0.32, hoverinfo="skip", showlegend=False)
    colors = []
    for i, v in enumerate(vals.fillna(0)):
        base = p["series"][0] if v >= 0 else p["neg"]
        colors.append(base if i == len(vals) - 1 else _rgba(base, 0.6))
    fig.add_bar(x=x, y=vals, marker_color=colors, width=0.32, name="Tone index",
                hovertemplate="<b>%{y:+.3f}</b><extra>Tone index</extra>")
    fig.update_layout(barmode="overlay")
    fig.add_hline(y=0, line_color=p["muted"], line_width=1, opacity=0.4)
    last = vals.iloc[-1]
    if pd.notna(last):
        fig.add_annotation(x=x[-1], y=last, text=f"<b>{last:+.2f}</b>", showarrow=False,
                           yshift=16 if last >= 0 else -16, font=dict(size=11, color="#fff"),
                           bgcolor=p["series"][0] if last >= 0 else p["neg"], borderpad=5)
    method = a.model_name
    fig.update_yaxes(range=[-span * 1.05, span * 1.25])
    return _layout(fig, "Management tone index", mode, f"{method} · MD&A + press release · −1 to +1", "+.2f",
                   legend=False)


def tone_sources_chart(a: Analysis, mode: str = "light") -> go.Figure:
    p = _pal(mode)
    st = a.sentiment_table()
    x = [_short(i) for i in st.index]
    series = []
    if a.used_finbert:
        series += [("press_finbert", f"Press release · {a.model_name}"), ("mdna_finbert", f"MD&A · {a.model_name}")]
    series += [("mdna_lm_tone", "MD&A · dictionary")]
    if not a.used_finbert:
        series += [("press_lm_tone", "Press release · dictionary")]
    fig = go.Figure()
    for i, (col, name) in enumerate(series):
        if col in st:
            _spline(fig, x, st[col], name, p["series"][i % 3], fill=(i == 0), hover="<b>%{y:+.3f}</b>")
    fig.add_hline(y=0, line_color=p["muted"], line_width=1, opacity=0.35)
    return _layout(fig, "Tone by document & method", mode, "each scored from −1 (negative) to +1 (positive)", "+.2f")


def lm_categories_chart(a: Analysis, section: str = "mdna", mode: str = "light") -> go.Figure:
    p = _pal(mode)
    st = a.sentiment_table()
    x = [_short(i) for i in st.index]
    fig = go.Figure()
    for i, (suffix, name) in enumerate((("unc_pct", "Uncertainty"), ("neg_pct", "Negative"), ("lit_pct", "Litigious"))):
        col = f"{section}_{suffix}"
        if col in st:
            _spline(fig, x, st[col], name, p["series"][i], fill=(i == 0), hover="<b>%{y:.2f}%</b>")
    where = {"mdna": "MD&A", "risk": "risk factors", "press": "press release"}[section]
    return _layout(fig, "Cautious language", mode, f"Loughran-McDonald word share in {where}, % of words")


def risk_length_chart(a: Analysis, mode: str = "light") -> go.Figure:
    p = _pal(mode)
    st = a.sentiment_table()
    x = [_short(i) for i in st.index]
    words = list(st["risk_words"]) if "risk_words" in st else [None] * len(x)
    forms = list(st["form"])
    fig = go.Figure()
    for form, color, name in (("10-K", p["series"][1], "Annual report (10-K): full list"),
                              ("10-Q", p["series"][0], "Quarterly (10-Q): changes only")):
        ys = [w if f.startswith(form) else None for w, f in zip(words, forms)]
        fig.add_bar(x=x, y=ys, name=name, marker_color=color, width=0.42, hovertemplate="<b>%{y:,.0f} words</b>")
    fig.update_layout(barmode="overlay")
    return _layout(fig, "Risk-factor section length", mode, "words · compare like with like (10-K vs 10-K)")


# ------------------------------------------------------------------ health charts
def health_gauge(a: Analysis, mode: str = "light", height: int = 300) -> go.Figure:
    p = _pal(mode)
    h = a.latest.health or {}
    score = h.get("overall") or 0
    fig = go.Figure(go.Pie(values=[score, 100 - score], hole=0.8, sort=False, direction="clockwise", rotation=0,
                           domain=dict(x=[0.1, 0.9], y=[0.0, 0.88]),
                           marker=dict(colors=[p["series"][0], p["track"]], line=dict(width=0)),
                           textinfo="none", hoverinfo="skip"))
    fig.add_annotation(text=f"<b>{score:.0f}</b>", x=0.5, y=0.5, showarrow=False, font=dict(size=44, color=p["text"]))
    fig.add_annotation(text=f"{h.get('band', 'n/a')} · out of 100", x=0.5, y=0.33, showarrow=False,
                       font=dict(size=12, color=p["muted"]))
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=70, b=10), showlegend=False,
                      paper_bgcolor="rgba(0,0,0,0)", font=dict(family=FONT),
                      title=dict(text=f"<b>Health score</b><br><span style='font-size:12px;color:{p['muted']}'>"
                                      f"{a.latest.fq.label}</span>", x=0.03, y=1, yref="container", yanchor="top",
                                 pad=dict(t=18, l=4), font=dict(size=15, color=p["text"])))
    return fig


def health_trend_chart(a: Analysis, mode: str = "light") -> go.Figure:
    p = _pal(mode)
    ht = a.health_table()
    x = [_short(i) for i in ht.index]
    fig = go.Figure()
    _spline(fig, x, ht["overall"], "Overall", p["series"][0], hover="<b>%{y:.0f}/100</b>")
    for i, pillar in enumerate(PILLARS, start=1):
        fig.add_scatter(x=x, y=ht[pillar], name=pillar, mode="lines", visible="legendonly",
                        line=dict(color=p["series"][i % 3], width=2, shape="spline"), hovertemplate="<b>%{y:.0f}</b>")
    _highlight_last(fig, x, list(ht["overall"]), p["series"][0], f"{ht['overall'].iloc[-1]:.0f}", mode)
    fig.update_yaxes(range=[0, 108])
    fig = _layout(fig, "Health over time", mode, "0–100 · click a pillar below to add it", height=350)
    fig.update_layout(legend=dict(yanchor="top", y=-0.12, xanchor="left", x=0))
    return fig


def pillars_chart(a: Analysis, mode: str = "light", height: int = 300) -> go.Figure:
    p = _pal(mode)
    h = a.latest.health or {"pillars": {}}
    names = list(h["pillars"].keys())
    vals = [h["pillars"][n] or 0 for n in names]
    fig = go.Figure()
    fig.add_bar(y=names, x=[100] * len(names), orientation="h", marker_color=p["track"], width=0.42,
                hoverinfo="skip", showlegend=False)
    fig.add_bar(y=names, x=vals, orientation="h", width=0.42, showlegend=False,
                marker=dict(color=vals, colorscale=[[0, _rgba(p["series"][0], 0.45)], [1, p["series"][0]]], cmin=0, cmax=100),
                text=[f"<b>{v:.0f}</b>" for v in vals], textposition="inside", insidetextanchor="end", textangle=0,
                constraintext="none", textfont=dict(color="#fff", size=11),
                hovertemplate="%{y}: <b>%{x:.0f}/100</b><extra></extra>")
    fig = _layout(fig, "Health pillars", mode, f"{a.latest.fq.label} · each 0–100", height=height, legend=False)
    fig.update_layout(barmode="overlay", hovermode="closest")
    fig.update_xaxes(type="linear", range=[0, 100], showticklabels=False)
    fig.update_yaxes(autorange="reversed", showgrid=False, type="category", tickfont=dict(size=12, color=p["text"]))
    return fig


def fscore_chart(a: Analysis, mode: str = "light", height: int = 330) -> go.Figure:
    p = _pal(mode)
    ht = a.health_table()
    x = [_short(i) for i in ht.index]
    vals = ht["fscore"].fillna(0).astype(float)
    fig = go.Figure()
    fig.add_bar(x=x, y=[9] * len(x), marker_color=p["track"], width=0.34, hoverinfo="skip", showlegend=False)
    colors = [_rgba(p["series"][2], 0.6)] * (len(x) - 1) + [p["series"][2]]
    fig.add_bar(x=x, y=vals, marker_color=colors, width=0.34, name="F-Score",
                hovertemplate="<b>%{y:.0f}/9</b><extra>Piotroski F-Score</extra>")
    fig.update_layout(barmode="overlay")
    fig.update_yaxes(range=[0, 10], dtick=3)
    fig.add_annotation(x=x[-1], y=vals.iloc[-1], text=f"<b>{vals.iloc[-1]:.0f}/9</b>", showarrow=False, yshift=16,
                       font=dict(size=11, color="#fff"), bgcolor=p["series"][2], borderpad=5)
    return _layout(fig, "Piotroski F-Score", mode, "0–9 · higher = stronger fundamentals", legend=False, height=height)


def sparkline_series(a: Analysis) -> dict[str, list[float]]:
    """Small trend series for the KPI cards (oldest -> newest)."""
    df = _fin(a)
    st = a.sentiment_table()
    ht = a.health_table()
    clean = lambda s: [float(v) for v in s if pd.notna(v)]  # noqa: E731
    return {
        "Revenue": clean(df["revenue"] / 1e9),
        "Diluted EPS": clean(df["eps_diluted"]),
        "Gross margin": clean(df["gross_margin"] * 100),
        "Free cash flow (TTM)": clean(df.get("fcf_ttm", pd.Series(dtype=float)) / 1e9),
        "Tone index": clean(st["tone_index"]),
        "Health score": clean(ht["overall"]) if not ht.empty else [],
    }


def all_charts(a: Analysis, mode: str = "light") -> dict[str, go.Figure]:
    return {
        "revenue": revenue_income_chart(a, mode),
        "growth": growth_chart(a, mode),
        "margins": margins_chart(a, mode),
        "cash": cash_chart(a, mode),
        "balance": balance_chart(a, mode),
        "tone": tone_index_chart(a, mode),
        "tone_sources": tone_sources_chart(a, mode),
        "lm_mdna": lm_categories_chart(a, "mdna", mode),
        "risk_length": risk_length_chart(a, mode),
        "gauge": health_gauge(a, mode),
        "health": health_trend_chart(a, mode),
        "pillars": pillars_chart(a, mode),
        "fscore": fscore_chart(a, mode),
    }
