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
    return [
        {"name": "Revenue", "value": money(_f(r["revenue"])), "delta": pct(_f(r["revenue_yoy"])) + " YoY"},
        {"name": "Diluted EPS", "value": f"${_f(r['eps_diluted']):.2f}" if _f(r["eps_diluted"]) is not None else "n/a",
         "delta": pct(_f(r["eps_diluted_yoy"])) + " YoY"},
        {"name": "Gross margin", "value": pct(_f(r["gross_margin"]), False), "delta": ""},
        {"name": "Free cash flow (TTM)", "value": money(_f(r.get("fcf_ttm"))), "delta": ""},
        {"name": "Tone index", "value": f"{tone:+.2f}" if tone is not None else "n/a",
         "delta": (f"{tone - tone_ya:+.2f} YoY" if tone is not None and tone_ya is not None else "")},
        {"name": "Health score", "value": f"{h.get('overall'):.0f}/100" if h.get("overall") is not None else "n/a",
         "delta": h.get("band", "")},
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
@media (prefers-color-scheme: dark) { :root { --bg:#0d0d0d; --card:#1a1a19; --ink:#f0efec; --ink2:#c3c2b7;
        --line:#2c2c2a; --good:#0ca30c; --bad:#e66767; } }
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
@media (max-width:520px) { .grid2 { grid-template-columns:1fr; } }
/* chart text follows the page theme (plotly writes fixed inline colors) */
.js-plotly-plot .plotly .main-svg text { fill: var(--ink2) !important; }
.js-plotly-plot .plotly .main-svg .gtitle { fill: var(--ink) !important; }
</style></head><body><main>
<div class="hero"><div class="brand">{{ app_name }} · {{ tagline }}</div>
<h1>{{ a.company.name }} ({{ a.company.ticker }})</h1>
<p class="sub">Quarterly results sentiment &amp; health report - latest quarter <b>{{ a.latest.fq.label }}</b>
(period ended {{ a.latest.period_end }}) - generated {{ a.generated_at }}</p></div>
<div class="kpis">{% for k in kpis %}<div class="kpi"><div class="n">{{ k.name }}</div><div class="v">{{ k.value }}</div><div class="d">{{ k.delta }}</div></div>{% endfor %}</div>

<h2>What changed</h2>
<div class="verdict">Overall direction: {{ verdict[0] }}</div> <span class="note">({{ verdict[1] }})</span>
<ul class="ins">{% for i in insights %}<li class="{{ i.signal }}"><span class="area">{{ i.area }}</span>{{ i.text }}</li>{% endfor %}</ul>

<h2>Financial trends</h2>
<div class="grid2">{% for k in ["revenue","growth","margins","cash","balance"] %}<div class="card">{{ charts[k] }}</div>{% endfor %}</div>

<h2>Management sentiment</h2>
<div class="grid2">{% for k in ["tone","tone_sources","lm_mdna","risk_length"] %}<div class="card">{{ charts[k] }}</div>{% endfor %}</div>
<h3>Evidence from {{ a.latest.fq.label }} (most positive / most negative sentences)</h3>
<table><tr><th>Document</th><th>Most positive</th><th>Most negative</th></tr>
{% for sec, d in a.latest.docs.items() if sec != "risk" %}<tr><td>{{ sections[sec] }}</td>
<td class="quote">{% for s in d.top_positive[:2] %}"{{ s.text }}"<br>{% endfor %}</td>
<td class="quote">{% for s in d.top_negative[:2] %}"{{ s.text }}"<br>{% endfor %}</td></tr>{% endfor %}</table>

<h2>Financial health</h2>
<div class="grid2">{% for k in ["health","pillars","fscore"] %}<div class="card">{{ charts[k] }}</div>{% endfor %}</div>
<h3>Scorecard metrics - {{ a.latest.fq.label }}</h3>
<table><tr><th>Metric</th><th>Value</th><th>Score (0-100)</th></tr>
{% for key, label in metric_labels.items() %}<tr><td>{{ label }}</td><td>{{ metric_value(key, health.metrics.get(key)) }}</td>
<td>{{ "%.0f"|format(health.metric_scores.get(key)) if health.metric_scores.get(key) is not none else "n/a" }}</td></tr>{% endfor %}</table>
{% if fscore %}<h3>Piotroski F-Score signals - {{ fscore.score }}/{{ fscore.available }}</h3>
<table><tr><th>Group</th><th>Signal</th><th>Pass</th></tr>{% for s in fscore.signals %}<tr><td>{{ s.group }}</td><td>{{ s.signal }}</td>
<td>{{ "Yes" if s["pass"] else ("No" if s["pass"] is not none else "n/a") }}</td></tr>{% endfor %}</table>{% endif %}

<h2>Quarter-by-quarter data</h2>
{{ table_html }}

<h2>Sources (every figure is traceable)</h2>
<table><tr><th>Document</th><th>Link</th></tr>{% for s in sources %}<tr><td>{{ s.what }}</td><td><a href="{{ s.url }}">{{ s.url }}</a></td></tr>{% endfor %}</table>
<h2>Method</h2>
<p class="note">Tone: {{ "FinBERT (Araci 2019, ProsusAI/finbert) sentence scores, P(positive) - P(negative)" if a.used_finbert else "Loughran-McDonald net tone" }}, averaged over the MD&amp;A and the earnings press release.
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
        app_name=APP_NAME, tagline=TAGLINE, g=GRADIENT,
    )


# --------------------------------------------------------------------------- PDF


def _ascii(s: str) -> str:
    """Core PDF fonts are Latin-1 only; map common typography to safe characters."""
    rep = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "…": "...", "®": "(R)", "™": "(TM)",
           " ": " ", "•": "-", "▲": "+", "▼": "-"}
    for k, v in rep.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")


def _mpl_style(ax, title: str):
    ax.set_title(title, loc="left", fontsize=10, color="#0b0b0b")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#c3c2b7")
    ax.tick_params(colors="#52514e", labelsize=7)
    ax.grid(axis="y", color="#e1e0d9", linewidth=0.6)
    ax.set_axisbelow(True)


def _png(fig) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf


def _pdf_charts(a: Analysis) -> list[io.BytesIO]:
    labels = [q.fq.label for q in a.quarters if q.fq.label in a.financials.index]
    short = [lbl.replace("FY20", "'").replace(" ", "\n") for lbl in labels]
    fin = a.financials.loc[labels]
    st = a.sentiment_table().loc[[lbl for lbl in labels if lbl in a.sentiment_table().index]]
    ht = a.health_table()
    x = range(len(labels))
    out = []

    fig, ax = plt.subplots(figsize=(7.2, 2.6))
    w = 0.38
    ax.bar([i - w / 2 for i in x], fin["revenue"] / 1e9, w, color=SERIES[0], label="Revenue")
    ax.bar([i + w / 2 for i in x], fin["net_income"] / 1e9, w, color=SERIES[1], label="Net income")
    ax.set_xticks(list(x), short)
    ax.set_ylabel("US$ billions", fontsize=7, color="#52514e")
    ax.legend(fontsize=7, frameon=False, ncol=2, loc="upper left")
    _mpl_style(ax, "Revenue and net income per quarter")
    out.append(_png(fig))

    fig, ax = plt.subplots(figsize=(7.2, 2.6))
    for i, (col, name) in enumerate((("gross_margin", "Gross"), ("operating_margin", "Operating"), ("net_margin", "Net"))):
        ax.plot(list(x), fin[col] * 100, color=SERIES[i], lw=2, marker="o", ms=4, label=name)
    ax.set_xticks(list(x), short)
    ax.set_ylabel("% of revenue", fontsize=7, color="#52514e")
    ax.legend(fontsize=7, frameon=False, ncol=3, loc="upper left")
    _mpl_style(ax, "Margins")
    out.append(_png(fig))

    fig, ax = plt.subplots(figsize=(7.2, 2.6))
    tone = st["tone_index"].astype(float)
    ax.bar(list(range(len(tone))), tone, color=[POSITIVE if v >= 0 else NEGATIVE for v in tone.fillna(0)])
    ax.axhline(0, color="#898781", lw=0.8)
    ax.set_xticks(list(range(len(tone))), [lbl.replace("FY20", "'").replace(" ", "\n") for lbl in st.index])
    method = "FinBERT" if a.used_finbert else "LM net tone"
    _mpl_style(ax, f"Management tone index ({method}, -1 to +1)")
    out.append(_png(fig))

    fig, ax = plt.subplots(figsize=(7.2, 2.6))
    if not ht.empty:
        ax.plot(list(range(len(ht))), ht["overall"], color=SERIES[0], lw=2, marker="o", ms=4, label="Health score")
        ax.set_xticks(list(range(len(ht))), [lbl.replace("FY20", "'").replace(" ", "\n") for lbl in ht.index])
        ax.set_ylim(0, 100)
    _mpl_style(ax, "Financial health score (0-100)")
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
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(109, 40, 217)
    pdf.cell(W, 5, _ascii(f"{APP_NAME.upper()}  |  {TAGLINE}"), new_x="LMARGIN", new_y="NEXT")
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

    h2("Sources")
    for s in a.sources():
        para(s["what"], 8, style="B")
        pdf.set_font("Helvetica", size=7); pdf.set_text_color(42, 120, 214)
        pdf.multi_cell(W, 4, _ascii(s["url"]), link=s["url"], new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    para("Method: " + ("FinBERT sentence-level scores (Araci 2019)" if a.used_finbert else "Loughran-McDonald net tone")
         + f"; dictionary: {a.dictionary_source} (Loughran & McDonald 2011); financials from SEC XBRL company facts; "
         "health = five-pillar scorecard + Piotroski (2000) F-Score on a TTM basis.", 8, (82, 81, 78))
    if a.warnings:
        para("Data notes: " + "; ".join(a.warnings), 8, (137, 135, 129))
    para(DISCLAIMER, 8, (137, 135, 129))
    return bytes(pdf.output())
