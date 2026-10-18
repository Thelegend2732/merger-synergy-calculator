"""Tab 6: multi-variable Monte Carlo risk analysis and EPS tornado for the selected year."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engine import GREEN, N_SIM, NAVY, RED, STAT_LABELS, eps_tornado, fmt_value, make_table

from .components import ST_DF, cached_montecarlo, card, card_title, gap, show_chart, style_fig


def render(inp, deal: dict, model: dict) -> dict:
    P, year_sel, cur_syn, base = inp.P, inp.year_sel, model["cur_syn"], model["base"]
    gap()
    dash = card()   # dashboard: filled after the simulation, but shown at the top
    gap()

    col_p, col_h = st.columns([1, 2], gap="medium")
    with col_p, card():
        card_title("Simulation parameters",
                   f"{N_SIM:,} draws for {year_sel}. Each driver is normally distributed around the base case "
                   f"(synergies centred on {cur_syn:,.1f} M); set a volatility to 0 to switch a driver off.")
        vol = st.slider("Synergy volatility (std. deviation, %)", 0, 100, step=1, key="mc_vol") / 100
        tni_vol = st.slider("Target net income volatility (%)", 0, 50, step=1, key="mc_tni_vol",
                            help="Execution risk on the acquired business's earnings.") / 100
        corr = st.slider("Correlation synergies ↔ Target earnings", -1.0, 1.0, step=0.1, key="mc_corr",
                         help="Positive: a smooth integration lifts both synergies and the Target's earnings.")
        rate_vol = st.slider("Interest rate shock on Senior debt (std. dev., bp)", 0, 300, step=5,
                             key="mc_rate_bp", help="Treats the Senior tranche as floating-rate.") / 10_000
        integ_vol = st.slider("Integration cost overrun (std. deviation, %)", 0, 100, step=5, key="mc_integ_vol",
                              help="Only bites where integration costs hit EPS (Year 1, GAAP basis).") / 100
        seed = st.number_input("Random seed (reproducibility)", min_value=0, max_value=2**31 - 1,
                               step=1, key="mc_seed")
        if cur_syn * vol == 0:
            st.info("Zero standard deviation (volatility or expected synergies = 0): the simulation is deterministic.")

    mc = cached_montecarlo(P, deal, inp.yi, vol, int(seed), tni_vol, rate_vol, integ_vol, corr)   # cached
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
    # Tornado: which driver moves EPS the most (±1 std. dev., one at a time)
    tornado = eps_tornado(P, deal, inp.yi, vol, tni_vol, rate_vol, integ_vol)
    base_eps = tornado.attrs["base_eps"]
    torn = go.Figure()
    torn.add_trace(go.Bar(y=tornado["Driver"], x=tornado["EPS low"] - base_eps, base=base_eps, orientation="h",
                          name="−1 std. dev.", marker_color=RED))
    torn.add_trace(go.Bar(y=tornado["Driver"], x=tornado["EPS high"] - base_eps, base=base_eps, orientation="h",
                          name="+1 std. dev.", marker_color=GREEN))
    torn.add_vline(x=base_eps, line_color=NAVY, line_width=2)
    torn.add_vline(x=sa_eps, line_dash="dash", line_color=NAVY,
                   annotation_text=f"Standalone {sa_eps:.3f}", annotation_position="top")
    lo = min(tornado["EPS low"].min(), sa_eps, base_eps)
    hi = max(tornado["EPS high"].max(), sa_eps, base_eps)
    pad = max((hi - lo) * 0.08, abs(base_eps) * 0.01, 1e-3)
    torn.update_layout(barmode="overlay", xaxis_title="Pro-forma EPS", yaxis_autorange="reversed",
                       xaxis_range=[lo - pad, hi + pad],
                       legend=dict(orientation="h", y=1.15, x=1, xanchor="right"))
    style_fig(torn, "EPS tornado: impact of each driver (±1 std. dev.)", height=340)
    gap()
    with card():
        show_chart(torn)
        st.caption("Bars show pro-forma EPS when one driver moves one standard deviation and the rest stay at "
                   "the base case; the solid line is the deterministic EPS.")

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
        ("Synergy volatility (std. deviation)", vol, "pct"),
        ("Target net income volatility", tni_vol, "pct"),
        ("Correlation synergies / Target earnings", f"{corr:+.1f}", "txt"),
        ("Interest rate shock (std. deviation)", rate_vol, "pct"),
        ("Integration cost overrun (std. deviation)", integ_vol, "pct"),
        ("Random seed", str(int(seed)), "txt"),
        ("Iterations", f"{N_SIM:,}", "txt"),
        ("Standalone EPS", sa_eps, "eps"),
        ("Deterministic pro-forma EPS (Summary)", base["pf_eps"], "eps"),
        ("Probability the transaction is accretive", prob_acc / 100, "pct"),
    ])
    mc_hist = pd.DataFrame({"Pro-forma EPS (bin mid)": mc["mids"], "Frequency": mc["counts"],
                            "Zone": np.where(mc["mids"] >= sa_eps, "Accretive", "Dilutive")})
    mc_sim = pd.DataFrame({"Simulated synergies (M)": mc["syn_draws"], "Target net income (M)": mc["tni_draws"],
                           "Rate shock": mc["rate_draws"], "Integration costs (M)": mc["integ_draws"],
                           "Pro-forma EPS": mc["eps"]})

    mc_tornado = tornado.drop(columns="Swing")
    return dict(vol=vol, seed=int(seed), drivers=(tni_vol, rate_vol, integ_vol, corr), mc_params=mc_params, mc_stats=mc_stats, mc_hist=mc_hist, mc_sim=mc_sim,
                mc_tornado=mc_tornado)
