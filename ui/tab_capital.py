"""Tab 2: funding of the cash component, sources & uses, debt schedule and leverage risk."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engine import (
    AMBER, GREEN, GREY, LEVERAGE_LIMIT, LEVERAGE_WARN, RED, YEARS, build_deal, fmt_value, leverage_metrics,
    make_table, safe_div,
)

from .components import ST_DF, card, card_title, gap, show_chart, show_table, style_fig
from .theme import hero, icon, metric, section


def render(inp, base_price: float) -> dict:
    P = inp.P
    gap()
    dash = card()   # dashboard: filled once the deal is built
    gap()

    col_in, col_side = st.columns([2, 1], gap="medium")
    with col_in, card():
        card_title("Funding the cash component",
                   "Cash is funded with balance sheet cash and two debt tranches; the stock component with new "
                   "Acquirer shares.", "settings")
        a, b = st.columns(2)
        with a:
            cash_share = st.slider("Balance sheet cash (% of cash needed)", 0, 100, step=5, key="cap_cash")
            senior_share = st.slider("Senior debt (%)", 0, 100, step=5, key="cap_sr")
        with b:
            rate_cash = st.number_input("Opportunity cost of cash (%)", min_value=0.0,
                                        max_value=20.0, step=0.25, key="rate_cash",
                                        help="Pre-tax interest income forgone by using balance sheet cash.") / 100
            senior_rate = st.number_input("Senior interest rate (%)", min_value=0.0, max_value=30.0,
                                          step=0.25, key="rate_sr") / 100
            mezz_rate = st.number_input("Mezzanine interest rate (%)", min_value=0.0, max_value=40.0,
                                        step=0.25, key="rate_mz") / 100
        f1, f2, f3 = st.columns(3)
        senior_term = f1.number_input("Senior amortisation term (years)", min_value=0, max_value=30,
                                      step=1, key="sr_term",
                                      help="Straight-line amortisation; 0 = bullet. Mezzanine is always bullet.")
        fee_adv = f2.number_input("Advisory fees (% of equity value)", min_value=0.0,
                                  max_value=10.0, step=0.25, key="fee_adv",
                                  help="M&A advisory, legal and due diligence: one-off, excluded from recurring EPS.") / 100
        fee_fin = f3.number_input("Financing fees (% of new debt)", min_value=0.0,
                                  max_value=10.0, step=0.25, key="fee_fin",
                                  help="Capitalised and amortised over the Senior term.") / 100

    # Cash + Senior cannot exceed 100%; the remainder is Mezzanine
    raw_total = cash_share + senior_share
    scale = 100 / raw_total if raw_total > 100 else 1.0
    cap_cash, cap_senior = cash_share * scale / 100, senior_share * scale / 100
    cap_mezz = max(0.0, 1.0 - cap_cash - cap_senior)

    params = dict(cap_cash=cap_cash, cap_senior=cap_senior, cap_mezz=cap_mezz, rate_senior=senior_rate,
                  rate_mezz=mezz_rate, rate_cash=rate_cash, senior_term=int(senior_term), fee_adv=fee_adv,
                  fee_fin=fee_fin)
    P.update(params)
    deal = build_deal(P, base_price, inp.premium)
    acq_cash = P["acq_cash"]

    with col_side, card():
        card_title("Resulting split", "Of the cash needed, including fees.", "equity")
        st.progress(cap_cash, text=f"Balance sheet cash · {cap_cash:.0%}")
        st.progress(cap_senior, text=f"Senior debt · {cap_senior:.0%}")
        st.progress(cap_mezz, text=f"Mezzanine (remainder) · {cap_mezz:.0%}")
        if raw_total > 100:
            st.error(f"Cash ({cash_share}%) + Senior ({senior_share}%) add up to {raw_total}%. "
                     "They are rescaled proportionally to 100% (Mezzanine = 0%).", icon=icon("error"))
        if mezz_rate < senior_rate:
            st.warning("The Mezzanine rate is below the Senior rate: subordinated debt normally pays more.",
                       icon=icon("warn"))
        cash_use = safe_div(deal["cash_bs"], acq_cash, 0.0)
        if deal["cash_bs"] > acq_cash + 1e-9:
            st.error(f"Balance sheet cash required ({deal['cash_bs']:,.1f} M) exceeds the Acquirer's available "
                     f"cash ({acq_cash:,.1f} M).", icon=icon("error"))
        else:
            st.metric("Balance sheet cash used", f"{deal['cash_bs']:,.1f} M", border=True, icon=icon("cash"),
                      delta=f"{cash_use:.0%} of {acq_cash:,.1f} M available", delta_arrow="off")

    with dash:
        card_title("Deal funding", "How the cash component is paid for and what it costs each year.", "capital")
        k1, k2, k3, k4, k5 = st.columns(5)
        metric(k1, "Cash needed (incl. fees)", fmt_value(deal["cash"], "m1"), "cash")
        metric(k2, "New debt (Senior + Mezz)", fmt_value(deal["debt"], "m1"), "debt")
        metric(k3, "Average cost of debt", fmt_value(deal["avg_cost_debt"], "pct"), "rate")
        metric(k4, "Annual interest (Year 1)", fmt_value(deal["interest"], "m1"), "interest")
        metric(k5, "Opportunity cost of cash", fmt_value(deal["opp_cost"], "m1"), "savings",
               help="Annual opportunity cost of the balance sheet cash used (M, pre-tax).")

    cash_total = deal["cash"]
    tranches = pd.DataFrame({
        "Source": ["Balance sheet cash", "Senior debt", "Mezzanine debt", "Total"],
        "Amount (M)": [deal["cash_bs"], deal["senior"], deal["mezz"], cash_total],
        "% of cash": [cap_cash, cap_senior, cap_mezz, cap_cash + cap_senior + cap_mezz],
        "Rate / cost": [rate_cash, senior_rate, mezz_rate, safe_div(deal["fin_cost"], cash_total)],
        "Annual cost (M)": [deal["opp_cost"], deal["int_senior"], deal["int_mezz"], deal["fin_cost"]],
    })
    eq = deal["equity_value"]
    total_uses = eq + deal["adv_fees"] + deal["fin_fees"]
    su_rows = [
        ("Source", "Balance sheet cash", deal["cash_bs"]),
        ("Source", "Senior debt", deal["senior"]),
        ("Source", "Mezzanine debt", deal["mezz"]),
        ("Source", "New shares issued", deal["stock"]),
        ("Source", "Total sources", deal["cash"] + deal["stock"]),
        ("Use", "Purchase of Target equity", eq),
        ("Use", "Advisory fees", deal["adv_fees"]),
        ("Use", "Financing fees", deal["fin_fees"]),
        ("Use", "Total uses", total_uses),
    ]
    sources_uses = pd.DataFrame({
        "Type": [r[0] for r in su_rows],
        "Item": [r[1] for r in su_rows],
        "Amount (M)": [r[2] for r in su_rows],
        "% of total": [safe_div(r[2], total_uses) for r in su_rows],
    })
    n = len(YEARS)
    debt_schedule = make_table("Debt schedule (M)", YEARS, [
        ("Senior opening balance", deal["senior_beg"], "m1"),
        ("Senior repayment", -deal["senior_repay"], "m1"),
        ("Mezzanine balance (bullet)", np.full(n, deal["mezz"]), "m1"),
        ("Senior interest", deal["int_senior_y"], "m1"),
        ("Mezzanine interest", deal["int_mezz_y"], "m1"),
        ("Opportunity cost of cash", np.full(n, deal["opp_cost"]), "m1"),
        ("Financing fee amortisation", deal["fee_amort_y"], "m1"),
        ("Total pre-tax financing charge", deal["fin_cost_y"] + deal["fee_amort_y"], "m1"),
    ])

    gap()
    t1, t2 = st.columns([1, 1], gap="medium")
    with t1, card():
        card_title("Funding tranches", icon_key="table")
        st.dataframe(
            tranches.style.format({"Amount (M)": "{:,.1f}", "% of cash": "{:.1%}", "Rate / cost": "{:.2%}",
                                   "Annual cost (M)": "{:,.1f}"}, na_rep="–"),
            hide_index=True, **ST_DF)
    with t2, card():
        card_title("Sources & uses", icon_key="balance")
        st.dataframe(
            sources_uses.drop(columns="Type").rename(columns={"% of total": "%"})
            .style.format({"Amount (M)": "{:,.1f}", "%": "{:.0%}"}, na_rep="–"),
            hide_index=True, **ST_DF)
    gap()
    with card():
        card_title("Debt schedule and financing charge",
                   f"Senior amortises over {int(senior_term)} years (interest on opening balance)."
                   if senior_term else "Senior is bullet (no amortisation); financing fees expensed in Year 1.",
                   "calendar_month")
        show_table(debt_schedule)

    st.divider()
    section("leverage", "Leverage risk", "Net debt / EBITDA at closing versus the rating-agency comfort zones.")
    incl_syn = st.checkbox("Include run-rate synergies in pro-forma EBITDA", key="incl_syn",
                           help="Excluded by default (the conservative approach rating agencies take).")
    lev = leverage_metrics(P, deal, inp.total_syn if incl_syn else 0.0)
    lp = lev["lev_pf"]

    with card():
        m1, m2, m3, m4 = st.columns(4)
        metric(m1, "Net debt / EBITDA standalone", fmt_value(lev["lev_sa"], "x"), "leverage")
        delta_lev = lev["lev_pf"] - lev["lev_sa"]
        metric(m2, "Net debt / EBITDA pro forma", fmt_value(lev["lev_pf"], "x"), "leverage",
               delta=fmt_value(delta_lev, "x") if not pd.isna(delta_lev) else None, delta_color="inverse")
        metric(m3, "Pro-forma EBITDA (M)", fmt_value(lev["ebitda_pf"], "m1"), "income")
        metric(m4, "EBITDA / new interest cover", fmt_value(lev["coverage"], "x"), "verified")

        if pd.isna(lp):
            st.warning("Leverage cannot be computed: pro-forma EBITDA is not positive.", icon=icon("warn"))
        elif lp > LEVERAGE_LIMIT:
            hero("bad", "Leverage at closing", f"{lp:.2f}x net debt / EBITDA",
                 f"Above {LEVERAGE_LIMIT:.1f}x: high risk of a credit rating downgrade and leverage stress "
                 "(covenants, refinancing cost). Consider more stock consideration or a lower premium.", "leverage")
        elif lp > LEVERAGE_WARN:
            st.warning(f"Pro-forma net debt / EBITDA of **{lp:.2f}x**: watch zone "
                       f"({LEVERAGE_WARN:.1f}x–{LEVERAGE_LIMIT:.1f}x). No immediate stress, but little headroom.",
                       icon=icon("warn"))
        else:
            hero("ok", "Leverage at closing", f"{lp:.2f}x net debt / EBITDA",
                 f"Comfortable leverage, below the {LEVERAGE_WARN:.1f}x watch zone.", "ok")

    lev_fig = go.Figure()
    bar_color = GREY if pd.isna(lp) else (RED if lp > LEVERAGE_LIMIT else AMBER if lp > LEVERAGE_WARN else GREEN)
    lev_vals = [0 if pd.isna(v) else v for v in (lev["lev_sa"], lev["lev_pf"])]
    lev_fig.add_trace(go.Bar(x=["Standalone", "Pro forma"], y=lev_vals, marker_color=[GREY, bar_color],
                             text=[fmt_value(v, "x") for v in (lev["lev_sa"], lev["lev_pf"])], textposition="outside"))
    lev_fig.add_hline(y=LEVERAGE_LIMIT, line_dash="dash", line_color=RED,
                      annotation_text=f"Limit {LEVERAGE_LIMIT:.1f}x", annotation_position="top left")
    lev_fig.update_layout(showlegend=False, yaxis_title="Net debt / EBITDA (x)",
                          yaxis_range=[0, max(LEVERAGE_LIMIT * 1.25, max(lev_vals) * 1.2)])
    style_fig(lev_fig, "Leverage: standalone vs. pro forma", height=420)

    credit = make_table("Credit metrics", ["Value"], [
        ("Acquirer net debt (pre-deal, M)", P["acq_netdebt"], "m1"),
        ("Target net debt (M)", P["tgt_netdebt"], "m1"),
        ("(+) Cash deployed (cash + new debt, M)", deal["cash"], "m1"),
        ("Pro-forma net debt (M)", lev["net_debt_pf"], "m1"),
        ("Acquirer EBITDA (M)", P["acq_ebitda"], "m1"),
        ("Target LTM EBITDA (M)", P["tgt_ebitda"], "m1"),
        ("Synergies included in EBITDA (M)", inp.total_syn if incl_syn else 0.0, "m1"),
        ("Pro-forma EBITDA (M)", lev["ebitda_pf"], "m1"),
        ("Net debt / EBITDA standalone", lev["lev_sa"], "x"),
        ("Net debt / EBITDA pro forma", lev["lev_pf"], "x"),
        ("Leverage limit", LEVERAGE_LIMIT, "x"),
        ("EBITDA / new interest cover", lev["coverage"], "x"),
    ])
    gap()
    cl, cr = st.columns([2, 3], gap="medium")
    with cl, card():
        card_title("Credit metrics", icon_key="table")
        show_table(credit)
    with cr, card():
        show_chart(lev_fig)

    st.divider()
    with st.expander("Capital structure notes", icon=icon("method")):
        st.markdown(
            """
- Cash paid out (balance sheet cash + new debt) **increases net debt** by the same amount, so the split between
  cash, Senior and Mezzanine changes the **financing cost** (and EPS) but not net debt / EBITDA.
- **Average cost of debt** = (Senior × Senior rate + Mezzanine × Mezzanine rate) / total debt.
- **Opportunity cost of cash** = balance sheet cash used × yield forgone; it is deducted from pro-forma earnings
  after tax, like interest, so cash is not "free".
- Balance sheet cash used cannot exceed the Acquirer's available cash (red alert otherwise).
- **Fees**: advisory fees are paid at closing and excluded from recurring EPS; financing fees (% of new debt)
  are capitalised and amortised over the Senior term.
- **Senior debt** amortises straight-line (interest on each year's opening balance); **Mezzanine** is bullet.
  Repayment is funded from the combined company's cash flow, so net debt / EBITDA is shown at closing.
            """
        )

    return dict(params=params, deal=deal, incl_syn=incl_syn, tranches=tranches, sources_uses=sources_uses,
                debt_schedule=debt_schedule, credit=credit)
