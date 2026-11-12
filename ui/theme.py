"""
Visual system of the app: icon vocabulary, the CSS layer on top of the Streamlit theme, and the branded
building blocks (hero header, section titles, KPI tiles, verdict banner, status chips).

Art direction ("lights off" editorial, see docs/design_system.md):
  * Cinematic hero band with a generated image (ui/assets/hero.jpg) and an uppercase display title.
  * Dark ink sidebar with a soft light texture; warm off-white canvas with white cards in the main area.
  * One accent colour per tab (teal, amber, violet, green/red, coral, indigo): section icons, KPI tiles
    and the active tab underline pick it up through a scoped container (`st.container(key=...)`).
  * One icon per concept, from Material Symbols Rounded (the set Streamlit ships).
  * Numbers use tabular figures so columns of KPIs line up.
"""
from __future__ import annotations

import base64
import html
from pathlib import Path

import streamlit as st

from engine import AMBER, GREEN, GREY, NAVY, RED

ASSETS = Path(__file__).with_name("assets")

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

# Accent per tab: (main colour, soft tint for icon squares / highlights)
ACCENTS = {
    "dcf": ("#0ea5a4", "rgba(14,165,164,0.12)"),
    "comps": ("#f59e0b", "rgba(245,158,11,0.14)"),
    "capital": ("#7c3aed", "rgba(124,58,237,0.12)"),
    "summary": ("#1f4e79", "rgba(31,78,121,0.10)"),
    "sensitivity": ("#f97316", "rgba(249,115,22,0.13)"),
    "montecarlo": ("#4f46e5", "rgba(79,70,229,0.12)"),
}


def icon(name: str) -> str:
    """Markdown directive for a Material icon, usable in labels of native widgets (tabs, buttons, metrics)."""
    return f":material/{ICONS.get(name, name)}:"


def _sym(name: str, size: int = 20, color: str = "currentColor") -> str:
    """Inline icon for the HTML blocks below."""
    return (f'<span class="msc-ico" style="font-size:{size}px;color:{color}">'
            f'{html.escape(ICONS.get(name, name))}</span>')


def _asset_uri(name: str, mime: str = "image/jpeg") -> str | None:
    """Data URI of a bundled asset (hero / sidebar textures), or None if it is missing."""
    path = ASSETS / name
    if not path.exists():
        return None
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


