"""Downloadable summary reports.

* HTML: self-contained single file with interactive Plotly charts (works offline).
* PDF: print-ready, charts rendered with matplotlib (no browser needed).
"""

from __future__ import annotations

import html
import io
import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from fpdf import FPDF  # noqa: E402
from jinja2 import Template  # noqa: E402

from .analysis import SECTIONS, Analysis  # noqa: E402
from .charts import NEGATIVE, POSITIVE, SERIES, all_charts  # noqa: E402
from .health import METRIC_LABELS, PERCENT_METRICS  # noqa: E402
from .narrative import build_insights, money, pct, verdict  # noqa: E402
from .theme import APP_NAME, GRADIENT, TAGLINE  # noqa: E402
from .logos import logo_html, logo_png  # noqa: E402
from .explain import CHART_GUIDES, GLOSSARY, guide_html  # noqa: E402

DISCLAIMER = (
    "Hobby research tool. Automated text and ratio analysis of public SEC filings; "
    "not investment advice. Verify figures against the linked filings before relying on them."
)


def _f(x):
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def kpis(a: Analysis) -> list[dict]:
    """Headline numbers for the latest quarter with YoY change."""
    fin = a.financials
    lbl = a.latest.fq.label
    if lbl not in fin.index:
        return []
    r = fin.loc[lbl]
    st = a.sentiment_table()
    tone = _f(st.loc[lbl, "tone_index"]) if lbl in st.index else None
    ya = a.latest.fq.year_ago().label
    tone_ya = _f(st.loc[ya, "tone_index"]) if ya in st.index else None
    h = a.latest.health or {}
    r_ya = fin.loc[ya] if ya in fin.index else {}
    gm, gm_ya = _f(r["gross_margin"]), _f(r_ya.get("gross_margin")) if len(r_ya) else None
    fcf, fcf_ya = _f(r.get("fcf_ttm")), _f(r_ya.get("fcf_ttm")) if len(r_ya) else None
    ht = a.health_table()
    h_ya = _f(ht.loc[ya, "overall"]) if ya in ht.index else None
    hv = _f(h.get("overall"))
    return [
        {"name": "Revenue", "value": money(_f(r["revenue"])), "delta": pct(_f(r["revenue_yoy"])) + " YoY"},
        {"name": "Diluted EPS", "value": f"${_f(r['eps_diluted']):.2f}" if _f(r["eps_diluted"]) is not None else "n/a",
         "delta": pct(_f(r["eps_diluted_yoy"])) + " YoY"},
        {"name": "Gross margin", "value": pct(gm, False),
         "delta": f"{(gm - gm_ya) * 100:+.1f} pts YoY" if gm is not None and gm_ya is not None else ""},
        {"name": "Free cash flow (TTM)", "value": money(fcf),
         "delta": pct((fcf - fcf_ya) / abs(fcf_ya)) + " YoY" if fcf is not None and fcf_ya else ""},
        {"name": "Tone index", "value": f"{tone:+.2f}" if tone is not None else "n/a",
         "delta": (f"{tone - tone_ya:+.2f} YoY" if tone is not None and tone_ya is not None else "")},
        {"name": "Health score", "value": f"{hv:.0f}/100" if hv is not None else "n/a",
         "delta": f"{hv - h_ya:+.0f} pts YoY" if hv is not None and h_ya is not None else h.get("band", ""),
         "note": h.get("band", "")},
    ]


def metric_value(key: str, v) -> str:
    v = _f(v)
    if v is None:
        return "n/a"
    return pct(v, signed=key.endswith("yoy"), digits=1) if key in PERCENT_METRICS else f"{v:.2f}"


# --------------------------------------------------------------------------- HTML

