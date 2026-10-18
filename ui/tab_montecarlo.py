"""Tab 5: Monte Carlo risk analysis on the synergies captured in the selected year."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engine import GREEN, N_SIM, NAVY, RED, STAT_LABELS, fmt_value, make_table

from .components import ST_DF, cached_montecarlo, card, card_title, gap, show_chart, style_fig


def render(inp, deal: dict, model: dict) -> dict:
    P, year_sel, cur_syn, base = inp.P, inp.year_sel, model["cur_syn"], model["base"]
    gap()
    dash = card()   # dashboard: filled after the simulation, but shown at the top
    gap()

    col_p, col_h = st.columns([1, 2], gap="medium")
    with col_p, card():
        card_title("Simulation parameters",
                   f"{N_SIM:,} draws for {year_sel}. Synergies follow a normal distribution centred on "
                   f"{cur_syn:,.1f} M; all other variables are held constant.")
        vol = st.slider("Expected synergy volatility (std. deviation, %)", 0, 100, 20, 1, key="mc_vol") / 100
        seed = st.number_input("Random seed (reproducibility)", value=42, min_value=0, max_value=2**31 - 1,
                               step=1, key="mc_seed")
        if cur_syn * vol == 0:
            st.info("Zero standard deviation (volatility or expected synergies = 0): the simulation is deterministic.")

    mc = cached_montecarlo(P, deal, inp.yi, vol, int(seed))   # 5,000 cached draws
    sa_eps, prob_acc = mc["sa_eps"], mc["prob_acc"]

    with dash:
        card_title(f"Deal risk: {year_sel}")
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Probability accretive", f"{prob_acc:.1f}%",
                  help="Share of simulations in which the transaction is accretive.")
        k2.metric("Mean pro-forma EPS", fmt_value(mc["eps_mean"], "eps"),
                  delta=fmt_value(mc["eps_mean"] - sa_eps, "eps_s"))
        k3.metric("Deterministic EPS (Summary)", fmt_value(base["pf_eps"], "eps"))
        k4.metric("Standalone EPS", fmt_value(sa_eps, "eps"))
        k5.metric("Downside (P5) EPS", fmt_value(mc["eps_p5"], "eps"))
        if prob_acc >= 50:
            st.success(f"The deal is accretive in {prob_acc:.1f}% of the {N_SIM:,} simulations.")
        else:
            st.error(f"The deal is accretive in only {prob_acc:.1f}% of the {N_SIM:,} simulations.")

    # Histogram with shared edges for both zones (accretive in green, dilutive in red)
    hist = go.Figure()
    hist.add_trace(go.Bar(x=mc["mids"], y=mc["cnt_acc"], width=mc["widths"], name="Accretive",
                          marker_color=GREEN, opacity=0.9))
    hist.add_trace(go.Bar(x=mc["mids"], y=mc["cnt_dil"], width=mc["widths"], name="Dilutive",
                          marker_color=RED, opacity=0.9))
    hist.add_vline(x=sa_eps, line_dash="dash", line_color=NAVY, line_width=2,
                   annotation_text=f"Standalone EPS {sa_eps:.3f}", annotation_position="top")
    hist.update_layout(barmode="stack", bargap=0.02, xaxis_title="Pro-forma EPS", yaxis_title="Frequency",
                       legend=dict(orientation="h", y=1.1, x=1, xanchor="right"))
    style_fig(hist, f"Pro-forma EPS distribution ({N_SIM:,} simulations)", height=460)
    with col_h, card():
        show_chart(hist)

    # Numeric version (Excel) and formatted version (UI)
    mc_stats = pd.DataFrame({"Statistic": STAT_LABELS, "Pro-forma EPS": mc["eps_stats"],
                             "Accretion / (dilution) %": mc["acc_stats"]})
    with col_p, card():
        card_title("Simulation statistics")
        st.dataframe(
            pd.DataFrame({"Statistic": STAT_LABELS,
                          "Pro-forma EPS": [fmt_value(e, "eps") for e in mc["eps_stats"]],
                          "Acc./(dil.)": [fmt_value(a_, "pct_s") for a_ in mc["acc_stats"]]}),
            hide_index=True, **ST_DF)

    mc_params = make_table("Parameter", ["Value"], [
        ("Simulated year", year_sel, "txt"),
        ("Expected synergies (M)", cur_syn, "m1"),
        ("Volatility (std. deviation)", vol, "pct"),
        ("Random seed", str(int(seed)), "txt"),
        ("Iterations", f"{N_SIM:,}", "txt"),
        ("Standalone EPS", sa_eps, "eps"),
        ("Deterministic pro-forma EPS (Summary)", base["pf_eps"], "eps"),
        ("Probability the transaction is accretive", prob_acc / 100, "pct"),
    ])
    mc_hist = pd.DataFrame({"Pro-forma EPS (bin mid)": mc["mids"], "Frequency": mc["counts"],
                            "Zone": np.where(mc["mids"] >= sa_eps, "Accretive", "Dilutive")})
    mc_sim = pd.DataFrame({"Simulated synergies (M)": mc["syn_draws"], "Pro-forma EPS": mc["eps"]})

    return dict(vol=vol, seed=int(seed), mc_params=mc_params, mc_stats=mc_stats, mc_hist=mc_hist, mc_sim=mc_sim)