@st.cache_resource(show_spinner=False)
def _css() -> str:
    hero_img = _asset_uri("hero.jpg")
    side_img = _asset_uri("sidebar.jpg")
    hero_bg = (f"url('{hero_img}') center right / cover no-repeat, " if hero_img else "") + \
        f"linear-gradient(120deg, #0b1220 0%, #12213a 55%, #3b2a2a 100%)"
    side_bg = (f"url('{side_img}') center / cover no-repeat" if side_img else
               "linear-gradient(180deg, #0b1220 0%, #101a2c 70%, #2a1f2a 100%)")
    accent_rules = "\n".join(
        f""".st-key-scope_{k} .msc-sqr {{ background: {tint}; color: {col}; }}
.st-key-scope_{k} [data-testid="stMetric"] {{ border-left: 4px solid {col}; }}
.st-key-scope_{k} .msc-eyebrow {{ color: {col}; }}
.st-key-scope_{k} .msc-kpi {{ border-left: 4px solid {col}; }}"""
        for k, (col, tint) in ACCENTS.items()
    )
    tab_rules = "\n".join(
        f'.stTabs [role="tablist"] [data-testid="stTab"]:nth-child({i + 1})[aria-selected="true"] '
        f'{{ box-shadow: inset 0 -3px 0 {col}; }} '
        f'.stTabs [role="tablist"] [data-testid="stTab"]:nth-child({i + 1})[aria-selected="true"] p '
        f'{{ color: {col} !important; }}'
        for i, (col, _) in enumerate(ACCENTS.values())
    )
    return f"""
<style>
.msc-ico {{
  font-family: "Material Symbols Rounded"; font-weight: normal; font-style: normal; line-height: 1;
  display: inline-block; vertical-align: -0.2em; letter-spacing: normal; text-transform: none;
  -webkit-font-smoothing: antialiased; font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
}}
[data-testid="stMetricValue"], [data-testid="stMetricDelta"], [data-testid="stDataFrame"],
.msc-kpi-value, .msc-hero-value {{ font-variant-numeric: tabular-nums; }}
.block-container {{ padding-top: 3.2rem; padding-bottom: 3rem; }}
[data-testid="stDecoration"] {{ display: none; }}

/* ---------- Hero band ---------- */
.msc-header {{
  position: relative; overflow: hidden; border-radius: 18px; min-height: 196px; margin-bottom: 16px;
  background: {hero_bg}; color: #fff; box-shadow: 0 18px 40px rgba(11,18,32,0.28);
  display: flex; align-items: flex-end; padding: 26px 30px;
}}
.msc-header::before {{
  content: ""; position: absolute; inset: 0;
  background: linear-gradient(90deg, rgba(11,18,32,0.92) 0%, rgba(11,18,32,0.72) 45%, rgba(11,18,32,0.15) 100%);
}}
.msc-header > * {{ position: relative; }}
.msc-header .msc-eyebrow {{ color: #f59e0b; margin-bottom: 6px; }}
.msc-header h1 {{
  margin: 0; font-family: "Space Grotesk", Inter, sans-serif; font-size: 2.35rem; font-weight: 700;
  letter-spacing: 0.01em; text-transform: uppercase; line-height: 1.02; color: #fff;
}}
.msc-header p {{ margin: 8px 0 0; font-size: 0.95rem; color: rgba(255,255,255,0.78); max-width: 640px; }}
.msc-header .msc-chips {{ margin-left: auto; display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end;
  align-self: flex-start; }}
.msc-chip {{
  display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 999px;
  background: rgba(255,255,255,0.10); border: 1px solid rgba(255,255,255,0.28); font-size: 0.78rem;
  font-weight: 600; color: #fff; white-space: nowrap; backdrop-filter: blur(6px);
}}
.msc-chip.ok {{ background: rgba(46,158,91,0.55); border-color: rgba(46,158,91,0.9); }}
.msc-chip.bad {{ background: rgba(214,69,69,0.55); border-color: rgba(214,69,69,0.9); }}

/* ---------- Editorial eyebrow label ---------- */
.msc-eyebrow {{
  font-family: "Space Grotesk", Inter, sans-serif; font-size: 0.72rem; font-weight: 700;
  letter-spacing: 0.16em; text-transform: uppercase; color: #6b7280;
}}

/* ---------- Tabs: uppercase, accent underline ---------- */
.stTabs [role="tablist"] {{ gap: 4px; border-bottom: 1px solid #e4e1d8; }}
.stTabs [data-testid="stTab"] {{ height: 46px; padding: 0 14px; border-radius: 0; }}
.stTabs [data-testid="stTab"] p {{
  font-family: "Space Grotesk", Inter, sans-serif !important; font-weight: 600 !important;
  font-size: 0.78rem !important; letter-spacing: 0.1em; text-transform: uppercase; color: #5b6472;
}}
.stTabs [data-testid="stTab"]:hover {{ background: rgba(20,26,38,0.05); }}
.stTabs [data-testid="stTab"]:hover p {{ color: #141a26; }}
.stTabs [data-testid="stTabHighlight"], .stTabs [data-baseweb="tab-highlight"] {{ display: none; }}
{tab_rules}

/* ---------- Section title ---------- */
.msc-section {{ display: flex; align-items: center; gap: 12px; margin: 2px 0 12px; }}
.msc-section .msc-sqr {{
  width: 36px; height: 36px; border-radius: 10px; background: rgba(31,78,121,0.09); color: {NAVY};
  display: flex; align-items: center; justify-content: center; flex: 0 0 36px;
}}
.msc-section .msc-ttl {{ font-family: "Space Grotesk", Inter, sans-serif; font-weight: 600; font-size: 1.05rem;
  color: #141a26; line-height: 1.2; }}
.msc-section .msc-cap {{ font-size: 0.8rem; color: #6b7280; margin-top: 2px; }}

/* ---------- Verdict banner ---------- */
.msc-hero {{
  display: flex; align-items: center; gap: 18px; padding: 18px 22px; border-radius: 14px; margin: 4px 0 10px;
  color: #fff; box-shadow: 0 10px 24px rgba(11,18,32,0.18);
}}
.msc-hero.ok {{ background: linear-gradient(120deg, #166534 0%, #2e9e5b 100%); }}
.msc-hero.bad {{ background: linear-gradient(120deg, #7f1d1d 0%, #d64545 100%); }}
.msc-hero.na {{ background: linear-gradient(120deg, #0b1220 0%, #1f4e79 100%); }}
.msc-hero .msc-hero-ico {{
  width: 56px; height: 56px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  flex: 0 0 56px; background: rgba(255,255,255,0.18); border: 1px solid rgba(255,255,255,0.35);
}}
.msc-hero-label {{ font-family: "Space Grotesk", Inter, sans-serif; font-size: 0.72rem; text-transform: uppercase;
  letter-spacing: 0.14em; color: rgba(255,255,255,0.8); font-weight: 700; }}
.msc-hero-value {{ font-family: "Space Grotesk", Inter, sans-serif; font-size: 1.9rem; font-weight: 700;
  line-height: 1.1; color: #fff; }}
.msc-hero-sub {{ font-size: 0.88rem; color: rgba(255,255,255,0.85); margin-top: 3px; }}

/* ---------- KPI tiles ---------- */
[data-testid="stMetric"] {{ background: #fff; border-radius: 12px; }}
[data-testid="stMetricLabel"] p {{ font-size: 0.8rem; color: #5b6472; }}
[data-testid="stMetricValue"] {{ font-family: "Space Grotesk", Inter, sans-serif; }}
.msc-kpi {{ padding: 10px 12px; border: 1px solid #e4e1d8; border-radius: 10px; background: #fff; }}
.msc-kpi-label {{ font-size: 0.76rem; color: #6b7280; display: flex; align-items: center; gap: 5px; }}
.msc-kpi-value {{ font-family: "Space Grotesk", Inter, sans-serif; font-size: 1.2rem; font-weight: 600;
  color: #141a26; margin-top: 2px; }}
{accent_rules}

/* ---------- Cards and tables ---------- */
[data-testid="stVerticalBlockBorderWrapper"] {{ background: #fff; border-radius: 14px; }}
[data-testid="stDataFrame"] {{ border-radius: 10px; overflow: hidden; }}

/* ---------- Sidebar: lights off ---------- */
[data-testid="stSidebar"] {{ background: {side_bg}; }}
[data-testid="stSidebar"] > div:first-child {{ background: rgba(11,18,32,0.55); }}
[data-testid="stSidebarUserContent"] {{ padding-top: 1.4rem; }}
[data-testid="stSidebar"] .msc-section .msc-ttl {{ color: #fff; }}
[data-testid="stSidebar"] .msc-section .msc-cap {{ color: #9aa4b5; }}
[data-testid="stSidebar"] .msc-section .msc-sqr {{ background: rgba(245,158,11,0.18); color: #f59e0b; }}
[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] {{
  background: rgba(21,30,48,0.85); border-color: #263247; }}
[data-testid="stSidebar"] [data-testid="stExpander"] details {{ background: rgba(21,30,48,0.85);
  border-color: #263247; border-radius: 12px; }}
[data-testid="stSidebar"] [data-testid="stExpander"] summary {{ font-weight: 600; color: #fff; }}
[data-testid="stSidebar"] [data-testid="stMetric"] {{ background: rgba(255,255,255,0.05); border-color: #263247; }}
[data-testid="stSidebar"] [data-testid="stMetricLabel"] p {{ color: #c3cad6; }}
[data-testid="stSidebar"] .msc-kpi {{ background: rgba(255,255,255,0.05); border-color: #263247; }}
[data-testid="stSidebar"] .msc-kpi-value {{ color: #fff; }}
</style>
"""


