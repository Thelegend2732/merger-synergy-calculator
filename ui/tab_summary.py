"""Tab 3: transaction summary for the selected year — EPS impact, thresholds, EPS bridge, PPA, contribution."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engine import (
    GREEN, GREY, NAVY, RED, breakeven_synergies, fmt_value, make_table, max_premium_eps_neutral,
    ownership_contribution, safe_div,
)

from .components import card, card_title, gap, show_chart, show_table, style_fig, verdict_metric


def render(inp, base_price: float, base_label: str, deal: dict, model: dict) -> dict:
    P, yi, year_sel = inp.P, inp.yi, inp.year_sel
    base, cur_syn, cur_integ, cur_tni = model["base"], model["cur_syn"], model["cur_integ"], model["cur_tni"]
    acq_sh, tax_f = P["acq_sh"], 1 - P["tax"]
    be = breakeven_synergies(P, deal, yi)
    max_prem = max_premium_eps_neutral(P, base_price, yi)
    oc = ownership_contribution(P, deal)

    gap()
    with card():
        card_title(f"EPS impact: {year_sel}",
                   f"{inp.phases[yi]:.0%} of run-rate synergies ({cur_syn:,.1f} M), integration costs "
                   f"{cur_integ:,.1f} M and DCF-derived Target net income ({cur_tni:,.1f} M). "
                   f"Target base price: {base_label}.")
        c1, c2, c3 = st.columns(3)
        c1.metric("Standalone EPS (Acquirer)", fmt_value(base["sa_eps"], "eps"))
        c2.metric("Pro-forma EPS", fmt_value(base["pf_eps"], "eps"), delta=fmt_value(base["acc"], "eps_s"))
        verdict_metric(c3, "Accretion / (dilution)", base["acc_pct"], "pct_s", base["accretive"])

        if pd.isna(base["acc"]):
            st.warning("EPS cannot be computed: check that shares outstanding are greater than zero.")
        elif base["accretive"]:
            st.success(f"The deal is **ACCRETIVE**: EPS rises by {fmt_value(base['acc'], 'eps_s')} "
                       f"({fmt_value(base['acc_pct'], 'pct_s')}).")
        else:
            st.error(f"The deal is **DILUTIVE**: EPS falls by {fmt_value(base['acc'], 'eps_s')} "
                     f"({fmt_value(base['acc_pct'], 'pct_s')}).")

    gap()
    with card():
        card_title("Deal thresholds", f"{year_sel}: what it would take for the deal to be EPS-neutral.")
        b1, b2, b3, b4 = st.columns(4)
        b1.metric("Breakeven synergies (run-rate)", fmt_value(be["run_rate"], "m1"),
                  delta=(fmt_value(be["cushion"], "m1") + " cushion") if np.isfinite(be["cushion"]) else None,
                  help="Minimum pre-tax run-rate synergies for pro-forma EPS to equal standalone EPS, "
                       "given the selected year's phasing.")
        b2.metric("Max EPS-neutral premium", fmt_value(max_prem, "pct"),
                  delta=fmt_value(max_prem - inp.premium, "pct_s") + " vs. current" if np.isfinite(max_prem) else None,
                  help="Highest premium over the base price that keeps the deal non-dilutive.")
        b3.metric("Pro-forma ownership: Acquirer", fmt_value(oc["own_acq"], "pct"))
        b4.metric("Pro-forma ownership: Target", fmt_value(oc["own_tgt"], "pct"))
        if not np.isfinite(max_prem):
            st.caption("The deal is dilutive even at a zero premium: there is no EPS-neutral premium.")

    tgt_netdebt = P["tgt_netdebt"]
    implied_ev = deal["equity_value"] + tgt_netdebt
    summary = make_table("Metric", ["Value"], [
        ("Analysis year", year_sel, "txt"),
        ("Target base price per share", base_price, "m2"),
        ("Offer price per share", deal["offer_price"], "m2"),
        ("Implied premium to market price", safe_div(deal["offer_price"], P["tgt_px"]) - 1, "pct_s"),
        ("Deal equity value (M)", deal["equity_value"], "m1"),
        ("Implied enterprise value (M)", implied_ev, "m1"),
        ("Implied EV / LTM EBITDA", safe_div(implied_ev, P["tgt_ebitda"]), "x"),
        ("Cash consideration (M)", deal["cash_consid"], "m1"),
        ("Stock consideration (M)", deal["stock"], "m1"),
        ("Advisory fees (M)", deal["adv_fees"], "m1"),
        ("Financing fees (M)", deal["fin_fees"], "m1"),
        ("Total cash needed (M)", deal["cash"], "m1"),
        ("New shares issued (M)", deal["new_shares"], "m2"),
        ("Exchange ratio (Acquirer shares per Target share)", deal["exchange_ratio"], "eps"),
        ("Balance sheet cash used (M)", deal["cash_bs"], "m1"),
        ("Senior debt (M)", deal["senior"], "m1"),
        ("Mezzanine debt (M)", deal["mezz"], "m1"),
        ("Interest expense for the year (M)", deal["interest_y"][yi], "m1"),
        ("Opportunity cost of cash (M)", deal["opp_cost"], "m1"),
        ("Financing fee amortisation (M)", deal["fee_amort_y"][yi], "m1"),
        ("PPA intangible amortisation (M)", deal["ppa_amort"], "m1"),
        ("Synergies captured (%)", inp.phases[yi], "pct"),
        ("Pre-tax synergies captured (M)", cur_syn, "m1"),
        ("Integration costs (M)", cur_integ, "m1"),
        ("Target net income — DCF (M)", cur_tni, "m1"),
        ("Pro-forma net income (M)", base["pf_ni"], "m1"),
        ("Pro-forma shares outstanding (M)", base["pf_shares"], "m2"),
        ("Standalone EPS", base["sa_eps"], "eps"),
        ("Pro-forma EPS", base["pf_eps"], "eps"),
        ("Accretion / (dilution) per share", base["acc"], "eps_s"),
        ("Accretion / (dilution) %", base["acc_pct"], "pct_s"),
        ("Breakeven run-rate synergies (M)", be["run_rate"], "m1"),
        ("Max EPS-neutral premium", max_prem, "pct"),
    ])

    # EPS bridge: steps over the original share count; the last step captures dilution from new shares
    def per_share(v: float) -> float:
        return safe_div(v * tax_f, acq_sh, 0.0)

    wf_steps = [
        ("Target net income (DCF)", safe_div(cur_tni, acq_sh, 0.0)),
        ("Synergies (after tax)", per_share(cur_syn)),
        ("Integration costs (after tax)", -per_share(cur_integ)),
        ("Senior interest (after tax)", -per_share(deal["int_senior_y"][yi])),
        ("Mezzanine interest (after tax)", -per_share(deal["int_mezz_y"][yi])),
        ("Cash opportunity cost (after tax)", -per_share(deal["opp_cost"])),
        ("Financing fee amort. (after tax)", -per_share(deal["fee_amort_y"][yi])),
        ("PPA amortisation (after tax)", -per_share(deal["ppa_amort"])),
    ]
    eps_pre_dilution = base["sa_eps"] + sum(v for _, v in wf_steps)
    wf_steps.append(("Dilution from new shares", base["pf_eps"] - eps_pre_dilution))

    wf_labels = ["Standalone EPS", *[lb for lb, _ in wf_steps], "Pro-forma EPS"]
    wf_values = [base["sa_eps"], *[v for _, v in wf_steps], base["pf_eps"]]
    wf_measures = ["absolute"] + ["relative"] * len(wf_steps) + ["total"]
    waterfall = make_table("Step", ["EPS"], [(lb, v, "eps" if m != "relative" else "eps_s")
                                             for lb, v, m in zip(wf_labels, wf_values, wf_measures)])

    wf = go.Figure(go.Waterfall(
        x=wf_labels, y=wf_values, measure=wf_measures,
        text=[f"{v:+.3f}" if m == "relative" else f"{v:.3f}" for v, m in zip(wf_values, wf_measures)],
        textposition="outside", connector={"line": {"color": GREY, "dash": "dot"}},
        increasing={"marker": {"color": GREEN}}, decreasing={"marker": {"color": RED}},
        totals={"marker": {"color": NAVY}},
    ))
    wf.update_layout(yaxis_title="EPS", showlegend=False)
    style_fig(wf, f"EPS bridge ({year_sel}): standalone to pro forma", height=560)

    st.divider()
    left, right = st.columns([2, 3], gap="medium")
    with left, card():
        card_title("Transaction summary")
        show_table(summary)
    with right, card():
        show_chart(wf)

    # --- PPA and contribution ---
    ppa = make_table("Purchase price allocation (M)", ["Value"], [
        ("Equity purchase price", deal["equity_value"], "m1"),
        ("(−) Target book equity", -deal["book_equity"], "m1"),
        ("Excess purchase price", deal["excess"], "m1"),
        ("(−) Identifiable intangibles", -deal["intangibles"], "m1"),
        ("(+) Deferred tax liability", deal["dtl"], "m1"),
        ("Goodwill", deal["goodwill"], "m1"),
        ("Goodwill as % of price", safe_div(deal["goodwill"], deal["equity_value"]), "pct"),
        ("Annual intangible amortisation", deal["ppa_amort"], "m1"),
    ])
    contribution = make_table("Contribution vs. ownership", ["Acquirer", "Target"], [
        ("EBITDA", list(oc["ebitda"]), "pct"),
        ("Net income (Year 1)", list(oc["net_income"]), "pct"),
        ("Market capitalisation", list(oc["market_cap"]), "pct"),
        ("Pro-forma ownership", [oc["own_acq"], oc["own_tgt"]], "pct"),
    ])
    contrib_labels = ["EBITDA", "Net income (Year 1)", "Market cap", "Pro-forma ownership"]
    contrib_acq = [oc["ebitda"][0], oc["net_income"][0], oc["market_cap"][0], oc["own_acq"]]
    contrib_fig = go.Figure()
    contrib_fig.add_trace(go.Bar(y=contrib_labels, x=contrib_acq, name="Acquirer", orientation="h",
                                 marker_color=NAVY, text=[fmt_value(v, "pct") for v in contrib_acq],
                                 textposition="inside"))
    contrib_fig.add_trace(go.Bar(y=contrib_labels, x=[1 - v for v in contrib_acq], name="Target",
                                 orientation="h", marker_color=GREY,
                                 text=[fmt_value(1 - v, "pct") for v in contrib_acq], textposition="inside"))
    contrib_fig.update_layout(barmode="stack", xaxis_tickformat=".0%", xaxis_range=[0, 1],
                              yaxis_autorange="reversed",
                              legend=dict(orientation="h", y=1.15, x=1, xanchor="right", traceorder="normal"))
    style_fig(contrib_fig, "Contribution analysis vs. pro-forma ownership", height=360)

    st.divider()
    pl, pr = st.columns([2, 3], gap="medium")
    with pl, card():
        card_title("Purchase price allocation", "Goodwill = price − book equity − intangibles + DTL.")
        show_table(ppa)
    with pr, card():
        show_chart(contrib_fig)
        st.caption("If Target shareholders receive less ownership than they contribute, the deal transfers value "
                   "to the Acquirer's shareholders (and vice versa).")

    st.divider()
    with st.expander("Methodology and formulas"):
        st.markdown(
            """
