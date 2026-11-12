"""
Visual system of the app: icon vocabulary, the small CSS layer on top of the Streamlit theme, and the
branded building blocks (header band, section titles, KPI tiles, verdict banner, status chips).

Design rules (see docs/design_system.md):
  * One icon per concept, always the same one, from Material Symbols Rounded (the set Streamlit ships).
  * Colour is semantic only: navy = neutral / totals, green = accretive, red = dilutive, amber = watch.
  * Numbers use tabular figures so columns of KPIs line up.
  * Native widgets everywhere; HTML is limited to presentational blocks that Streamlit has no element for.
"""
from __future__ import annotations

import html

import streamlit as st

from engine import AMBER, GREEN, GREY, NAVY, RED

# ---------------------------------------------------------------------------
# Icon vocabulary (Material Symbols names). Use through ICONS[...] so every screen stays consistent.
# ---------------------------------------------------------------------------
ICONS = {
    # navigation
    "dcf": "query_stats", "comps": "stacked_bar_chart", "capital": "account_balance", "summary": "receipt_long",
    "sensitivity": "grid_on", "montecarlo": "scatter_plot",
    # sidebar groups
    "case": "folder_open", "pitchbook": "description", "acquirer": "domain", "target": "my_location",
    "consideration": "payments", "synergies": "hub", "ppa": "inventory_2", "phasing": "timeline",
    "import": "cloud_download", "load": "download", "fetch": "travel_explore", "inputs": "tune",
    # KPI concepts
    "ev": "apartment", "equity": "pie_chart", "per_share": "paid", "market": "show_chart", "eps": "functions",
    "premium": "trending_up", "ownership": "groups", "breakeven": "balance", "cash": "savings",
    "debt": "credit_card", "rate": "percent", "interest": "request_quote", "leverage": "speed",
    "probability": "casino", "distribution": "bar_chart", "downside": "south", "mean": "equalizer",
    "price": "sell", "shares": "layers", "income": "account_balance_wallet", "year": "calendar_month",
    # states
    "accretive": "trending_up", "dilutive": "trending_down", "ok": "check_circle", "warn": "warning",
    "error": "error", "info": "info", "help": "help", "method": "menu_book", "table": "table_chart",
    "chart": "insights", "settings": "settings", "verified": "verified", "source": "link",
}


def icon(name: str) -> str:
    """Markdown directive for a Material icon, usable in labels of native widgets (tabs, buttons, metrics)."""
    return f":material/{ICONS.get(name, name)}:"


def _sym(name: str, size: int = 20, color: str = "currentColor") -> str:
    """Inline icon for the HTML blocks below."""
    return (f'<span class="msc-ico" style="font-size:{size}px;color:{color}">'
            f'{html.escape(ICONS.get(name, name))}</span>')