HTML_TEMPLATE = Template("""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ app_name }} · {{ a.company.ticker }} {{ a.latest.fq.label }}</title>
<style>
:root { --bg:#f9f9f7; --card:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781; --line:#e1e0d9;
        --good:#006300; --bad:#d03b3b; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }
main { max-width:1100px; margin:0 auto; padding:24px 16px 48px; }
.hero { border-radius:16px; padding:22px 24px; margin:0 0 18px; color:#fff;
        background:linear-gradient(120deg, {{ g[0] }} 0%, {{ g[1] }} 55%, {{ g[2] }} 100%); }
.hero .brand { font-size:12px; letter-spacing:.08em; text-transform:uppercase; opacity:.8; margin-bottom:6px; }
.hero h1 { color:#fff; } .hero .sub { color:rgba(255,255,255,.85); margin:0; }
h1 { font-size:26px; margin:0 0 4px; } h2 { font-size:19px; margin:32px 0 12px; border-bottom:1px solid var(--line); padding-bottom:6px; }
.sub { color:var(--ink2); margin:0 0 16px; }
.kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; }
.kpi { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px 14px; }
.kpi .n { color:var(--ink2); font-size:13px; } .kpi .v { font-size:22px; font-weight:600; font-variant-numeric:tabular-nums; }
.kpi .d { color:var(--muted); font-size:13px; }
.verdict { display:inline-block; padding:4px 10px; border-radius:999px; border:1px solid var(--line); font-weight:600; margin:8px 0; }
ul.ins { padding-left:0; list-style:none; } ul.ins li { padding:6px 0 6px 28px; position:relative; border-bottom:1px solid var(--line); }
ul.ins li::before { position:absolute; left:4px; font-weight:700; }
li.positive::before { content:"\\25B2"; color:var(--good); } li.negative::before { content:"\\25BC"; color:var(--bad); }
li.neutral::before { content:"\\25CF"; color:var(--muted); }
.area { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; margin-right:6px; }
.grid2 { display:grid; grid-template-columns:repeat(auto-fill,minmax(460px,1fr)); gap:12px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:8px; overflow:hidden; min-width:0; }
table { border-collapse:collapse; width:100%; font-size:14px; font-variant-numeric:tabular-nums; }
th, td { text-align:left; padding:6px 8px; border-bottom:1px solid var(--line); vertical-align:top; }
th { color:var(--ink2); font-weight:600; }
.quote { color:var(--ink2); font-style:italic; }
a { color:#2a78d6; word-break:break-all; }
.note { color:var(--muted); font-size:13px; }
details.howto { margin: 2px 8px 8px; font-size: 13px; color: var(--ink2); }
details.howto summary { cursor: pointer; color: #6d28d9; font-weight: 600; list-style: none; }
details.howto summary::before { content: "\24D8  "; }
details.howto p { margin: 6px 0; line-height: 1.5; }
.gloss { display:grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 8px; }
.gloss div { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px; font-size: 13px; }
.gloss b { display:block; color:#6d28d9; margin-bottom: 2px; }
@media (max-width:520px) { .grid2 { grid-template-columns:1fr; } }
</style></head><body><main>
<div class="hero" style="display:flex;gap:18px;align-items:center;">{{ logo }}<div>
<div class="brand">{{ app_name }} · {{ tagline }}</div>
<h1>{{ a.company.name }} ({{ a.company.ticker }})</h1>
<p class="sub">Quarterly results sentiment &amp; health report - latest quarter <b>{{ a.latest.fq.label }}</b>
(period ended {{ a.latest.period_end }}) - generated {{ a.generated_at }}</p></div></div>
<div class="kpis">{% for k in kpis %}<div class="kpi"><div class="n">{{ k.name }}</div><div class="v">{{ k.value }}</div><div class="d">{{ k.delta }}</div></div>{% endfor %}</div>

<h2>What changed</h2>
<div class="verdict">Overall direction: {{ verdict[0] }}</div> <span class="note">({{ verdict[1] }})</span>
<ul class="ins">{% for i in insights %}<li class="{{ i.signal }}"><span class="area">{{ i.area }}</span>{{ i.text }}</li>{% endfor %}</ul>

<h2>Financial trends</h2>
<div class="grid2">{% for k in ["revenue","growth","margins","cash","balance"] %}<div class="card">{{ charts[k] }}{{ guides[k] }}</div>{% endfor %}</div>

<h2>Management sentiment</h2>
<div class="grid2">{% for k in ["tone","tone_sources","lm_mdna","risk_length"] %}<div class="card">{{ charts[k] }}{{ guides[k] }}</div>{% endfor %}</div>
<h3>Evidence from {{ a.latest.fq.label }} (most positive / most negative sentences)</h3>
<table><tr><th>Document</th><th>Most positive</th><th>Most negative</th></tr>
{% for sec, d in a.latest.docs.items() if sec != "risk" %}<tr><td>{{ sections[sec] }}</td>
<td class="quote">{% for s in d.top_positive[:2] %}"{{ s.text }}"<br>{% endfor %}</td>
<td class="quote">{% for s in d.top_negative[:2] %}"{{ s.text }}"<br>{% endfor %}</td></tr>{% endfor %}</table>

<h2>Financial health</h2>
<div class="grid2">{% for k in ["gauge","pillars","fscore","health"] %}<div class="card">{{ charts[k] }}{{ guides[k] }}</div>{% endfor %}</div>
<h3>Scorecard metrics - {{ a.latest.fq.label }}</h3>
<table><tr><th>Metric</th><th>Value</th><th>Score (0-100)</th></tr>
{% for key, label in metric_labels.items() %}<tr><td>{{ label }}</td><td>{{ metric_value(key, health.metrics.get(key)) }}</td>
<td>{{ "%.0f"|format(health.metric_scores.get(key)) if health.metric_scores.get(key) is not none else "n/a" }}</td></tr>{% endfor %}</table>
{% if fscore %}<h3>Piotroski F-Score signals - {{ fscore.score }}/{{ fscore.available }}</h3>
<table><tr><th>Group</th><th>Signal</th><th>Pass</th></tr>{% for s in fscore.signals %}<tr><td>{{ s.group }}</td><td>{{ s.signal }}</td>
<td>{{ "Yes" if s["pass"] else ("No" if s["pass"] is not none else "n/a") }}</td></tr>{% endfor %}</table>{% endif %}

<h2>Quarter-by-quarter data</h2>
{{ table_html }}

<h2>Glossary</h2>
<div class="gloss">{% for t, d in glossary.items() %}<div><b>{{ t }}</b>{{ d }}</div>{% endfor %}</div>

<h2>Sources (every figure is traceable)</h2>
<table><tr><th>Document</th><th>Link</th></tr>{% for s in sources %}<tr><td>{{ s.what }}</td><td><a href="{{ s.url }}">{{ s.url }}</a></td></tr>{% endfor %}</table>
<h2>Method</h2>
<p class="note">Tone: {{ (a.model_name ~ " sentence scores (model: " ~ (a.model_id or "") ~ "), P(positive) - P(negative)") if a.used_finbert else "Loughran-McDonald net tone" }}, averaged over the MD&amp;A and the earnings press release.
Dictionary: {{ a.dictionary_source }} (Loughran &amp; McDonald 2011). Financials: SEC XBRL company facts; Q4 derived as full year minus nine months.
Health: transparent five-pillar scorecard plus Piotroski (2000) F-Score on a trailing-twelve-month basis. Full methodology: docs/METHODOLOGY.md in the project repository.</p>
{% if a.warnings %}<p class="note"><b>Data notes:</b> {{ a.warnings|join("; ") }}</p>{% endif %}
<p class="note">{{ disclaimer }}</p>
</main>
<script>
// Charts are drawn while the page is still loading; refit them once the grid is final.
window.addEventListener("load", function () {
  if (typeof Plotly === "undefined") return;
  document.querySelectorAll(".js-plotly-plot").forEach(function (el) { Plotly.Plots.resize(el); });
});
</script>
</body></html>""")


