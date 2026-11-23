"""EarningsPulse visual identity: names, palettes and the light/dark switch.

The sidebar is always the indigo -> violet gradient. The main area has a light
and a dark palette tuned to sit next to it. Streamlit has no public API to
change the theme from Python, so the toggle rewrites the theme options and
reruns the app. That setting is per server process: on a shared server every
open tab follows the most recent toggle, which is fine for a local app.
"""

from __future__ import annotations

APP_NAME = "EarningsPulse"
TAGLINE = "Sentiment & health from every quarterly result"
APP_ICON = "📈"

# Brand gradient (sidebar, hero banner, report header)
GRADIENT = ("#1e1b4b", "#4c1d95", "#6d28d9")
ACCENT = "#8b5cf6"

_SIDEBAR = {
    "theme.sidebar.backgroundColor": "#2e1f78",
    "theme.sidebar.secondaryBackgroundColor": "#3a2d8c",
    "theme.sidebar.textColor": "#f5f3ff",
    "theme.sidebar.primaryColor": "#c4b5fd",
    "theme.sidebar.borderColor": "#6656c4",
}

PALETTES = {
    "light": {
        "theme.base": "light",
        "theme.primaryColor": "#6d28d9",
        "theme.backgroundColor": "#f7f6fc",
        "theme.secondaryBackgroundColor": "#eeebfa",
        "theme.textColor": "#1b1733",
        "theme.borderColor": "#dcd6f2",
        "theme.linkColor": "#5b21b6",
        **_SIDEBAR,
    },
    "dark": {
        "theme.base": "dark",
        "theme.primaryColor": "#a78bfa",
        "theme.backgroundColor": "#0f0d1f",
        "theme.secondaryBackgroundColor": "#1b1833",
        "theme.textColor": "#ecebf7",
        "theme.borderColor": "#2f2a52",
        "theme.linkColor": "#c4b5fd",
        **_SIDEBAR,
    },
}

# Colors used by the custom CSS for each mode
CSS_VARS = {
    "light": {"card": "#ffffff", "card_border": "#e4dff5", "muted": "#5d5878", "shadow": "rgba(76,29,149,0.08)"},
    "dark": {"card": "#17142c", "card_border": "#2f2a52", "muted": "#a9a4c7", "shadow": "rgba(0,0,0,0.35)"},
}


def apply_palette(mode: str) -> None:
    """Write the palette into Streamlit's config; takes effect on the next run."""
    from streamlit import config

    for key, value in PALETTES[mode].items():
        config._set_option(key, value, "<earningspulse theme toggle>")


def current_mode() -> str:
    from streamlit import config

    return "dark" if config.get_option("theme.base") == "dark" else "light"