# ---------------------------------------------------------------------------
# CSS layer: only what the theme cannot express (tabs, header band, chips, tiles)
# ---------------------------------------------------------------------------
_CSS = f"""
<style>
/* Material icon font inside our HTML blocks (Streamlit already loads it for its own icons) */
.msc-ico {{
  font-family: "Material Symbols Rounded"; font-weight: normal; font-style: normal; line-height: 1;
  display: inline-block; vertical-align: -0.2em; letter-spacing: normal; text-transform: none;
  -webkit-font-smoothing: antialiased; font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
}}
/* Tabular figures everywhere numbers appear */
[data-testid="stMetricValue"], [data-testid="stMetricDelta"], [data-testid="stDataFrame"],
.msc-kpi-value, .msc-hero-value {{ font-variant-numeric: tabular-nums; }}

/* Tighter top padding; the header band is our first element */
.block-container {{ padding-top: 1.25rem; padding-bottom: 3rem; }}

/* Header band */
.msc-header {{
  display: flex; align-items: center; gap: 16px; padding: 18px 22px; border-radius: 14px;
  background: linear-gradient(135deg, {NAVY} 0%, #2b6ca3 100%); color: #fff; margin-bottom: 14px;
  box-shadow: 0 6px 18px rgba(31, 78, 121, 0.18);
}}
.msc-header .msc-logo {{
  width: 46px; height: 46px; border-radius: 12px; background: rgba(255,255,255,0.14); display: flex;
  align-items: center; justify-content: center; flex: 0 0 46px; border: 1px solid rgba(255,255,255,0.22);
}}
.msc-header h1 {{ margin: 0; font-size: 1.45rem; font-weight: 700; color: #fff; line-height: 1.2; }}
.msc-header p {{ margin: 2px 0 0; font-size: 0.86rem; color: rgba(255,255,255,0.78); }}
.msc-header .msc-chips {{ margin-left: auto; display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }}
.msc-chip {{
  display: inline-flex; align-items: center; gap: 6px; padding: 5px 10px; border-radius: 999px;
  background: rgba(255,255,255,0.14); border: 1px solid rgba(255,255,255,0.25); font-size: 0.78rem;
  font-weight: 500; color: #fff; white-space: nowrap;
}}
.msc-chip.ok {{ background: rgba(46,158,91,0.35); border-color: rgba(46,158,91,0.6); }}
.msc-chip.bad {{ background: rgba(214,69,69,0.35); border-color: rgba(214,69,69,0.6); }}

/* Tabs: pill-style, with the icon beside the label */
.stTabs [data-baseweb="tab-list"] {{ gap: 2px; border-bottom: 1px solid #dde3ec; padding-bottom: 0; }}
.stTabs [data-baseweb="tab"] {{
  height: 42px; padding: 0 10px; border-radius: 10px 10px 0 0; font-weight: 500; font-size: 0.88rem;
}}
.stTabs [data-baseweb="tab"]:hover {{ background: rgba(31,78,121,0.06); }}
.stTabs [aria-selected="true"] {{ background: rgba(31,78,121,0.08); font-weight: 600; }}
.stTabs [data-baseweb="tab-highlight"] {{ height: 3px; border-radius: 3px; }}

/* Section title: icon in a tinted square + title + caption */
.msc-section {{ display: flex; align-items: center; gap: 10px; margin: 2px 0 10px; }}
.msc-section .msc-sqr {{
  width: 32px; height: 32px; border-radius: 9px; background: rgba(31,78,121,0.09); color: {NAVY};
  display: flex; align-items: center; justify-content: center; flex: 0 0 32px;
}}
.msc-section .msc-ttl {{ font-weight: 600; font-size: 1rem; color: #1b2a41; line-height: 1.2; }}
.msc-section .msc-cap {{ font-size: 0.8rem; color: #6b7280; margin-top: 2px; }}

/* Hero verdict banner */
.msc-hero {{
  display: flex; align-items: center; gap: 18px; padding: 16px 20px; border-radius: 12px; margin: 4px 0 8px;
  border: 1px solid;
}}
.msc-hero.ok {{ background: #eef9f2; border-color: rgba(46,158,91,0.35); }}
.msc-hero.bad {{ background: #fdf0f0; border-color: rgba(214,69,69,0.35); }}
.msc-hero.na {{ background: #f3f4f6; border-color: #dde3ec; }}
.msc-hero .msc-hero-ico {{
  width: 52px; height: 52px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  flex: 0 0 52px; color: #fff;
}}
.msc-hero.ok .msc-hero-ico {{ background: {GREEN}; }}
.msc-hero.bad .msc-hero-ico {{ background: {RED}; }}
.msc-hero.na .msc-hero-ico {{ background: {GREY}; }}
.msc-hero-label {{ font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.06em; color: #6b7280; font-weight: 600; }}
.msc-hero-value {{ font-size: 1.6rem; font-weight: 700; line-height: 1.15; }}
.msc-hero.ok .msc-hero-value {{ color: #1e7a43; }}
.msc-hero.bad .msc-hero-value {{ color: #b23636; }}
.msc-hero-sub {{ font-size: 0.86rem; color: #4b5563; margin-top: 2px; }}

/* Compact KPI tile (used where st.metric is too tall, e.g. sidebar summaries) */
.msc-kpi {{ padding: 10px 12px; border: 1px solid #e3e8f0; border-radius: 10px; background: #fff; }}
.msc-kpi-label {{ font-size: 0.76rem; color: #6b7280; display: flex; align-items: center; gap: 5px; }}
.msc-kpi-value {{ font-size: 1.15rem; font-weight: 600; color: #1b2a41; margin-top: 2px; }}

/* Metrics with border read as cards: give them a white background and a soft shadow */
[data-testid="stMetric"] {{ background: #fff; }}
[data-testid="stMetricLabel"] p {{ font-size: 0.82rem; color: #4b5563; }}

/* Sidebar: section expanders look like grouped cards */
[data-testid="stSidebar"] [data-testid="stExpander"] details {{ border-radius: 10px; }}
[data-testid="stSidebar"] [data-testid="stExpander"] summary {{ font-weight: 600; }}
[data-testid="stSidebarUserContent"] {{ padding-top: 1.5rem; }}

/* Dataframes: slightly rounder frame */
[data-testid="stDataFrame"] {{ border-radius: 10px; overflow: hidden; }}

/* Hide the colourful top decoration bar */
[data-testid="stDecoration"] {{ display: none; }}
</style>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------
_LOGO_SVG = """
<svg width="26" height="26" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <circle cx="8" cy="12" r="6" stroke="#fff" stroke-width="2" opacity="0.9"/>
  <circle cx="16" cy="12" r="6" stroke="#fff" stroke-width="2"/>
  <path d="M12 7.6a6 6 0 0 1 0 8.8a6 6 0 0 1 0-8.8z" fill="#fff" opacity="0.9"/>