def data_table(a: Analysis):
    cols = {
        "revenue": "Revenue", "revenue_yoy": "Rev YoY", "net_income": "Net income", "eps_diluted": "EPS",
        "gross_margin": "Gross m.", "operating_margin": "Op. m.", "fcf": "FCF",
    }
    labels = [q.fq.label for q in a.quarters if q.fq.label in a.financials.index]
    fin = a.financials.loc[labels, list(cols)]
    st = a.sentiment_table()
    ht = a.health_table()
    rows = []
    for lbl in labels:
        r = fin.loc[lbl]
        rows.append({
            "Quarter": lbl,
            "Revenue": money(_f(r["revenue"])),
            "Rev YoY": pct(_f(r["revenue_yoy"])),
            "Net income": money(_f(r["net_income"])),
            "EPS": f"{_f(r['eps_diluted']):.2f}" if _f(r["eps_diluted"]) is not None else "n/a",
            "Gross m.": pct(_f(r["gross_margin"]), False),
            "Op. m.": pct(_f(r["operating_margin"]), False),
            "FCF": money(_f(r["fcf"])),
            "Tone": f"{_f(st.loc[lbl, 'tone_index']):+.2f}" if lbl in st.index and _f(st.loc[lbl, "tone_index"]) is not None else "n/a",
            "Health": f"{_f(ht.loc[lbl, 'overall']):.0f}" if lbl in ht.index and _f(ht.loc[lbl, "overall"]) is not None else "n/a",
        })
    return rows


