"""Tab 4: three-year accretion/dilution projection and the premium × synergies sensitivity grid."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engine import GREEN, NAVY, RED, YEARS, fmt_value, make_table

from .components import (
    HEAT_COLORSCALE, cached_sensitivity_matrix, card, card_title, gap, show_chart, show_table, style_fig,
)


def render(inp, base_price: float, deal: dict, model: dict) -> dict:
    P, proj, base = inp.P, model["proj"], model["base"]
    gap()
    with card():
        card_title(f"{inp.eps_basis} accretion / (dilution) by year",
                   "Sidebar phasing: " + " · ".join(f"{y} {p_:.0%}" for y, p_ in zip(YEARS, inp.phases))
                   + ". Integration costs fall in Year 1.")
        for col, yr, p_ in zip(st.columns(len(YEARS)), YEARS, proj):
            sc = p_[3]
            col.metric(f"{yr}: pro-forma EPS", fmt_value(sc["pf_eps"], "eps"),
                       delta=fmt_value(sc["acc_pct"], "pct_s"))

    projection = make_table("Line item", YEARS, [
        ("Synergies captured (%)", inp.phases, "pct"),
        ("Pre-tax synergies captured (M)", [p_[0] for p_ in proj], "m1"),
        ("Integration costs (M)", [p_[1] for p_ in proj], "m1"),
        ("Target net income — DCF (M)", [p_[2] for p_ in proj], "m1"),
        ("Pre-tax financing charge (M)", deal["fin_cost_y"] + deal["fee_amort_y"], "m1"),
        ("PPA amortisation in EPS (M)", [0.0 if inp.adjusted else deal["ppa_amort"]] * len(YEARS), "m1"),
        ("Pro-forma net income (M)", [p_[3]["pf_ni"] for p_ in proj], "m1"),
        ("Pro-forma shares (M)", [p_[3]["pf_shares"] for p_ in proj], "m2"),
        ("Standalone EPS", [p_[3]["sa_eps"] for p_ in proj], "eps"),
        ("Pro-forma EPS", [p_[3]["pf_eps"] for p_ in proj], "eps"),
        ("Accretion / (dilution) per share", [p_[3]["acc"] for p_ in proj], "eps_s"),
        ("Accretion / (dilution) %", [p_[3]["acc_pct"] for p_ in proj], "pct_s"),
        ("Result", ["Accretive" if p_[3]["accretive"] else "Dilutive" for p_ in proj], "txt"),
    ])

    gap()
    col_t, col_c = st.columns([3, 2], gap="medium")
    with col_t, card():
        card_title("Three-year projection")
        show_table(projection)
    with col_c, card():
        acc_pcts = [p_[3]["acc_pct"] for p_ in proj]
        bar = go.Figure(go.Bar(
            x=YEARS, y=[0 if pd.isna(v) else v for v in acc_pcts],
            marker_color=[GREEN if (not pd.isna(v) and v >= 0) else RED for v in acc_pcts],
            text=[fmt_value(v, "pct_s") for v in acc_pcts], textposition="outside",
        ))
        bar.update_layout(yaxis_title="Accretion / (dilution)", yaxis_tickformat=".1%", showlegend=False)
        style_fig(bar, "Accretion / (dilution) by year", height=400)
        show_chart(bar)

    st.divider()
    st.subheader(f"Sensitivity grid: {inp.year_sel}")

    hm = cached_sensitivity_matrix(P, base_price, inp.premium, inp.yi)   # 63 cached scenarios
    z, syn_axis, prem_axis, fallback = hm["z"], hm["syn_axis"], hm["prem_axis"], hm["fallback"]
    n_x, n_y = hm["n_x"], hm["n_y"]
    heat_df = pd.DataFrame(z, index=prem_axis, columns=syn_axis)

    z_limit = max(float(np.nanmax(np.abs(z))) if np.isfinite(z).any() else 1e-9, 1e-9)  # symmetric scale
    heat = go.Figure(go.Heatmap(
        z=z, x=[f"{v:,.0f}" for v in syn_axis], y=[f"{v:.1%}" for v in prem_axis],
        colorscale=HEAT_COLORSCALE, zmin=-z_limit, zmax=z_limit, zmid=0, texttemplate="%{z:+.1%}",
        hovertemplate="Synergies: %{x} M<br>Premium: %{y}<br>Accretion/(dilution): %{z:+.2%}<extra></extra>",
        colorbar=dict(title="Acc./(dil.)", tickformat=".0%"),
    ))
    if not fallback:  # outline the base case (centre cell)
        heat.add_shape(type="rect", xref="x", yref="y",
                       x0=n_x // 2 - 0.5, x1=n_x // 2 + 0.5, y0=n_y // 2 - 0.5, y1=n_y // 2 + 0.5,
                       line=dict(color=NAVY, width=3))
    heat.update_layout(xaxis_title="Pre-tax run-rate synergies (M)", yaxis_title="Premium over base price")
    style_fig(heat, f"EPS accretion / (dilution), {inp.year_sel}", height=520)

    col_h, col_n = st.columns([3, 1], gap="medium")
    with col_h, card():
        show_chart(heat)
    with col_n, card():
        card_title("How to read the grid")
        st.caption("X axis: run-rate synergies at EBITDA level (±50% of the base case).")
        st.caption("Y axis: premium over the base price (±20% of the input).")
        st.caption("Green = accretive; red = dilutive. The outlined cell is the base case and matches the Summary.")
        if fallback:
            st.info("Synergies or premium are zero, so the grid uses absolute ranges "
                    "(synergies 0–100 M; premium 0–20%).")
        st.divider()
        st.metric("Base case", fmt_value(base["acc_pct"], "pct_s"))
        st.caption(f"Premium {inp.premium:.0%} · Synergies {inp.total_syn:,.0f} M")

    return dict(projection=projection, heat=heat_df)
