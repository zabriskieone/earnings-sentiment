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
  display:inline-block; padding: 5px 14px; border-radius: 999px; font-weight: 700; color: #fff;
  background: linear-gradient(90deg, {g1}, {g2});
}}
</style>
"""
