"""Global alerts shown above the tabs, so critical issues are visible from anywhere in the app."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from engine import LEVERAGE_LIMIT, leverage_metrics, safe_div


def render(inp, out: dict, model_err: str) -> None:
    if model_err:
        st.error(f"The model could not be computed ({model_err}). Check the DCF and Capital Structure tabs.")
        return
    P, dcf_out, deal = inp.P, out["dcf"], out["cap"]["deal"]
    if inp.use_dcf_basis and not dcf_out["dcf"]["valid"]:
        st.warning("**Invalid DCF**: the Target base price is the market price, not intrinsic value. "
                   f"Reason: {dcf_out['dcf']['reason']}")
    implied_premium = safe_div(deal["offer_price"], P["tgt_px"]) - 1
    if implied_premium < 0:
        st.warning(f"**Offer below market price**: {deal['offer_price']:,.2f} per share vs. {P['tgt_px']:,.2f} "
                   f"(implied premium {implied_premium:+.1%}). Target shareholders are unlikely to accept; "
                   "review the premium or the price basis.")
    if deal["cash_bs"] > P["acq_cash"] + 1e-9:
        st.error(f"**Insufficient cash**: the deal uses {deal['cash_bs']:,.1f} M of balance sheet cash and the "
                 f"Acquirer has {P['acq_cash']:,.1f} M available.")
    if deal["bargain"]:
        st.warning(f"**Negative goodwill** ({deal['goodwill']:,.1f} M): the price is below the Target's book "
                   "equity (bargain purchase). Review book equity or the price.")
    lev = leverage_metrics(P, deal, 0.0)["lev_pf"]   # conservative view, independent of the tab-2 checkbox
    if not pd.isna(lev) and lev > LEVERAGE_LIMIT:
        st.error(f"**Pro-forma leverage {lev:.2f}x** > {LEVERAGE_LIMIT:.1f}x: risk of a credit rating downgrade.")