def build_html(a: Analysis, offline: bool = True) -> str:
    """offline=True embeds plotly.js (~4 MB) so the file works without internet;
    offline=False loads it from a CDN (used for small snapshots committed to git)."""
    figs = all_charts(a)
    rendered = {}
    first = True
    for k, fig in figs.items():
        rendered[k] = fig.to_html(full_html=False, include_plotlyjs=((True if offline else "cdn") if first else False),
                                  default_width="100%", default_height=f"{fig.layout.height or 360}px",
                                  config={"displaylogo": False, "responsive": True})
        first = False
    rows = data_table(a)
    head = "".join(f"<th>{html.escape(c)}</th>" for c in rows[0]) if rows else ""
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in r.values()) + "</tr>" for r in rows)
    insights = build_insights(a)
    return HTML_TEMPLATE.render(
        a=a, kpis=kpis(a), insights=insights, verdict=verdict(insights), charts=rendered,
        sections=SECTIONS, health=a.latest.health or {"metrics": {}, "metric_scores": {}},
        fscore=a.latest.fscore, metric_labels=METRIC_LABELS, metric_value=metric_value,
        table_html=f"<table><tr>{head}</tr>{body}</table>", sources=a.sources(), disclaimer=DISCLAIMER,
        app_name=APP_NAME, tagline=TAGLINE, g=GRADIENT, logo=logo_html(a.company.ticker, 60, 16),
        guides={k: guide_html(k) for k in figs}, glossary=GLOSSARY,
    )


# --------------------------------------------------------------------------- PDF


def _ascii(s: str) -> str:
    """Core PDF fonts are Latin-1 only; map common typography to safe characters."""
    rep = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "…": "...", "®": "(R)", "™": "(TM)",
           " ": " ", "•": "-", "▲": "+", "▼": "-"}
    for k, v in rep.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")


def _mpl_style(ax, title: str, subtitle: str = ""):
    ax.set_title(title, loc="left", fontsize=10.5, color="#1b1733", fontweight="bold", pad=18 if subtitle else 8)
    if subtitle:
        ax.text(0, 1.03, subtitle, transform=ax.transAxes, fontsize=7.5, color="#6b6788")
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.tick_params(colors="#6b6788", labelsize=7, length=0)
    ax.grid(axis="y", color="#e9e5f7", linewidth=0.7, linestyle=(0, (2, 3)))
    ax.set_axisbelow(True)


def _png(fig) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf


def _round_bar(ax, x, height, width, color, bottom=0.0, zorder=2):
    """Bar with a fully rounded end (capsule look), drawn as a fancy box."""
    from matplotlib.patches import FancyBboxPatch

    if height is None or height != height or height == 0:
        return
    ymin, ymax = ax.get_ylim()
    xmin, xmax = ax.get_xlim()
    bbox = ax.get_window_extent()
    # rounding radius in data units, matched in both axes so the end is a semicircle
    rx = width / 2
    ry = rx * (ymax - ymin) / (xmax - xmin) * bbox.width / bbox.height
    r = min(rx, abs(height) / 2)
    patch = FancyBboxPatch((x - width / 2, min(bottom, bottom + height)), width, abs(height),
                           boxstyle=f"round,pad=0,rounding_size={r}", mutation_aspect=ry / rx if rx else 1,
                           linewidth=0, facecolor=color, zorder=zorder)
    ax.add_patch(patch)


def _smooth(xs, ys, n=24):
    """Catmull-Rom spline through the points (no SciPy needed)."""
    import numpy as np

    pts = [(x, y) for x, y in zip(xs, ys) if y == y]
    if len(pts) < 3:
        return [p[0] for p in pts], [p[1] for p in pts]
    P = np.array(pts, dtype=float)
    P = np.vstack([P[0], P, P[-1]])
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for t in np.linspace(0, 1, n, endpoint=False):
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(P[-2])
    out = np.array(out)
    return out[:, 0], out[:, 1]


def _area_line(ax, x, y, color, label, fill=True):
    sx, sy = _smooth(x, y)
    ax.plot(sx, sy, color=color, lw=2.2, label=label, solid_capstyle="round", zorder=3)
    if fill and len(sx):
        ax.fill_between(sx, sy, min(0, min(sy)), color=color, alpha=0.12, linewidth=0, zorder=2)