def inject_css() -> None:
    st.markdown(_css(), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------
_LOGO_SVG = """
<svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <circle cx="8" cy="12" r="6" stroke="#fff" stroke-width="2" opacity="0.9"/>
  <circle cx="16" cy="12" r="6" stroke="#fff" stroke-width="2"/>
  <path d="M12 7.6a6 6 0 0 1 0 8.8a6 6 0 0 1 0-8.8z" fill="#f59e0b" opacity="0.95"/>
</svg>
"""


def render_header(title: str, subtitle: str, chips: list[tuple[str, str, str]], eyebrow: str = "") -> None:
    """Hero band. `chips` = [(icon_key, text, state)] with state in {"", "ok", "bad"}."""
    chips_html = "".join(
        f'<span class="msc-chip {state}">{_sym(ic, 16)}{html.escape(text)}</span>' for ic, text, state in chips
    )
    eyebrow_html = f'<div class="msc-eyebrow">{_LOGO_SVG} {html.escape(eyebrow)}</div>' if eyebrow else ""
    st.markdown(
        f'<div class="msc-header"><div>{eyebrow_html}<h1>{html.escape(title)}</h1>'
        f'<p>{html.escape(subtitle)}</p></div><div class="msc-chips">{chips_html}</div></div>',
        unsafe_allow_html=True,
    )


def scope(key: str):
    """Container that carries a tab's accent colour (CSS class st-key-scope_<key>)."""
    return st.container(key=f"scope_{key}")


def eyebrow(text: str) -> None:
    st.markdown(f'<div class="msc-eyebrow">{html.escape(text)}</div>', unsafe_allow_html=True)


def section(icon_key: str, title: str, caption: str | None = None) -> None:
    """Section header: tinted icon square + bold title + optional caption. Replaces card_title."""
    cap = f'<div class="msc-cap">{html.escape(caption)}</div>' if caption else ""
    st.markdown(
        f'<div class="msc-section"><div class="msc-sqr">{_sym(icon_key, 22)}</div>'
        f'<div><div class="msc-ttl">{html.escape(title)}</div>{cap}</div></div>',
        unsafe_allow_html=True,
    )


def hero(state: str, label: str, value: str, sub: str = "", icon_key: str | None = None) -> None:
    """Verdict banner. state in {"ok", "bad", "na"}."""
    ic = icon_key or {"ok": "accretive", "bad": "dilutive"}.get(state, "info")
    st.markdown(
        f'<div class="msc-hero {state}"><div class="msc-hero-ico">{_sym(ic, 30, "#fff")}</div>'
        f'<div><div class="msc-hero-label">{html.escape(label)}</div>'
        f'<div class="msc-hero-value">{html.escape(value)}</div>'
        f'<div class="msc-hero-sub">{html.escape(sub)}</div></div></div>',
        unsafe_allow_html=True,
    )


def kpi(label: str, value: str, icon_key: str | None = None, parent=None) -> None:
    """Compact KPI tile (HTML). For the main dashboards use `metric`."""
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
