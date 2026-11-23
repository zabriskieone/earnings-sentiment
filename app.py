"""Interactive dashboard: quarterly earnings sentiment & financial health.

Run locally:   streamlit run app.py
Run in Docker: docker compose up      (then open http://localhost:8501)
"""

from __future__ import annotations

import html
import io
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))  # works without `pip install -e .`

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from earnings_sentiment import charts, config, theme  # noqa: E402
from earnings_sentiment.analysis import SECTIONS, Analysis, analyze  # noqa: E402
from earnings_sentiment.edgar import EdgarClient, EdgarError  # noqa: E402
from earnings_sentiment.health import METRIC_LABELS  # noqa: E402
from earnings_sentiment.narrative import build_insights, verdict  # noqa: E402
from earnings_sentiment.report import DISCLAIMER, build_html, build_pdf, data_table, kpis, metric_value  # noqa: E402
from earnings_sentiment.sentiment import finbert_available  # noqa: E402

st.set_page_config(page_title=f"{theme.APP_NAME} · {theme.TAGLINE}", page_icon=theme.APP_ICON, layout="wide")

# ----------------------------------------------------------------------------- light / dark mode
if "theme_mode" not in st.session_state:
    # start in whatever the browser/OS is using; the toggle takes over from there
    browser_mode = getattr(getattr(st.context, "theme", None), "type", None)
    st.session_state["theme_mode"] = browser_mode if browser_mode in ("light", "dark") else "light"
MODE = st.session_state["theme_mode"]
if theme.current_mode() != MODE or not st.session_state.get("_palette_applied"):
    theme.apply_palette(MODE)
    st.session_state["_palette_applied"] = True
    st.rerun()
st.markdown(theme.css(MODE), unsafe_allow_html=True)


def _toggle_theme() -> None:
    # Only record the choice here: Streamlit sends the theme at the start of a run, so the
    # check at the top of the script applies the palette and triggers one more run.
    st.session_state["theme_mode"] = "light" if st.session_state["theme_mode"] == "dark" else "dark"


def top_bar() -> None:
    """Right-aligned light/dark switch shown above every page."""
    _, right = st.columns([20, 1])
    dark = st.session_state["theme_mode"] == "dark"
    right.button("", icon=":material/light_mode:" if dark else ":material/dark_mode:", key="theme_toggle",
                 help="Switch to light mode" if dark else "Switch to dark mode", on_click=_toggle_theme,
                 type="tertiary")

SIGNAL_ICON = {"positive": ":green[▲]", "negative": ":red[▼]", "neutral": ":gray[●]"}


# ----------------------------------------------------------------------------- cached work
@st.cache_resource(show_spinner=False, ttl=24 * 3600)
def company_options(user_agent: str) -> list[str]:
    companies = EdgarClient(user_agent).company_list()
    seen, out = set(), []
    for c in companies:
        if c.ticker not in seen:
            seen.add(c.ticker)
            out.append(f"{c.ticker} — {c.name}")
    return out


@st.cache_resource(show_spinner=False)
def _results_store() -> dict:
    """Process-wide store of finished analyses (shared across browser sessions).

    The analysis itself can't live inside a cached function because it updates
    the progress bar; SEC downloads and sentiment scores are also cached on disk.
    """
    return {}


RESULT_TTL_SECONDS = 6 * 3600


def run_analysis(ticker: str, quarters: int, use_finbert: bool, user_agent: str, progress=None) -> Analysis:
    store = _results_store()
    key = (ticker, quarters, use_finbert)
    hit = store.get(key)
    if hit and time.time() - hit[0] < RESULT_TTL_SECONDS:
        return hit[1]
    result = analyze(ticker, quarters, use_finbert=use_finbert, user_agent=user_agent, progress=progress)
    if len(store) >= 20:
        store.pop(min(store, key=lambda k: store[k][0]))
    store[key] = (time.time(), result)
    return result


@st.cache_data(show_spinner=False, max_entries=20)
def html_report(_a: Analysis, key: str) -> str:
    return build_html(_a, offline=True)


@st.cache_data(show_spinner=False, max_entries=20)
def pdf_report(_a: Analysis, key: str) -> bytes:
    return build_pdf(_a)


