"""Five-year unlevered DCF of the Target, plus its WACC × g sensitivity grid."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .constants import DCF_YEARS
from .utils import safe_div


def dcf_valuation(d: dict, wacc: float | None = None, g: float | None = None) -> dict:
    """
    5-year DCF of the Target. `d` holds: rev0, growth, margin, da_pct, capex_pct, nwc_pct, wacc, g,
    net_debt, td_rate, shares, tax. `wacc` / `g` override the inputs for sensitivity sweeps.

    FCF = EBITDA − taxes on EBIT − Capex − investment in NWC.
    It also derives the Target's net income (EBIT − interest on its net debt, after tax), which feeds
    the pro-forma EPS: valuation and accretion/dilution share a single operating model.
    """
    wacc = d["wacc"] if wacc is None else wacc
    g = d["g"] if g is None else g
    t = np.arange(1, DCF_YEARS + 1)

    with np.errstate(all="ignore"):
        rev = d["rev0"] * (1 + d["growth"]) ** t
        rev_prev = np.concatenate(([d["rev0"]], rev[:-1]))
        growth_row = np.divide(rev, rev_prev, out=np.full(rev.shape, np.nan), where=rev_prev != 0) - 1
        ebitda = rev * d["margin"]
        da = rev * d["da_pct"]
        ebit = ebitda - da
        taxes = np.maximum(ebit, 0.0) * d["tax"]
        capex = rev * d["capex_pct"]
        d_nwc = (rev - rev_prev) * d["nwc_pct"]
        fcf = ebitda - taxes - capex - d_nwc

        # Target net income (levered): EBIT − interest on its net debt, after tax
        interest_td = d["net_debt"] * d["td_rate"]
        pretax = ebit - interest_td
        ni = pretax - np.maximum(pretax, 0.0) * d["tax"]

        disc = (1 + wacc) ** -t
        pv_fcf = fcf * disc

        reason = ""
        if wacc <= g:
            reason = "WACC must exceed the perpetual growth rate (g); the terminal value is undefined."
        tv = pv_tv = ev = equity = price = np.nan
        if not reason:
            tv = fcf[-1] * (1 + g) / (wacc - g)
            pv_tv = tv * disc[-1]
            ev = float(pv_fcf.sum() + pv_tv)
            equity = ev - d["net_debt"]
            price = safe_div(equity, d["shares"])
            if not np.isfinite(equity) or equity <= 0:
                reason = "The resulting equity value is zero, negative or non-finite: check margins, WACC or net debt."
    return dict(
        valid=not reason, reason=reason, years=t, rev=rev, rev_prev=rev_prev, growth_row=growth_row,
        ebitda=ebitda, da=da, ebit=ebit, taxes=taxes, capex=capex, d_nwc=d_nwc, fcf=fcf, disc=disc,
        pv_fcf=pv_fcf, sum_pv=float(pv_fcf.sum()), tv=tv, pv_tv=pv_tv, ev=ev, equity=equity, price=price,
        interest_td=interest_td, ni=ni, wacc=wacc, g=g,
    )


def dcf_sensitivity(d: dict) -> pd.DataFrame:
    """Intrinsic value per share on a WACC × g grid (±1 pp in 0.5 pp steps; WACC floored at 0.5%)."""
    waccs = np.maximum(d["wacc"] + np.arange(-0.01, 0.0101, 0.005), 0.005)
    gs = d["g"] + np.arange(-0.01, 0.0101, 0.005)
    grid = np.full((len(waccs), len(gs)), np.nan)
    for i, w in enumerate(waccs):
        for j, gg in enumerate(gs):
            r = dcf_valuation(d, wacc=w, g=gg)
            grid[i, j] = r["price"] if r["valid"] else np.nan
    return pd.DataFrame(grid, index=waccs, columns=gs)