- **Offer price** = Target base price (DCF or market) × (1 + premium)
- **Deal equity value** = offer price × Target shares
- **New shares** = stock consideration / Acquirer share price
- **Run-rate synergies** = cost synergies + revenue synergies × EBITDA margin
- **Financing cost** = Senior interest (amortising balance) + Mezzanine interest + balance sheet cash × opportunity
  cost + financing fee amortisation
- **PPA**: excess = price − book equity; intangibles = % of excess (amortised); DTL = intangibles × t;
  goodwill = excess − intangibles + DTL (not amortised)
- **Target net income** = (EBIT − interest on its net debt) × (1 − t), from the DCF for each year
- **Pro-forma NI** = Acquirer NI + Target NI (DCF) + (synergies captured − integration costs − financing cost
  − intangible amortisation) × (1 − t)
- **Pro-forma EPS** = pro-forma NI / (Acquirer shares + new shares)
- **Accretion / (dilution)** = pro-forma EPS − standalone EPS
- **Breakeven synergies**: synergies at which pro-forma EPS equals standalone EPS (closed form, since NI is linear
  in synergies). **Max EPS-neutral premium**: bisection on the premium.
- Advisory fees are a one-off closing cost and are excluded from recurring EPS.
            """
        )

    return dict(summary=summary, waterfall=waterfall, ppa=ppa, contribution=contribution)
