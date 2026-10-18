"""Sidebar: global deal inputs. Returns them as a namespace plus the base parameter dict for the engine."""
from __future__ import annotations

from types import SimpleNamespace

import streamlit as st

from engine import MAX_M, MAX_PX, MAX_SH, MAX_SYN, YEARS, run_rate_synergies

from .components import card

BASIS_DCF = "Intrinsic value (DCF)"
BASIS_MARKET = "Market price"


def render_sidebar() -> tuple:
    """
    Draw the sidebar and return (export_box, inputs). `export_box` is an empty card at the top of the
    sidebar that the pitchbook section fills at the end of the run, once every table exists.
    `inputs.P` is the engine parameter dict; the DCF and capital structure tabs complete it.
    """
    sb = st.sidebar
    export_box = card(sb)
    sb.divider()
    sb.header("Deal inputs")

    with card(sb):
        st.markdown("**Acquirer**")
        acq_ni = st.number_input("Net income (M)", value=500.0, min_value=-MAX_M, max_value=MAX_M, step=10.0,
                                 key="acq_ni")
        acq_sh = st.number_input("Shares outstanding (M)", value=200.0, min_value=0.01, max_value=MAX_SH, step=1.0,
                                 key="acq_sh")
        acq_px = st.number_input("Current share price", value=50.0, min_value=0.01, max_value=MAX_PX, step=0.5,
                                 key="acq_px")
        acq_ebitda = st.number_input("EBITDA (M)", value=900.0, min_value=-MAX_M, max_value=MAX_M, step=10.0,
                                     key="acq_ebitda")
        acq_netdebt = st.number_input("Existing net debt (M)", value=1200.0, min_value=-MAX_M, max_value=MAX_M,
                                      step=50.0, key="acq_netdebt")
        acq_cash = st.number_input("Cash available for the deal (M)", value=600.0, min_value=0.0, max_value=MAX_M,
                                   step=50.0, key="acq_cash",
                                   help="Cap on the balance sheet cash that can be used to pay the cash component.")

    with card(sb):
        st.markdown("**Target: market data**")
        tgt_sh = st.number_input("Shares outstanding (M)", value=80.0, min_value=0.01, max_value=MAX_SH, step=1.0,
                                 key="tgt_sh")
        tgt_px = st.number_input("Current share price", value=20.0, min_value=0.01, max_value=MAX_PX, step=0.5,
                                 key="tgt_px")
        tgt_book = st.number_input("Book value of equity (M)", value=600.0, min_value=-MAX_M, max_value=MAX_M,
                                   step=10.0, key="tgt_book",
                                   help="Target's book equity: the starting point of the purchase price allocation.")
        st.caption("Target net income is derived from the DCF (DCF Valuation tab).")

    with card(sb):
        st.markdown("**Consideration**")
        price_basis = st.radio("Target price basis", [BASIS_DCF, BASIS_MARKET], index=0, key="basis",
                               help="With DCF, the valuation's equity value sets the price the premium is applied to.")
        premium = st.slider("Premium over base price (%)", 0.0, 100.0, 30.0, 1.0, key="premium") / 100
        cash_pct = st.slider("Cash consideration (%)", 0, 100, 50, 5, key="cash_pct")
        st.caption(f"Stock consideration: {100 - cash_pct}%")
        tax = st.number_input("Corporate tax rate (%)", value=25.0, min_value=0.0, max_value=100.0,
                              step=1.0, key="tax") / 100

    with card(sb):
        st.markdown("**Synergies (run-rate, pre-tax)**")
        cost_syn = st.number_input("Cost synergies (M)", value=60.0, min_value=0.0, max_value=MAX_SYN, step=5.0,
                                   key="cost_syn")
        rev_syn = st.number_input("Revenue synergies (M)", value=20.0, min_value=0.0, max_value=MAX_SYN, step=5.0,
                                  key="rev_syn")
        rev_syn_margin = st.number_input("EBITDA margin on revenue synergies (%)", value=30.0, min_value=0.0,
                                         max_value=100.0, step=1.0, key="rev_syn_mg",
                                         help="Only the margin on incremental sales reaches profit.") / 100
        integration = st.number_input("One-off integration costs (M)", value=30.0, min_value=0.0,
                                      max_value=MAX_SYN, step=5.0, key="integ")
        total_syn = run_rate_synergies(cost_syn, rev_syn, rev_syn_margin)
        st.caption(f"Run-rate synergies at EBITDA level: {cost_syn:,.1f} + {rev_syn:,.1f} × {rev_syn_margin:.0%} "
                   f"= **{total_syn:,.1f} M**")

    with card(sb):
        st.markdown("**Purchase price allocation (PPA)**")
        ppa_intang_pct = st.slider("Excess price allocated to intangibles (%)", 0, 100, 30, 5, key="ppa_pct",
                                   help="Brands, customer relationships, technology... They are amortised; "
                                        "the rest of the excess is goodwill.") / 100
        ppa_life = st.number_input("Useful life of intangibles (years)", value=10, min_value=1, max_value=40, step=1,
                                   key="ppa_life")

    with card(sb):
        st.markdown("**Phasing and analysis year**")
        st.caption("Share of run-rate synergies captured each year. Summary, Sensitivity and Monte Carlo use it.")
        phase_pct = [
            st.slider("Year 1 (%)", 0, 100, 50, 5, key="ph1"),
            st.slider("Year 2 (%)", 0, 100, 75, 5, key="ph2"),
            st.slider("Year 3 (%)", 0, 100, 100, 5, key="ph3"),
        ]
        if any(b < a for a, b in zip(phase_pct, phase_pct[1:])):
            st.warning("Synergy capture should not decrease over time.")
        year_sel = st.selectbox("Analysis year (Summary, Sensitivity, Monte Carlo)", YEARS, index=0, key="year")

    phases = [v / 100 for v in phase_pct]
    P = dict(acq_ni=acq_ni, acq_sh=acq_sh, acq_px=acq_px, acq_ebitda=acq_ebitda, acq_netdebt=acq_netdebt,
             acq_cash=acq_cash, tgt_sh=tgt_sh, tgt_px=tgt_px, cash_w=cash_pct / 100, tax=tax,
             total_syn=total_syn, integration=integration, phases=phases,
             tgt_book_equity=tgt_book, ppa_intang_pct=ppa_intang_pct, ppa_life=int(ppa_life))
    inputs = SimpleNamespace(
        P=P, use_dcf_basis=price_basis == BASIS_DCF, price_basis=price_basis, premium=premium, cash_pct=cash_pct,
        tax=tax, cost_syn=cost_syn, rev_syn=rev_syn, rev_syn_margin=rev_syn_margin, total_syn=total_syn,
        integration=integration, phases=phases, year_sel=year_sel, yi=YEARS.index(year_sel),
    )
    return export_box, inputs
