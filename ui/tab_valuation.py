"""Tab 2: relative valuation — trading comps, precedent transactions and the football field."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engine import (
    AMBER, GREY, MAX_PX, MULTIPLES, NAVY, RED, fmt_value, football_field, implied_multiples, make_table,
    multiple_stats,
)
from marketdata.yahoo import MarketDataError, fetch_multiples

from .cases import COMPS_COLS, table_state
from .components import ST_BTN, ST_DF, card, card_title, gap, show_chart, show_table, style_fig

EDITOR_CFG = {
    "EV/EBITDA": st.column_config.NumberColumn("EV/EBITDA", format="%.1fx", min_value=0.0),
    "EV/Revenue": st.column_config.NumberColumn("EV/Revenue", format="%.2fx", min_value=0.0),
}


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_multiples(ticker: str) -> dict:
    return fetch_multiples(ticker)


def _fetch_peers() -> None:
    """Callback: append current multiples for the tickers typed by the user."""
    tickers = [t.strip().upper() for t in st.session_state.get("peer_tickers", "").replace(";", ",").split(",")]
    rows, errors = [], []
    for tk in filter(None, tickers):
        try:
            m = _cached_multiples(tk)
            rows.append({c: m.get(c) for c in COMPS_COLS})
        except MarketDataError as exc:
            errors.append(str(exc))
    current = st.session_state["comps"]
    if rows:
        st.session_state["comps"] = pd.concat([current, table_state(rows, COMPS_COLS)], ignore_index=True)
        st.session_state.pop("comps_editor", None)
        st.session_state["comps_note"] = "Includes current multiples from Yahoo Finance (latest fiscal year, GAAP EBITDA)."
    st.session_state["peer_errors"] = errors


def _stats_table(df: pd.DataFrame, label: str):
    rows = []
    for m in MULTIPLES:
        s = multiple_stats(df[m]) if m in df else multiple_stats([])
        rows.append((f"{label} {m}", [s["p25"], s["median"], s["p75"]], "x"))
    return rows


def render(inp, dcf_out: dict, deal: dict) -> dict:
    P = inp.P
    target = dict(ebitda=P["tgt_ebitda"], revenue=dcf_out["dcf_inputs"]["rev0"], net_debt=P["tgt_netdebt"],
                  shares=P["tgt_sh"])
    gap()
    left, right = st.columns([3, 2], gap="medium")
    with left, card():
        card_title("Trading comparables", st.session_state.get("comps_note") or None)
        comps = st.data_editor(st.session_state["comps"], key="comps_editor", num_rows="dynamic",
                               hide_index=True, column_config=EDITOR_CFG, **ST_DF)
        c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
        c1.text_input("Add peers by ticker (current multiples)", key="peer_tickers", placeholder="e.g. CDNS, PTC, ADSK")
        c2.button("Fetch", on_click=_fetch_peers, disabled=not st.session_state.get("peer_tickers"), **ST_BTN)
        for err in st.session_state.get("peer_errors", []):
            st.warning(err)
    with right, card():
        card_title("Precedent transactions", "Multiples paid in comparable acquisitions (control premium included).")
        precedents = st.data_editor(st.session_state["precedents"], key="prec_editor", num_rows="dynamic",
                                    hide_index=True, column_config=EDITOR_CFG, **ST_DF)
        w1, w2 = st.columns(2)
        w52_lo = w1.number_input("52-week low (unaffected)", min_value=0.01, max_value=MAX_PX, key="w52_lo")
        w52_hi = w2.number_input("52-week high (unaffected)", min_value=0.01, max_value=MAX_PX, key="w52_hi")

    ff = football_field(target, comps, precedents, dcf_out["dcf_sens"],
                        (w52_lo, w52_hi) if w52_lo and w52_hi else None)
    own = implied_multiples(target, offer_equity_value=deal["equity_value"], market_price=P["tgt_px"])
    multiples = make_table("Multiple", ["25th pct", "Median", "75th pct"],
                           _stats_table(comps, "Trading comps") + _stats_table(precedents, "Precedents"))
    target_multiples = make_table("Target multiple", ["At market", "At offer"], [
        (m, [own["market"][m], own["offer"][m]], "x") for m in MULTIPLES
    ])

    # --- Football field ---
    gap()
    with card():
        if ff.empty:
            st.info("Add peer or precedent multiples (or a valid DCF) to build the football field.")
        else:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                y=ff["Method"], x=ff["High"] - ff["Low"], base=ff["Low"], orientation="h",
                marker_color=[NAVY if m.startswith("Trading") else AMBER if m.startswith("Precedent")
                              else GREY for m in ff["Method"]],
                text=[f"{lo:,.2f} – {hi:,.2f}" for lo, hi in zip(ff["Low"], ff["High"])], textposition="outside",
                cliponaxis=False,
                customdata=np.stack([ff["Low"], ff["Mid"], ff["High"], ff["Basis"]], axis=-1),
                hovertemplate="%{y}<br>Low %{customdata[0]:,.2f} · Mid %{customdata[1]:,.2f} · "
                              "High %{customdata[2]:,.2f}<br>%{customdata[3]}<extra></extra>",
            ))
            fig.add_trace(go.Scatter(y=ff["Method"], x=ff["Mid"], mode="markers", name="Midpoint",
                                     marker=dict(color="#ffffff", size=8, line=dict(color=NAVY, width=1.5)),
                                     hoverinfo="skip"))
            fig.add_vline(x=P["tgt_px"], line_dash="dot", line_color=GREY,
                          annotation_text=f"Market {P['tgt_px']:,.2f}", annotation_position="bottom right")
            fig.add_vline(x=deal["offer_price"], line_dash="dash", line_color=RED, line_width=2,
                          annotation_text=f"Offer {deal['offer_price']:,.2f}", annotation_position="top right")
            lo = min(ff["Low"].min(), P["tgt_px"], deal["offer_price"])
            hi = max(ff["High"].max(), P["tgt_px"], deal["offer_price"])
            span = max(hi - lo, 1e-6)
            fig.update_layout(showlegend=False, xaxis_title="Value per Target share", yaxis_autorange="reversed",
                              bargap=0.35, xaxis_range=[lo - 0.05 * span, hi + 0.25 * span])   # room for labels
            style_fig(fig, "Football field: implied value per share vs. offer", height=110 + 70 * len(ff))
            show_chart(fig)
            above = ff[ff["High"] < deal["offer_price"]]["Method"].tolist()
            if above:
                st.caption("The offer exceeds the top of: " + "; ".join(above) + ".")

    gap()
    t1, t2 = st.columns([3, 2], gap="medium")
    with t1, card():
        card_title("Implied value ranges per share")
        st.dataframe(ff.style.format({"Low": "{:,.2f}", "Mid": "{:,.2f}", "High": "{:,.2f}"}),
                     hide_index=True, **ST_DF)
    with t2, card():
        card_title("Peer multiples vs. the Target")
        show_table(multiples)
        show_table(target_multiples)
        st.caption(f"Target LTM EBITDA {fmt_value(target['ebitda'], 'm1')} M, revenue "
                   f"{fmt_value(target['revenue'], 'm1')} M, net debt {fmt_value(target['net_debt'], 'm1')} M.")

    with st.expander("Methodology"):
        st.markdown(
            """
- **Implied value per share** = (peer multiple × Target LTM metric − Target net debt) / Target shares.
- Ranges use the **interquartile range** (25th–75th percentile) of the peer multiples; the marker is the median.
- **Precedent transactions** include a control premium, so they usually sit above trading comps.
- **DCF** range: central 3×3 block of the WACC × g grid (±0.5 pp around the base case).
- Multiples must be consistent with the Target metrics: GAAP EBITDA here, as reported in the statements.
            """
        )

    comps_out = comps.copy()
    prec_out = precedents.copy()
    return dict(comps=comps_out, precedents=prec_out, football=ff, multiples=multiples,
                target_multiples=target_multiples)