# ----------------------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown(
        f'<div class="ep-brand"><div class="ep-logo">{theme.APP_ICON}</div>'
        f'<div class="ep-name">{theme.APP_NAME}</div></div><div class="ep-tag">{theme.TAGLINE}</div>',
        unsafe_allow_html=True,
    )

    ua = st.text_input(
        "Your name and e-mail (sent to SEC)",
        value=st.session_state.get("ua", config.SEC_USER_AGENT),
        placeholder="Jane Doe jane@example.com",
        help="SEC asks every automated client to identify itself "
             "(https://www.sec.gov/os/accessing-edgar-data). It is only sent to sec.gov. "
             "Set SEC_USER_AGENT in a .env file to skip this step.",
    )
    st.session_state["ua"] = ua
    ua_ok = config.valid_user_agent(ua)
    if not ua_ok:
        if "@" in ua and len(ua.split()) < 2:
            st.warning("Almost there: add your **name before the e-mail**, e.g. `Jane Doe jane@example.com`. "
                       "SEC asks for both.")
        elif ua.strip() and "@" not in ua:
            st.warning("Add a contact **e-mail** after your name, e.g. `Jane Doe jane@example.com`.")
        else:
            st.info("Enter your name and e-mail to start, e.g. `Jane Doe jane@example.com`.")

    choice = None
    if ua_ok:
        try:
            options = company_options(ua)
            default = next((i for i, o in enumerate(options) if o.startswith("AAPL ")), 0)
            choice = st.selectbox("Company (type to search ticker or name)", options, index=default)
        except EdgarError as exc:
            st.error(str(exc))

    quarters = st.slider("Quarters to analyse", 4, 12, 8,
                         help="More quarters = longer history; each new quarter takes a few seconds.")
    fb_ok = finbert_available()
    use_fb = st.toggle("Use FinBERT (context-aware model)", value=fb_ok, disabled=not fb_ok,
                       help="Scores every sentence with a finance-tuned language model. First use downloads "
                            "about 440 MB. Off = Loughran-McDonald dictionary only (fast)."
                            + ("" if fb_ok else " Not available: install torch and transformers."))
    go = st.button("Analyse", type="primary", width="stretch", disabled=choice is None)
    st.divider()
    st.caption(DISCLAIMER)

if go and choice:
    st.session_state["request"] = (choice.split(" — ")[0], quarters, use_fb)

req = st.session_state.get("request")
top_bar()
if not req:
    st.markdown(
        f"""
<div class="ep-hero">
  <h1>{theme.APP_ICON} {theme.APP_NAME}</h1>
  <p>{theme.TAGLINE}: management's tone, the numbers behind it, and the company's financial health.</p>
  <span class="ep-chip">Official SEC filings</span><span class="ep-chip">Loughran-McDonald + FinBERT</span>
  <span class="ep-chip">Every figure traceable</span>
</div>
<div class="ep-steps">
  <div class="ep-step"><div class="n">1</div><b>Read the filings</b>
    <span>Downloads each 10-Q / 10-K and the earnings press release (8-K, Exhibit 99.1) from SEC EDGAR.</span></div>
  <div class="ep-step"><div class="n">2</div><b>Score the tone</b>
    <span>Rates management's language with the Loughran-McDonald finance dictionary and, optionally, FinBERT.</span></div>
  <div class="ep-step"><div class="n">3</div><b>Compare the numbers</b>
    <span>Pulls reported figures from SEC's XBRL data and compares each quarter with last quarter and last year.</span></div>
  <div class="ep-step"><div class="n">4</div><b>Rate the health</b>
    <span>A transparent five-pillar scorecard plus the Piotroski F-Score, with every signal shown.</span></div>
</div>
<p class="ep-note">Pick a company in the sidebar and press <b>Analyse</b>. Covers companies that file 10-Q/10-K
reports with the US SEC. Download a full HTML or PDF report from the results page.</p>
""",
        unsafe_allow_html=True,
    )
    st.stop()

ticker, n_q, fb = req
progress_bar = st.progress(0.0, text=f"Analysing {ticker} ...")
try:
    a = run_analysis(ticker, n_q, fb, ua, progress=lambda p, m: progress_bar.progress(min(1.0, p), text=m))
except EdgarError as exc:
    progress_bar.empty()
    st.error(str(exc))
    st.stop()
except Exception as exc:  # surface unexpected problems without a stack trace wall
    progress_bar.empty()
    st.error(f"Something went wrong while analysing {ticker}: {exc}")
    st.stop()
