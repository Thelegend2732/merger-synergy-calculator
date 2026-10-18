"""Tab 1: Target DCF valuation. Sets the base price and the Target net income used everywhere else."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from engine import DCF_YEARS, GREEN, GREY, MAX_M, NAVY, RED, YEARS, dcf_valuation, fmt_value, make_table, safe_div

from .components import BLUE_SCALE, cached_dcf_sensitivity, card, card_title, gap, show_chart, show_table, style_fig


def render(inp) -> dict:
    P = inp.P
    tgt_sh, tgt_px = P["tgt_sh"], P["tgt_px"]
    gap()
    dash = card()   # dashboard: filled once the DCF is computed, but shown at the top
    gap()

    col_in, col_out = st.columns([2, 1], gap="medium")
    with col_in, card():
        card_title("Operating and valuation assumptions", "5-year DCF with a Gordon growth terminal value.")
        c1, c2, c3 = st.columns(3)
        rev0 = c1.number_input("LTM revenue (M)", value=640.0, min_value=0.0, max_value=MAX_M, step=10.0,
                               key="dcf_rev")
        growth = c1.number_input("Annual revenue growth (%)", value=6.0, min_value=-50.0, max_value=100.0,
                                 step=0.5, key="dcf_gr") / 100
        margin = c2.number_input("EBITDA margin (%)", value=27.0, min_value=0.0, max_value=100.0, step=0.5,
                                 key="dcf_mg") / 100
        da_pct = c2.number_input("D&A (% of revenue)", value=6.0, min_value=0.0, max_value=100.0, step=0.5,
                                 key="dcf_da") / 100
        capex_pct = c3.number_input("Capex (% of revenue)", value=7.0, min_value=0.0, max_value=100.0, step=0.5,
                                    key="dcf_cx") / 100
        nwc_pct = c3.number_input("NWC investment (% of Δ revenue)", value=10.0, min_value=0.0, max_value=100.0,
                                  step=1.0, key="dcf_nwc") / 100
        c4, c5, c6, c7 = st.columns(4)
        wacc = c4.number_input("WACC (%)", value=8.5, min_value=0.5, max_value=30.0, step=0.25, key="dcf_wacc") / 100
        g_perp = c5.number_input("Perpetual growth g (%)", value=2.5, min_value=-2.0, max_value=10.0,
                                 step=0.25, key="dcf_g") / 100
        tgt_netdebt = c6.number_input("Target net debt (M)", value=100.0, min_value=-MAX_M, max_value=MAX_M,
                                      step=10.0, key="dcf_nd")
        td_rate = c7.number_input("Interest rate on its net debt (%)", value=5.0, min_value=0.0, max_value=30.0,
                                  step=0.25, key="dcf_td",
                                  help="Used to derive Target net income (EBIT − interest, after tax).") / 100

    dcf_inputs = dict(rev0=rev0, growth=growth, margin=margin, da_pct=da_pct, capex_pct=capex_pct,
                      nwc_pct=nwc_pct, wacc=wacc, g=g_perp, net_debt=tgt_netdebt, td_rate=td_rate,
                      shares=tgt_sh, tax=inp.tax)
    dcf = dcf_valuation(dcf_inputs)

    # Target figures consumed by the other tabs (single source: the DCF)
    target = dict(tgt_ebitda=rev0 * margin, tgt_netdebt=tgt_netdebt,
                  tgt_ni_y=[float(v) for v in dcf["ni"][:len(YEARS)]])

    use_dcf = inp.use_dcf_basis and dcf["valid"]
    base_price = dcf["price"] if use_dcf else tgt_px
    base_label = "DCF (intrinsic value)" if use_dcf else "market price"
    mkt_cap = tgt_px * tgt_sh

    with dash:
        card_title("Target valuation")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Enterprise value", fmt_value(dcf["ev"], "m1"))
        k2.metric("Equity value (DCF)", fmt_value(dcf["equity"], "m1"),
                  delta=fmt_value(safe_div(dcf["equity"], mkt_cap) - 1, "pct_s") + " vs. market"
                  if dcf["valid"] else None)
        k3.metric("Intrinsic value per share", fmt_value(dcf["price"], "m2"))
        k4.metric("Market price per share", fmt_value(tgt_px, "m2"))
        if not dcf["valid"]:
            st.error(f"Invalid DCF: {dcf['reason']} The market price is used as the Target base price.")

    with col_out, card():
        card_title("Deal base price")
        st.markdown(f"### {base_price:,.2f}")
        st.caption(f"Per share, based on the {base_label}. The {inp.premium:.0%} premium is applied on top.")
        st.divider()
        card_title("Target net income (EPS input)")
        for col, yr, val in zip(st.columns(len(YEARS)), YEARS, target["tgt_ni_y"]):
            col.caption(yr)
            col.markdown(f"**{val:,.1f}**")
        st.caption("Millions. From the DCF: (EBIT − interest on its net debt) × (1 − t).")

    # --- Tables ---
    yrs = [f"Year {i}" for i in dcf["years"]]
    dcf_proj = make_table("Line item (M)", yrs, [
        ("Revenue", dcf["rev"], "m1"),
        ("Revenue growth", dcf["growth_row"], "pct"),
        ("EBITDA", dcf["ebitda"], "m1"),
        ("Memo: D&A", dcf["da"], "m1"),
        ("Memo: EBIT", dcf["ebit"], "m1"),
        ("(−) Taxes on EBIT", -dcf["taxes"], "m1"),
        ("(−) Capex", -dcf["capex"], "m1"),
        ("(−) NWC investment", -dcf["d_nwc"], "m1"),
        ("Free cash flow", dcf["fcf"], "m1"),
        ("Discount factor", dcf["disc"], "eps"),
        ("PV of FCF", dcf["pv_fcf"], "m1"),
        ("Memo: interest on Target net debt", np.full(DCF_YEARS, dcf["interest_td"]), "m1"),
        ("Memo: Target net income (EPS input)", dcf["ni"], "m1"),
    ])
    dcf_bridge = make_table("Valuation bridge", ["Value"], [
        ("Sum of PV of FCF (5 years)", dcf["sum_pv"], "m1"),
        ("Terminal value (Year 5)", dcf["tv"], "m1"),
        ("PV of terminal value", dcf["pv_tv"], "m1"),
        ("Enterprise value", dcf["ev"], "m1"),
        ("(−) Target net debt", -tgt_netdebt, "m1"),
        ("Equity value", dcf["equity"], "m1"),
        ("Target shares (M)", tgt_sh, "m2"),
        ("Intrinsic value per share", dcf["price"], "m2"),
        ("Market price per share", tgt_px, "m2"),
        ("DCF premium / (discount) to market", safe_div(dcf["price"], tgt_px) - 1, "pct_s"),
        ("Terminal value as % of EV", safe_div(dcf["pv_tv"], dcf["ev"]), "pct"),
        ("Implied EV / LTM EBITDA", safe_div(dcf["ev"], target["tgt_ebitda"]), "x"),
        ("Implied TV / Year 5 EBITDA", safe_div(dcf["tv"], dcf["ebitda"][-1]), "x"),
    ])

    st.divider()
    left, right = st.columns([3, 2], gap="medium")
    with left, card():
        card_title("Free cash flow and net income forecast")
        show_table(dcf_proj)
    with right, card():
        card_title("EV to equity value bridge")
        show_table(dcf_bridge)

    # --- Charts ---
    gap()
    g1, g2 = st.columns([3, 2], gap="medium")
    fcf_fig = go.Figure()
    fcf_fig.add_trace(go.Bar(x=yrs, y=dcf["fcf"], name="FCF", marker_color=NAVY,
                             text=[f"{v:,.1f}" for v in dcf["fcf"]], textposition="outside"))
    fcf_fig.add_trace(go.Bar(x=yrs, y=dcf["pv_fcf"], name="PV of FCF", marker_color=GREY))
    fcf_fig.update_layout(barmode="group", yaxis_title="M", legend=dict(orientation="h", y=1.12, x=1, xanchor="right"))
    style_fig(fcf_fig, "Projected free cash flow", height=400)
    with g1, card():
        show_chart(fcf_fig)

    if dcf["valid"]:
        steps = [dcf["sum_pv"], dcf["pv_tv"], dcf["ev"], -tgt_netdebt, dcf["equity"]]
        ev_fig = go.Figure(go.Waterfall(
            x=["PV of FCF", "PV of TV", "EV", "(−) Net debt", "Equity"], y=steps,
            measure=["relative", "relative", "total", "relative", "total"],
            text=[f"{v:,.0f}" for v in steps], textposition="outside",
            connector={"line": {"color": GREY, "dash": "dot"}},
            increasing={"marker": {"color": GREEN}}, decreasing={"marker": {"color": RED}},
            totals={"marker": {"color": NAVY}},
        ))
        ev_fig.update_layout(showlegend=False, yaxis_title="M")
        style_fig(ev_fig, "From enterprise value to equity value", height=400)
        with g2, card():
            show_chart(ev_fig)

    st.divider()
    dcf_sens = cached_dcf_sensitivity(dcf_inputs)
    with st.expander("Sensitivity of intrinsic value per share (WACC × g)"):
        sens_fig = go.Figure(go.Heatmap(
            z=dcf_sens.values, x=[f"{v:.1%}" for v in dcf_sens.columns], y=[f"{v:.1%}" for v in dcf_sens.index],
            colorscale=BLUE_SCALE, texttemplate="%{z:,.2f}",
            hovertemplate="g: %{x}<br>WACC: %{y}<br>Value per share: %{z:,.2f}<extra></extra>",
            colorbar=dict(title="Per share"),
        ))
        sens_fig.update_layout(xaxis_title="Perpetual growth (g)", yaxis_title="WACC")
        style_fig(sens_fig, "Intrinsic value per share", height=420)
        show_chart(sens_fig)

    with st.expander("DCF methodology"):
        st.markdown(
            """
- **Revenue** grows at a constant rate; **EBITDA** = revenue × margin; **EBIT** = EBITDA − D&A.
- **FCF** = EBITDA − taxes on EBIT − Capex − NWC investment (% of the revenue increase).
- **Terminal value** (Gordon growth) = FCF₅ × (1 + g) / (WACC − g), discounted with the Year 5 factor.
- **Enterprise value** = Σ PV(FCF) + PV(TV); **equity value** = EV − Target net debt.
- **Target net income** = (EBIT − interest on its net debt) × (1 − t). It feeds the pro-forma EPS, so changing
  margins, growth or Capex moves both the price and the earnings acquired.
- End-of-year discounting; no mid-year convention and no normalisation of the terminal FCF.
            """
        )

    return dict(dcf=dcf, dcf_inputs=dcf_inputs, target=target, base_price=base_price, base_label=base_label,
                dcf_proj=dcf_proj, dcf_bridge=dcf_bridge, dcf_sens=dcf_sens)
