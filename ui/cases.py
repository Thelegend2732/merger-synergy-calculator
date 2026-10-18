"""
Case loading: preset deals and live import from Yahoo Finance.

Every widget reads its value from st.session_state (no `value=` argument), so loading a case is just
writing the case's values into session state inside a button callback, before widgets are drawn.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from engine import MAX_PX
from marketdata.cases import BASIS_MARKET, CASES, DEFAULT_VALUES, ILLUSTRATIVE
from marketdata.yahoo import (
    EQUITY_RISK_PREMIUM, RISK_FREE, MarketDataError, acquirer_inputs, fetch_company, target_inputs,
)

from .components import ST_BTN, card

INFO_KEY = "case_info"     # metadata of the loaded case (shown above the tabs)
ERROR_KEY = "case_error"   # last import error, shown once in the sidebar


COMPS_COLS = ["Company", "Ticker", "EV/EBITDA", "EV/Revenue"]
PREC_COLS = ["Deal", "Year", "EV/EBITDA", "EV/Revenue"]


def table_state(rows: list, cols: list) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=cols).astype({"EV/EBITDA": float, "EV/Revenue": float})


def set_tables(comps: list, precedents: list, note: str = "") -> None:
    """Replace the comps / precedents tables and discard pending edits in their data editors."""
    st.session_state["comps"] = table_state(comps, COMPS_COLS)
    st.session_state["precedents"] = table_state(precedents, PREC_COLS)
    st.session_state["comps_note"] = note
    for k in ("comps_editor", "prec_editor"):
        st.session_state.pop(k, None)


def init_state() -> None:
    """Seed every widget with the illustrative case on the first run of a session."""
    for k, v in DEFAULT_VALUES.items():
        st.session_state.setdefault(k, v)
    if INFO_KEY not in st.session_state:
        st.session_state[INFO_KEY] = ILLUSTRATIVE
        set_tables(ILLUSTRATIVE["comps"], ILLUSTRATIVE["precedents"], ILLUSTRATIVE["comps_note"])


def _apply(values: dict) -> None:
    for k, v in values.items():
        st.session_state[k] = v


def _load_preset() -> None:
    case = CASES[st.session_state["case_choice"]]
    _apply(case["values"])
    set_tables(case["comps"], case["precedents"], case["comps_note"])
    st.session_state[INFO_KEY] = case
    st.session_state.pop(ERROR_KEY, None)


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_fetch(ticker: str) -> dict:
    return fetch_company(ticker)


def _px_or_none(v) -> float | None:
    return None if v is None else round(min(max(float(v), 0.01), MAX_PX), 2)


def _load_market() -> None:
    acq_tk, tgt_tk = st.session_state.get("tk_acq", ""), st.session_state.get("tk_tgt", "")
    try:
        acq, tgt = _cached_fetch(acq_tk.strip().upper()), _cached_fetch(tgt_tk.strip().upper())
    except MarketDataError as exc:
        st.session_state[ERROR_KEY] = str(exc)
        return
    tax = st.session_state["tax"] / 100
    tgt_vals, w = target_inputs(tgt, tax)
    _apply({**acquirer_inputs(acq), **tgt_vals, "basis": BASIS_MARKET,
            "w52_lo": _px_or_none(tgt.get("low_52w")), "w52_hi": _px_or_none(tgt.get("high_52w"))})
    set_tables([], [], "Add peers by ticker (current multiples) or type them in.")

    notes = [
        f"Acquirer: {acq['name']} ({acq['ticker']}), fiscal year ended {acq['fiscal_year_end']}, "
        f"price {acq['price']:,.2f} {acq['currency']}.",
        f"Target: {tgt['name']} ({tgt['ticker']}), fiscal year ended {tgt['fiscal_year_end']}, "
        f"price {tgt['price']:,.2f} {tgt['currency']}.",
        "Target revenue growth = historical revenue CAGR; margins, D&A and capex = latest fiscal year ratios.",
        f"WACC ≈ {w['wacc']:.2%}: CAPM cost of equity {w['ke']:.2%} (risk-free {RISK_FREE:.2%} + beta "
        f"{w['beta']:.2f} × ERP {EQUITY_RISK_PREMIUM:.2%}), pre-tax cost of debt {w['kd']:.2%}, debt weight "
        f"{w['w_d']:.0%}.",
        "Deal terms (premium, consideration mix, synergies, funding, PPA) were kept from the previous case: "
        "review them for this pair.",
    ]
    currencies = {acq["financial_currency"], tgt["financial_currency"], acq["currency"], tgt["currency"]}
    if len(currencies) > 1:
        notes.insert(0, f"⚠ Mixed currencies ({', '.join(sorted(c for c in currencies if c))}): the model assumes "
                        "one currency, so convert figures before relying on the results.")
    st.session_state[INFO_KEY] = dict(
        name=f"{acq['ticker']} / {tgt['ticker']} (live market data)",
        description=f"{acq['name']} acquiring {tgt['name']}, using the latest annual statements and current "
                    f"share prices from Yahoo Finance. Millions of {acq['financial_currency']}.",
        sources=[("Yahoo Finance via yfinance", f"https://finance.yahoo.com/quote/{tgt['ticker']}")],
        assumptions=notes,
    )
    st.session_state.pop(ERROR_KEY, None)


def render_case_loader(parent) -> None:
    """Sidebar card to load a preset deal or import two companies by ticker."""
    with card(parent):
        st.markdown("**Deal case**")
        st.selectbox("Preset", list(CASES), key="case_choice", label_visibility="collapsed")
        st.button("Load preset", on_click=_load_preset, **ST_BTN)
        with st.expander("Import from Yahoo Finance"):
            c1, c2 = st.columns(2)
            c1.text_input("Acquirer ticker", key="tk_acq", placeholder="e.g. CDNS")
            c2.text_input("Target ticker", key="tk_tgt", placeholder="e.g. PTC")
            st.button("Fetch and load", on_click=_load_market, **ST_BTN,
                      disabled=not (st.session_state.get("tk_acq") and st.session_state.get("tk_tgt")))
            st.caption("Loads both companies' latest annual financials and current prices. Requires internet.")
        if st.session_state.get(ERROR_KEY):
            st.error(st.session_state[ERROR_KEY])


def render_case_banner() -> None:
    """Expandable note above the tabs describing the loaded case, its sources and assumptions."""
    info = st.session_state.get(INFO_KEY)
    if not info:
        return
    with st.expander(f"Case: {info['name']}", expanded=False):
        st.markdown(info["description"])
        if info["sources"]:
            st.markdown("**Sources**")
            st.markdown("\n".join(f"- [{label}]({url})" if url else f"- {label}" for label, url in info["sources"]))
        if info["assumptions"]:
            st.markdown("**Assumptions and caveats**")
            st.markdown("\n".join(f"- {a}" for a in info["assumptions"]))