progress_bar.empty()

# ----------------------------------------------------------------------------- header
insights = build_insights(a)
verdict_label, verdict_detail = verdict(insights)
latest = a.latest
method = "FinBERT + Loughran-McDonald" if a.used_finbert else "Loughran-McDonald"
st.markdown(
    f"""
<div class="ep-hero">
  <h1>{html.escape(a.company.name)} ({a.company.ticker})</h1>
  <p>Latest quarter <b>{latest.fq.label}</b>: period ended {latest.period_end}, {latest.filing.form} filed
  {latest.filing.filing_date}</p>
  <span class="ep-chip">{len(a.quarters)} quarters</span><span class="ep-chip">Tone: {method}</span>
  <span class="ep-chip">Overall: {verdict_label}</span><span class="ep-chip">Generated {a.generated_at}</span>
</div>
""",
    unsafe_allow_html=True,
)

k_list = kpis(a)
cols = st.columns(3) + st.columns(3)
for col, k in zip(cols, k_list):
    delta = k["delta"] or None
    numeric_delta = delta and delta[0] in "+-"
    col.metric(k["name"], k["value"], delta if numeric_delta else None,
               help=None if numeric_delta else (delta or None), border=True)

key = f"{a.company.ticker}-{latest.fq.slug}-{n_q}-{fb}-{a.generated_at}"
d1, d2, d3, d4 = st.columns(4)
d1.download_button("⬇ HTML report (interactive)", html_report(a, key), f"{a.company.ticker}_{latest.fq.slug}_report.html",
                   "text/html", width="stretch", on_click="ignore")
d2.download_button("⬇ PDF report", pdf_report(a, key), f"{a.company.ticker}_{latest.fq.slug}_report.pdf",
                   "application/pdf", width="stretch", on_click="ignore")
buf = io.StringIO()
pd.DataFrame(data_table(a)).to_csv(buf, index=False)
d3.download_button("⬇ Quarterly data (CSV)", buf.getvalue(), f"{a.company.ticker}_quarters.csv", "text/csv",
                   width="stretch", on_click="ignore")
d4.download_button("⬇ Full results (JSON)", json.dumps(a.to_summary(), indent=2, default=str),
                   f"{a.company.ticker}_{latest.fq.slug}_summary.json", "application/json",
                   width="stretch", on_click="ignore")

for w in a.warnings:
    st.caption(f"ℹ️ {w}")


def show(fig, key: str):
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False}, key=key)


tab_over, tab_fin, tab_sent, tab_health, tab_src = st.tabs(
    ["Overview", "Financials", "Sentiment", "Health", "Sources & method"]
)

# ----------------------------------------------------------------------------- overview
with tab_over:
    st.subheader(f"What changed in {latest.fq.label}")
    st.markdown(f'<span class="ep-verdict">Overall direction: {verdict_label}</span> '
                f'<span class="ep-note">&nbsp;{verdict_detail}</span>', unsafe_allow_html=True)
    st.markdown("  \n".join(f"{SIGNAL_ICON[i.signal]} **{i.area}:** {i.text}" for i in insights))
    c1, c2 = st.columns(2)
    with c1:
        show(charts.revenue_income_chart(a), "revenue_income_chart_1")
    with c2:
        show(charts.tone_index_chart(a), "tone_index_chart_1")

# ----------------------------------------------------------------------------- financials
with tab_fin:
    c1, c2 = st.columns(2)
    with c1:
        show(charts.revenue_income_chart(a), "revenue_income_chart_2")
        show(charts.margins_chart(a), "margins_chart_1")
        show(charts.balance_chart(a), "balance_chart_1")
    with c2:
        show(charts.growth_chart(a), "growth_chart_1")
        show(charts.cash_chart(a), "cash_chart_1")
    st.subheader("Quarter-by-quarter")
    st.dataframe(pd.DataFrame(data_table(a)).set_index("Quarter"), width="stretch")
    st.caption("Fourth-quarter flows are derived as full-year minus nine months, as 10-K filings report annual totals.")