</svg>
"""


def render_header(title: str, subtitle: str, chips: list[tuple[str, str, str]]) -> None:
    """
    Branded header band. `chips` = [(icon_key, text, state)] with state in {"", "ok", "bad"}.
    """
    chips_html = "".join(
        f'<span class="msc-chip {state}">{_sym(ic, 16)}{html.escape(text)}</span>' for ic, text, state in chips
    )
    st.markdown(
        f'<div class="msc-header"><div class="msc-logo">{_LOGO_SVG}</div>'
        f'<div><h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p></div>'
        f'<div class="msc-chips">{chips_html}</div></div>',
        unsafe_allow_html=True,
    )


def section(icon_key: str, title: str, caption: str | None = None) -> None:
    """Section header: tinted icon square + bold title + optional caption. Replaces card_title."""
    cap = f'<div class="msc-cap">{html.escape(caption)}</div>' if caption else ""
    st.markdown(
        f'<div class="msc-section"><div class="msc-sqr">{_sym(icon_key, 20)}</div>'
        f'<div><div class="msc-ttl">{html.escape(title)}</div>{cap}</div></div>',
        unsafe_allow_html=True,
    )


def hero(state: str, label: str, value: str, sub: str = "", icon_key: str | None = None) -> None:
    """Verdict banner. state in {"ok", "bad", "na"}."""
    ic = icon_key or {"ok": "accretive", "bad": "dilutive"}.get(state, "info")
    st.markdown(
        f'<div class="msc-hero {state}"><div class="msc-hero-ico">{_sym(ic, 28, "#fff")}</div>'
        f'<div><div class="msc-hero-label">{html.escape(label)}</div>'
        f'<div class="msc-hero-value">{html.escape(value)}</div>'
        f'<div class="msc-hero-sub">{html.escape(sub)}</div></div></div>',
        unsafe_allow_html=True,
    )


def kpi(label: str, value: str, icon_key: str | None = None, parent=None) -> None:
    """Compact KPI tile (HTML). For the main dashboards use st.metric with border=True and icon=."""
    target = st if parent is None else parent
    ic = _sym(icon_key, 15, NAVY) if icon_key else ""
    target.markdown(
        f'<div class="msc-kpi"><div class="msc-kpi-label">{ic}{html.escape(label)}</div>'
        f'<div class="msc-kpi-value">{html.escape(value)}</div></div>',
        unsafe_allow_html=True,
    )


def metric(col, label: str, value, icon_key: str | None = None, **kwargs) -> None:
    """st.metric with the app's defaults: bordered tile and a Material icon in the label."""
    col.metric(label, value, icon=icon(icon_key) if icon_key else None, border=True, **kwargs)


STATE_COLORS = {"ok": GREEN, "warn": AMBER, "bad": RED, "neutral": NAVY}