def css(mode: str) -> str:
    v = CSS_VARS[mode]
    g0, g1, g2 = GRADIENT
    return f"""
<style>
/* ---------- sidebar: brand gradient ---------- */
section[data-testid="stSidebar"] > div:first-child,
section[data-testid="stSidebar"] {{
  background: linear-gradient(165deg, {g0} 0%, {g1} 55%, {g2} 100%) !important;
}}
section[data-testid="stSidebar"] * {{ color: #f5f3ff; }}
section[data-testid="stSidebar"] [data-baseweb="input"],
section[data-testid="stSidebar"] [data-baseweb="select"] > div {{
  background: rgba(255,255,255,0.10) !important;
  border-color: rgba(255,255,255,0.22) !important;
}}
section[data-testid="stSidebar"] input::placeholder {{ color: rgba(245,243,255,0.55) !important; }}
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] * {{ color: rgba(245,243,255,0.72) !important; }}
section[data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,0.18) !important; }}
section[data-testid="stSidebar"] button[kind="primary"] {{
  background: linear-gradient(90deg, #c4b5fd, #f0abfc) !important;
  border: none !important;
  box-shadow: 0 6px 18px rgba(240,171,252,0.25);
}}
section[data-testid="stSidebar"] button[kind="primary"] * {{ color: #1e1b4b !important; font-weight: 700; }}
section[data-testid="stSidebar"] button[kind="primary"]:disabled {{ opacity: 0.45; box-shadow: none; }}
section[data-testid="stSidebar"] [data-testid="stAlert"] * {{ color: #1b1733 !important; }}

.ep-brand {{ display:flex; align-items:center; gap:10px; margin: 0 0 4px; }}
.ep-logo {{
  width:38px; height:38px; border-radius:11px; display:grid; place-items:center; font-size:20px;
  background: linear-gradient(135deg, #c4b5fd, #f0abfc); box-shadow: 0 4px 14px rgba(240,171,252,0.35);
}}
.ep-name {{ font-size:22px; font-weight:800; letter-spacing:-0.02em; color:#fff; line-height:1.1; }}
.ep-tag {{ font-size:12.5px; color: rgba(245,243,255,0.75) !important; margin: 2px 0 14px; }}

/* ---------- main area ---------- */
.block-container {{ padding-top: 2.2rem; }}
.ep-hero {{
  border-radius: 18px; padding: 26px 28px; margin: 0 0 18px; color: #fff;
  background: linear-gradient(120deg, {g0} 0%, {g1} 55%, {g2} 100%);
  box-shadow: 0 10px 30px {v['shadow']};
  position: relative; overflow: hidden;
}}
.ep-hero::after {{
  content:""; position:absolute; right:-60px; top:-60px; width:240px; height:240px; border-radius:50%;
  background: radial-gradient(circle, rgba(240,171,252,0.35), transparent 70%);
}}
.ep-hero h1 {{ color:#fff !important; font-size: 30px; margin: 0 0 4px; padding: 0; letter-spacing:-0.02em; }}
.ep-hero p {{ color: rgba(255,255,255,0.82) !important; margin: 0; font-size: 14.5px; }}
.ep-hero .ep-chip {{
  display:inline-block; margin: 12px 8px 0 0; padding: 4px 11px; border-radius: 999px; font-size: 12.5px;
  background: rgba(255,255,255,0.14); border: 1px solid rgba(255,255,255,0.22); color:#fff;
}}
.ep-steps {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; margin: 6px 0 18px; }}
.ep-step {{
  background: {v['card']}; border: 1px solid {v['card_border']}; border-radius: 14px; padding: 16px 16px 14px;
  box-shadow: 0 4px 16px {v['shadow']};
}}
.ep-step .n {{
  width:28px; height:28px; border-radius:8px; display:grid; place-items:center; font-weight:700; color:#fff;
  background: linear-gradient(135deg, {g1}, {g2}); margin-bottom: 10px; font-size: 13px;
}}
.ep-step b {{ display:block; margin-bottom: 4px; }}
.ep-step span {{ color: {v['muted']}; font-size: 13.5px; line-height: 1.45; }}
.ep-note {{ color: {v['muted']}; font-size: 13px; }}

div[data-testid="stMetric"] {{
  background: {v['card']}; border: 1px solid {v['card_border']} !important; border-radius: 14px;
  box-shadow: 0 4px 16px {v['shadow']}; position: relative; overflow: hidden;
}}
div[data-testid="stMetric"]::before {{
  content:""; position:absolute; left:0; top:0; right:0; height:3px;
  background: linear-gradient(90deg, {g1}, {g2}, #f0abfc);
}}
div[data-testid="stPlotlyChart"] {{
  background: {v['card']}; border: 1px solid {v['card_border']}; border-radius: 14px; padding: 6px 8px;
  box-shadow: 0 4px 16px {v['shadow']};
}}
.stTabs [data-baseweb="tab-list"] {{ gap: 6px; }}
.stTabs [data-baseweb="tab"] {{ border-radius: 10px 10px 0 0; padding: 8px 14px; }}
.stTabs [aria-selected="true"] {{ font-weight: 700; }}
.ep-verdict {{
  display:inline-block; padding: 5px 14px; border-radius: 999px; font-weight: 700; color: #fff; font-size: 13px;
  background: linear-gradient(90deg, {g1}, {g2});
}}

/* company hero with logo */
.ep-hero-co {{ display:flex; align-items:center; gap: 20px; }}
.ep-hero-text {{ position: relative; z-index: 1; }}
.ep-ticker {{
  font-size: 14px; font-weight: 700; padding: 3px 10px; border-radius: 8px; vertical-align: middle; margin-left: 6px;
  background: rgba(255,255,255,0.16); border: 1px solid rgba(255,255,255,0.25);
}}
.ep-chip-strong {{ background: linear-gradient(90deg, #c4b5fd, #f0abfc) !important; color: {g0} !important;
  font-weight: 700; border: none !important; }}

/* generic card + insight list */
.ep-card {{
  background: {v['card']}; border: 1px solid {v['card_border']}; border-radius: 16px; padding: 18px 20px 8px;
  box-shadow: 0 4px 16px {v['shadow']}; height: 100%;
}}
.ep-card-head {{ display:flex; align-items:center; justify-content:space-between; gap: 12px; }}
.ep-card-head h3 {{ margin: 0; padding: 0; font-size: 18px; }}
.ep-card .ep-note {{ margin: 2px 0 8px; }}
.ep-ins-list {{ list-style: none; padding: 0; margin: 0; }}
.ep-ins {{ display:flex; align-items:flex-start; gap: 10px; padding: 9px 0; border-top: 1px dashed {v['card_border']};
  font-size: 14px; line-height: 1.45; }}
.ep-ins-icon {{
  flex: 0 0 22px; height: 22px; border-radius: 50%; display:grid; place-items:center; font-size: 10px; color: #fff;
  margin-top: 1px;
}}
.ep-ins.positive .ep-ins-icon {{ background: #0d9488; }}
.ep-ins.negative .ep-ins-icon {{ background: #e11d48; }}
.ep-ins.neutral .ep-ins-icon {{ background: #8a85a6; }}
.ep-ins-area {{ flex: 0 0 104px; font-size: 11px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase;
  color: {v['muted']}; padding-top: 3px; }}

/* segmented, pill-shaped tabs */
.stTabs [role="tablist"] {{
  background: {v['card']}; border: 1px solid {v['card_border']}; border-radius: 999px; padding: 5px; gap: 4px;
  width: fit-content; max-width: 100%; box-shadow: 0 4px 16px {v['shadow']}; border-bottom: 1px solid {v['card_border']};
}}
.stTabs [role="tab"] {{ border-radius: 999px !important; padding: 7px 18px !important; height: auto !important;
  margin: 0 !important; transition: background .15s ease; }}
.stTabs [role="tab"]:hover {{ background: {v['shadow']}; }}
.stTabs [role="tab"][data-selected="true"], .stTabs [role="tab"][aria-selected="true"] {{
  background: linear-gradient(90deg, {g1}, {g2}) !important; box-shadow: 0 4px 12px rgba(109,40,217,0.35);
}}
.stTabs [role="tab"][aria-selected="true"] p, .stTabs [role="tab"][aria-selected="true"] div {{ color: #fff !important; }}
.stTabs [role="tab"]::after, .stTabs [role="tab"]::before {{ display: none !important; }}
.stTabs [role="tablist"] > :not([role="tab"]) {{ display: none !important; }}
/* the pill already marks the active tab: hide Streamlit's 2px selection indicator */
.stTabs .react-aria-SelectionIndicator, .stTabs [class*="SelectionIndicator"] {{ display: none !important; }}
.stTabs [role="tabpanel"] {{ padding-top: 18px; }}

/* KPI sparklines in brand violet */
div[data-testid="stMetric"] .mark-line path {{ stroke: {ACCENT} !important; stroke-width: 2px !important; }}
div[data-testid="stMetric"] .mark-area path {{ fill: {ACCENT} !important; fill-opacity: 0.16 !important; }}
div[data-testid="stMetric"] .mark-symbol path {{ fill: {ACCENT} !important; }}

/* soft download buttons */
.main div[data-testid="stDownloadButton"] button, section.main div[data-testid="stDownloadButton"] button,
div[data-testid="stMainBlockContainer"] div[data-testid="stDownloadButton"] button {{
  border-radius: 999px; border: 1px solid {v['card_border']}; background: {v['card']};
  box-shadow: 0 2px 10px {v['shadow']};
}}
div[data-testid="stMainBlockContainer"] div[data-testid="stDownloadButton"] button:hover {{
  border-color: {ACCENT}; color: {ACCENT};
}}
div[data-testid="stExpander"] details {{ border-radius: 14px; border-color: {v['card_border']}; background: {v['card']}; }}
div[data-testid="stDataFrame"] {{ border-radius: 12px; overflow: hidden; }}

/* glossary */
.ep-gloss {{ display:grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 10px; }}
.ep-term {{ background: {v['card']}; border: 1px solid {v['card_border']}; border-radius: 12px; padding: 12px 14px;
  font-size: 13.5px; line-height: 1.5; }}
.ep-term b {{ display:block; margin-bottom: 3px; color: {ACCENT}; }}
.ep-term span {{ color: {v['muted']}; }}

/* "How to read this chart" trigger sits quietly under each chart card */
div[data-testid="stPopover"] {{ margin: -6px 0 10px 4px; }}
div[data-testid="stPopover"] button {{ font-size: 12.5px; color: {v['muted']}; padding: 2px 6px; min-height: 0; }}
div[data-testid="stPopover"] button:hover {{ color: {ACCENT}; }}
div[data-testid="stPopoverBody"] {{ max-width: 460px; border-radius: 14px; }}
</style>
"""