def _pdf_charts(a: Analysis) -> list[io.BytesIO]:
    violet, amber, teal = SERIES
    track = "#efecfa"
    labels = [q.fq.label for q in a.quarters if q.fq.label in a.financials.index]
    short = [f"{lbl.split()[1]} '{lbl.split()[0][-2:]}" for lbl in labels]
    fin = a.financials.loc[labels]
    stab = a.sentiment_table()
    st = stab.loc[[lbl for lbl in labels if lbl in stab.index]]
    ht = a.health_table()
    x = list(range(len(labels)))
    out = []

    # Revenue capsules on tracks, net income inside
    fig, ax = plt.subplots(figsize=(7.2, 2.7))
    rev, ni = (fin["revenue"] / 1e9).tolist(), (fin["net_income"] / 1e9).tolist()
    top = max(rev) * 1.18
    ax.set_xlim(-0.6, len(x) - 0.4)
    ax.set_ylim(0, top * 1.05)
    for i in x:
        _round_bar(ax, i, top, 0.52, track, zorder=1)
        _round_bar(ax, i, rev[i], 0.52, violet if i == x[-1] else "#b9a2f5", zorder=2)
        _round_bar(ax, i, ni[i], 0.22, amber, zorder=3)
    ax.text(x[-1], rev[-1] + top * 0.04, f"${rev[-1]:,.1f}B", ha="center", fontsize=7.5, color="white",
            fontweight="bold", bbox=dict(boxstyle="round,pad=0.35", fc=violet, ec="none"), zorder=4)
    ax.set_xticks(x, short)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=violet, label="Revenue"), Patch(color=amber, label="Net income")],
              fontsize=7, frameon=False, ncol=2, loc="lower right", bbox_to_anchor=(1, 1.0))
    _mpl_style(ax, "Revenue & net income", "US$ billions · net income shown inside revenue")
    out.append(_png(fig))

    # Margins as smooth lines with soft fill
    fig, ax = plt.subplots(figsize=(7.2, 2.6))
    for col, name, color, fill in (("gross_margin", "Gross", violet, True), ("operating_margin", "Operating", amber, False),
                                   ("net_margin", "Net", teal, False)):
        _area_line(ax, x, (fin[col] * 100).tolist(), color, name, fill)
    ax.set_xticks(x, short)
    ax.set_ylim(0, None)
    ax.legend(fontsize=7, frameon=False, ncol=3, loc="lower right", bbox_to_anchor=(1, 1.0))
    _mpl_style(ax, "Margins", "share of revenue kept at each level, %")
    out.append(_png(fig))

    # Tone: diverging capsules on tracks
    fig, ax = plt.subplots(figsize=(7.2, 2.6))
    tone = st["tone_index"].astype(float).tolist()
    span = max(0.1, max(abs(v) for v in tone if v == v) * 1.3)
    ax.set_xlim(-0.6, len(tone) - 0.4)
    ax.set_ylim(-span * 1.05, span * 1.3)
    for i, v in enumerate(tone):
        _round_bar(ax, i, span, 0.3, track, zorder=1)
        _round_bar(ax, i, -span, 0.3, track, zorder=1)
        base = violet if (v or 0) >= 0 else NEGATIVE
        _round_bar(ax, i, v, 0.3, base if i == len(tone) - 1 else (base + "99"), zorder=2)
    ax.axhline(0, color="#c9c3e3", lw=0.8, zorder=1)
    ax.set_xticks(range(len(tone)), [f"{lbl.split()[1]} '{lbl.split()[0][-2:]}" for lbl in st.index])
    method = a.model_name
    _mpl_style(ax, "Management tone index", f"{method} · MD&A + press release · -1 to +1")
    out.append(_png(fig))

    # Health trend
    fig, ax = plt.subplots(figsize=(7.2, 2.6))
    if not ht.empty:
        hx = list(range(len(ht)))
        _area_line(ax, hx, ht["overall"].tolist(), violet, "Health score")
        ax.scatter([hx[-1]], [ht["overall"].iloc[-1]], s=40, color=violet, edgecolor="white", linewidth=1.5, zorder=4)
        ax.set_xticks(hx, [f"{lbl.split()[1]} '{lbl.split()[0][-2:]}" for lbl in ht.index])
        ax.set_ylim(0, 105)
    _mpl_style(ax, "Financial health score", "0-100")
    out.append(_png(fig))
    return out