# ----------------------------------------------------------------------------- sentiment
with tab_sent:
    c1, c2 = st.columns(2)
    with c1:
        show(charts.tone_index_chart(a), "tone_index_chart_2")
        show(charts.lm_categories_chart(a, "mdna"), "lm_categories_chart_mdna_1")
    with c2:
        show(charts.tone_sources_chart(a), "tone_sources_chart_1")
        show(charts.risk_length_chart(a), "risk_length_chart_1")
    st.subheader("Evidence: the sentences driving the scores")
    labels = [q.fq.label for q in a.quarters]
    pick = st.selectbox("Quarter", list(reversed(labels)), key="evidence_q")
    q = next(q for q in a.quarters if q.fq.label == pick)
    for sec, d in q.docs.items():
        with st.expander(f"{SECTIONS[sec]} — {d['n_sentences']} sentences, {d['lm']['words']:,} words", expanded=sec != "risk"):
            lm = d["lm"]
            m = st.columns(5)
            m[0].metric("LM net tone", f"{lm['net_tone']:+.2f}" if lm.get("net_tone") is not None else "n/a")
            m[1].metric("Negative words", f"{lm['negative_pct']:.2f}%" if lm.get("negative_pct") is not None else "n/a")
            m[2].metric("Uncertainty words", f"{lm['uncertainty_pct']:.2f}%" if lm.get("uncertainty_pct") is not None else "n/a")
            m[3].metric("Litigious words", f"{lm['litigious_pct']:.2f}%" if lm.get("litigious_pct") is not None else "n/a")
            m[4].metric("FinBERT score", f"{d['finbert']['score']:+.2f}" if d.get("finbert") else "—")
            if d.get("top_positive"):
                st.markdown("**Most positive**")
                for s in d["top_positive"]:
                    st.markdown(f"> {s['text']}  \n:gray[score {s['score']:+.2f}]")
            if d.get("top_negative"):
                st.markdown("**Most negative**")
                for s in d["top_negative"]:
                    st.markdown(f"> {s['text']}  \n:gray[score {s['score']:+.2f}]")
            st.markdown(f"[Open source document]({d['source_url']})")

# ----------------------------------------------------------------------------- health
with tab_health:
    c1, c2 = st.columns(2)
    with c1:
        show(charts.pillars_chart(a), "pillars_chart_1")
        show(charts.fscore_chart(a), "fscore_chart_1")
    with c2:
        show(charts.health_trend_chart(a), "health_trend_chart_1")
    h = latest.health or {"metrics": {}, "metric_scores": {}}
    c1, c2 = st.columns(2)
    with c1:
        st.subheader(f"Scorecard metrics — {latest.fq.label}")
        st.dataframe(
            pd.DataFrame([
                {"Metric": label, "Value": metric_value(k, h["metrics"].get(k)),
                 "Score (0-100)": h["metric_scores"].get(k)}
                for k, label in METRIC_LABELS.items()
            ]).set_index("Metric"),
            width="stretch",
        )
    with c2:
        if latest.fscore:
            st.subheader(f"Piotroski F-Score — {latest.fscore['score']}/{latest.fscore['available']}")
            st.dataframe(
                pd.DataFrame([
                    {"Signal": s["signal"], "Group": s["group"],
                     "Pass": "✅" if s["pass"] else ("❌" if s["pass"] is not None else "n/a")}
                    for s in latest.fscore["signals"]
                ]).set_index("Signal"),
                width="stretch",
            )
    st.caption("Scorecard thresholds are generic rules of thumb (see docs/METHODOLOGY.md), not industry-specific benchmarks.")

# ----------------------------------------------------------------------------- sources
with tab_src:
    st.subheader("Sources")
    st.dataframe(pd.DataFrame(a.sources()), width="stretch", hide_index=True,
                 column_config={"what": "Document", "url": st.column_config.LinkColumn("Link")})
    st.subheader("Method")
    st.markdown(
        f"""
- **Tone index**: average of the MD&A and press-release scores, from -1 (negative) to +1 (positive).
  {'FinBERT score = P(positive) − P(negative), averaged over sentences.' if a.used_finbert else 'Loughran-McDonald net tone = (positive − negative) / (positive + negative) words.'}
- **Dictionary**: {a.dictionary_source} — Loughran & McDonald (2011), *Journal of Finance* 66(1).
- **FinBERT**: Araci (2019), arXiv:1908.10063, model `ProsusAI/finbert`.
- **Financials**: SEC XBRL company facts; restated figures use the latest filing.
- **Health**: five-pillar scorecard + Piotroski (2000) F-Score on a trailing-twelve-month basis.
- Full write-up with references: `docs/METHODOLOGY.md` in the repository.
"""
    )