class _PDF(FPDF):
    def __init__(self, title: str):
        super().__init__(format="A4")
        self.title_text = title
        self.set_auto_page_break(auto=True, margin=15)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", size=7)
        self.set_text_color(137, 135, 129)
        self.cell(0, 5, _ascii(f"{APP_NAME} - {self.title_text} - page {self.page_no()} - {DISCLAIMER[:80]}..."), align="C")


def build_pdf(a: Analysis) -> bytes:
    pdf = _PDF(f"{a.company.ticker} {a.latest.fq.label}")
    pdf.add_page()
    W = pdf.w - pdf.l_margin - pdf.r_margin

    def h1(t):
        pdf.set_font("Helvetica", "B", 18)
        pdf.set_text_color(11, 11, 11)
        pdf.multi_cell(W, 9, _ascii(t), new_x="LMARGIN", new_y="NEXT")

    def h2(t):
        if pdf.get_y() > pdf.h - 45:  # avoid orphaned headings at the page bottom
            pdf.add_page()
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(11, 11, 11)
        pdf.cell(W, 8, _ascii(t), new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(225, 224, 217)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + W, pdf.get_y())
        pdf.ln(2)

    def para(t, size=10, color=(11, 11, 11), style=""):
        pdf.set_font("Helvetica", style, size)
        pdf.set_text_color(*color)
        pdf.multi_cell(W, 5, _ascii(t), new_x="LMARGIN", new_y="NEXT")

    # brand band
    pdf.set_fill_color(76, 29, 149)
    pdf.rect(0, 0, pdf.w, 4, style="F")
    pdf.set_fill_color(109, 40, 217)
    pdf.rect(pdf.w * 0.55, 0, pdf.w * 0.45, 4, style="F")
    logo = logo_png(a.company.ticker)
    if logo:
        try:  # top-right, beside the brand line and title, clear of the subtitle
            pdf.image(io.BytesIO(logo), x=pdf.l_margin + W - 12, y=pdf.get_y() + 1, w=12, h=12, keep_aspect_ratio=True)
        except Exception:  # an unreadable image should never break the report
            pass
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(109, 40, 217)
    pdf.cell(W - 16, 5, _ascii(f"{APP_NAME.upper()}  |  {TAGLINE}"), new_x="LMARGIN", new_y="NEXT")
    h1(f"{a.company.name} ({a.company.ticker})")
    para(f"Quarterly results sentiment & health report - latest quarter {a.latest.fq.label} "
         f"(period ended {a.latest.period_end}) - generated {a.generated_at}", 9, (82, 81, 78))
    pdf.ln(3)

    # KPI grid: 3 per row
    ks = kpis(a)
    cw = W / 3
    for i, k in enumerate(ks):
        if i % 3 == 0 and i:
            pdf.ln(17)
        x0, y0 = pdf.l_margin + (i % 3) * cw, pdf.get_y()
        pdf.set_draw_color(225, 224, 217)
        pdf.rect(x0 + 1, y0, cw - 2, 15)
        pdf.set_xy(x0 + 3, y0 + 1)
        pdf.set_font("Helvetica", size=8); pdf.set_text_color(82, 81, 78)
        pdf.cell(cw - 6, 4, _ascii(k["name"]))
        pdf.set_xy(x0 + 3, y0 + 5)
        pdf.set_font("Helvetica", "B", 12); pdf.set_text_color(11, 11, 11)
        pdf.cell(cw - 6, 5, _ascii(k["value"]))
        pdf.set_xy(x0 + 3, y0 + 10)
        pdf.set_font("Helvetica", size=7); pdf.set_text_color(137, 135, 129)
        pdf.cell(cw - 6, 4, _ascii(k["delta"]))
        pdf.set_xy(pdf.l_margin, y0)
    pdf.ln(19)

    insights = build_insights(a)
    v = verdict(insights)
    h2("What changed")
    para(f"Overall direction: {v[0]} ({v[1]})", 10, style="B")
    pdf.ln(1)
    marks = {"positive": ("+", (0, 99, 0)), "negative": ("-", (208, 59, 59)), "neutral": ("o", (137, 135, 129))}
    for ins in insights:
        sym, col = marks[ins.signal]
        pdf.set_font("Helvetica", "B", 10); pdf.set_text_color(*col)
        pdf.cell(6, 5, sym)
        pdf.set_font("Helvetica", size=9); pdf.set_text_color(11, 11, 11)
        pdf.multi_cell(W - 6, 5, _ascii(f"[{ins.area}] {ins.text}"), new_x="LMARGIN", new_y="NEXT")

    h2("Charts")
    for img in _pdf_charts(a):
        if pdf.get_y() > pdf.h - 80:
            pdf.add_page()
        pdf.image(img, w=W)
        pdf.ln(2)

    h2(f"Evidence from {a.latest.fq.label}")
    for sec, d in a.latest.docs.items():
        if sec == "risk":
            continue
        para(SECTIONS[sec], 10, style="B")
        for s in d.get("top_positive", [])[:2]:
            para(f'(+) "{s["text"]}"', 8, (82, 81, 78))
        for s in d.get("top_negative", [])[:2]:
            para(f'(-) "{s["text"]}"', 8, (82, 81, 78))
        pdf.ln(1)

    h2(f"Health scorecard - {a.latest.fq.label}")
    h = a.latest.health or {"metrics": {}, "metric_scores": {}}
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(W * 0.6, 6, "Metric", border="B"); pdf.cell(W * 0.2, 6, "Value", border="B"); pdf.cell(W * 0.2, 6, "Score", border="B", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=9)
    for key, label in METRIC_LABELS.items():
        sc = h["metric_scores"].get(key)
        pdf.cell(W * 0.6, 6, _ascii(label)); pdf.cell(W * 0.2, 6, metric_value(key, h["metrics"].get(key)))
        pdf.cell(W * 0.2, 6, f"{sc:.0f}" if sc is not None else "n/a", new_x="LMARGIN", new_y="NEXT")
    if a.latest.fscore:
        fs = a.latest.fscore
        pdf.ln(2)
        para(f"Piotroski F-Score: {fs['score']}/{fs['available']}", 10, style="B")
        for s in fs["signals"]:
            mark = "Yes" if s["pass"] else ("No" if s["pass"] is not None else "n/a")
            para(f"  {mark:>3}  {s['signal']}", 8, (82, 81, 78))

    h2("Quarter-by-quarter")
    rows = data_table(a)
    if rows:
        cols = list(rows[0])
        widths = [W * w for w in (0.11, 0.1, 0.09, 0.11, 0.07, 0.09, 0.09, 0.11, 0.1, 0.09)]
        pdf.set_font("Helvetica", "B", 8)
        for c, wd in zip(cols, widths):
            pdf.cell(wd, 6, c, border="B")
        pdf.ln()
        pdf.set_font("Helvetica", size=8)
        for r in rows:
            for c, wd in zip(cols, widths):
                pdf.cell(wd, 5.5, _ascii(str(r[c])))
            pdf.ln()

    h2("How to read the charts")
    for gkey in ("revenue", "margins", "tone", "health"):
        g = CHART_GUIDES[gkey]
        para(g["title"], 9, style="B")
        para(f"{g['read']} {g['good']}", 8, (82, 81, 78))
        pdf.ln(1)

    h2("Glossary")
    for term, definition in GLOSSARY.items():
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(109, 40, 217)
        pdf.multi_cell(W, 4, _ascii(term), new_x="LMARGIN", new_y="NEXT")
        para(definition, 8, (82, 81, 78))

    h2("Sources")
    for s in a.sources():
        para(s["what"], 8, style="B")
        pdf.set_font("Helvetica", size=7); pdf.set_text_color(42, 120, 214)
        pdf.multi_cell(W, 4, _ascii(s["url"]), link=s["url"], new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    para("Method: " + (f"{a.model_name} sentence-level scores (ONNX, model id {a.model_id})" if a.used_finbert else "Loughran-McDonald net tone")
         + f"; dictionary: {a.dictionary_source} (Loughran & McDonald 2011); financials from SEC XBRL company facts; "
         "health = five-pillar scorecard + Piotroski (2000) F-Score on a TTM basis.", 8, (82, 81, 78))
    if a.warnings:
        para("Data notes: " + "; ".join(a.warnings), 8, (137, 135, 129))
    para(DISCLAIMER, 8, (137, 135, 129))
    return bytes(pdf.output())
