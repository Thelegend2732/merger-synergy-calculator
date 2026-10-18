"""
Deal mechanics: synergies, purchase price allocation, funding and debt schedule, pro-forma EPS,
breakeven analysis, ownership vs. contribution and leverage.

`p` is the flat parameter dict assembled by the UI (see ui/sidebar.py and app.py for the keys).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .constants import YEARS
from .utils import safe_div


def run_rate_synergies(cost_syn: float, rev_syn: float, rev_syn_margin: float) -> float:
    """
    Run-rate synergies at EBITDA level (pre-tax). Cost synergies drop straight to profit; revenue
    synergies only contribute their margin (20 M of extra sales is not 20 M of EBIT).
    """
    return cost_syn + rev_syn * rev_syn_margin


def purchase_price_allocation(p: dict, equity_value: float) -> dict:
    """
    Simplified PPA. The excess of the purchase price over the Target's book equity is partly allocated
    to identifiable intangibles (amortised over `ppa_life` years), which create a deferred tax liability
    (DTL = intangibles × t); the remainder is goodwill (not amortised, tested for impairment).
        Goodwill = price − book equity − intangibles + DTL
    If the price is below book value no intangibles are recognised and negative goodwill flags a
    bargain purchase.
    """
    book = p.get("tgt_book_equity", 0.0)
    excess = equity_value - book
    intangibles = max(excess, 0.0) * p.get("ppa_intang_pct", 0.0)
    dtl = intangibles * p["tax"]
    goodwill = excess - intangibles + dtl
    life = p.get("ppa_life", 0)
    amort = safe_div(intangibles, life, default=0.0)
    return dict(book_equity=book, excess=excess, intangibles=intangibles, dtl=dtl, goodwill=goodwill,
                ppa_amort=amort, bargain=goodwill < 0)


def build_deal(p: dict, base_price: float, premium: float) -> dict:
    """
    Transaction structure. The Target's base price comes from the DCF (or the market).

    Cash uses = cash consideration + advisory fees (one-off, excluded from recurring EPS) + financing
    fees (% of new debt, capitalised and amortised over the Senior term). They are funded with balance
    sheet cash + Senior + Mezzanine (p['cap_*'] sum to 1). Financing fees depend on the debt they fund,
    so the circularity is solved in closed form:
        U = (cash consideration + advisory fees) / (1 − f × debt share)

    Debt schedule (Years 1..3): Senior amortises straight-line over `senior_term` years with interest on
    the opening balance; Mezzanine is bullet. Annual financing cost = interest + opportunity cost of the
    cash used; financing-fee and PPA intangible amortisation are added on top. All four reduce
    pro-forma net income after tax.
    """
    offer_price = base_price * (1 + premium)
    equity_value = offer_price * p["tgt_sh"]
    cash_consid = equity_value * p["cash_w"]
    stock = equity_value - cash_consid
    new_shares = safe_div(stock, p["acq_px"], default=0.0)

    adv_fees = equity_value * p.get("fee_adv", 0.0)
    debt_share = p["cap_senior"] + p["cap_mezz"]
    fin_fee_pct = p.get("fee_fin", 0.0)
    cash = (cash_consid + adv_fees) / (1 - fin_fee_pct * debt_share)   # fin_fee_pct < 1 by input caps
    cash_bs = cash * p["cap_cash"]
    senior = cash * p["cap_senior"]
    mezz = cash * p["cap_mezz"]
    fin_fees = (senior + mezz) * fin_fee_pct
    debt = senior + mezz

    # Three-year debt schedule
    term = max(int(p.get("senior_term", 0)), 0)
    n = len(YEARS)
    yrs = np.arange(n)
    if term > 0:
        senior_beg = senior * np.clip(1 - yrs / term, 0.0, 1.0)
        senior_repay = np.minimum(senior / term, senior_beg)
        fee_amort = np.where(yrs < term, fin_fees / term, 0.0)
    else:   # no amortisation: bullet, fees expensed in Year 1
        senior_beg = np.full(n, senior)
        senior_repay = np.zeros(n)
        fee_amort = np.where(yrs == 0, fin_fees, 0.0)
    int_senior_y = senior_beg * p["rate_senior"]
    int_mezz_y = np.full(n, mezz * p["rate_mezz"])
    opp_cost = cash_bs * p["rate_cash"]
    interest_y = int_senior_y + int_mezz_y
    fin_cost_y = interest_y + opp_cost

    ppa = purchase_price_allocation(p, equity_value)
    # Pre-tax items that reduce pro-forma net income each year
    eps_costs_y = fin_cost_y + fee_amort + ppa["ppa_amort"]

    return dict(
        premium=premium, base_price=base_price, offer_price=offer_price, equity_value=equity_value,
        cash_consid=cash_consid, adv_fees=adv_fees, fin_fees=fin_fees, cash=cash, stock=stock,
        new_shares=new_shares, exchange_ratio=safe_div(new_shares, p["tgt_sh"], default=0.0),
        cash_bs=cash_bs, senior=senior, mezz=mezz, debt=debt,
        # Year 1 values (single-period tables)
        int_senior=float(int_senior_y[0]), int_mezz=float(int_mezz_y[0]), interest=float(interest_y[0]),
        opp_cost=opp_cost, fin_cost=float(fin_cost_y[0]), avg_cost_debt=safe_div(float(interest_y[0]), debt),
        # Per-year schedule
        senior_beg=senior_beg, senior_repay=senior_repay, int_senior_y=int_senior_y, int_mezz_y=int_mezz_y,
        interest_y=interest_y, fin_cost_y=fin_cost_y, fee_amort_y=fee_amort, eps_costs_y=eps_costs_y,
        **ppa,
    )


def year_inputs(p: dict, i: int) -> tuple:
    """
    Single source for year i (0..2): captured (phased) synergies, integration costs (Year 1 only;
    excluded on an adjusted EPS basis) and the Target's net income from the DCF.
    """
    syn = p["total_syn"] * p["phases"][i]
    integ = p["integration"] if i == 0 and not p.get("adjusted_eps", False) else 0.0
    return syn, integ, p["tgt_ni_y"][i]


def pf_net_income(p: dict, deal: dict, year_idx: int, synergies, integration, tgt_ni):
    """
    Pro-forma net income for `year_idx` (accepts synergy arrays, e.g. for Monte Carlo):
    Acquirer NI + Target NI + (synergies − integration − financing cost − fee amortisation
    − PPA intangible amortisation) × (1 − t).
    On an adjusted basis (p['adjusted_eps']) PPA amortisation is excluded, as banks and acquirers
    usually do when they quote "cash EPS" accretion.
    """
    tax = p["tax"]
    costs = deal["eps_costs_y"][year_idx] - (deal["ppa_amort"] if p.get("adjusted_eps", False) else 0.0)
    return p["acq_ni"] + tgt_ni + (synergies - integration - costs) * (1 - tax)


def scenario(p: dict, deal: dict, synergies: float, integration: float, tgt_ni: float, year_idx: int = 0) -> dict:
    """Pro-forma EPS and accretion/dilution for given synergies, integration costs and Target NI."""
    tax = p["tax"]
    fin_at = deal["fin_cost_y"][year_idx] * (1 - tax)
    pf_ni = pf_net_income(p, deal, year_idx, synergies, integration, tgt_ni)
    pf_shares = p["acq_sh"] + deal["new_shares"]
    sa_eps = safe_div(p["acq_ni"], p["acq_sh"])
    pf_eps = safe_div(pf_ni, pf_shares)
    acc = pf_eps - sa_eps
    return dict(
        pf_ni=pf_ni, pf_shares=pf_shares, sa_eps=sa_eps, pf_eps=pf_eps, acc=acc,
        acc_pct=safe_div(acc, abs(sa_eps)), fin_at=fin_at,
        accretive=bool(acc >= 0) if not pd.isna(acc) else False,
    )


def project_years(p: dict, deal: dict) -> list:
    """Scenario for each of the 3 years: [(synergies, integration, Target NI, scenario), ...]."""
    out = []
    for i in range(len(YEARS)):
        syn, integ, tni = year_inputs(p, i)
        out.append((syn, integ, tni, scenario(p, deal, syn, integ, tni, i)))
    return out


def breakeven_synergies(p: dict, deal: dict, year_idx: int) -> dict:
    """
    Pre-tax synergies needed in `year_idx` for the deal to be EPS-neutral. Pro-forma net income is
    linear in synergies, so it solves in closed form:
        synergies* = (standalone EPS × pro-forma shares − pro-forma NI at zero synergies) / (1 − t)
    Returns the captured synergies needed and their run-rate equivalent (÷ the year's phasing %).
    """
    _, integ, tni = year_inputs(p, year_idx)
    sa_eps = safe_div(p["acq_ni"], p["acq_sh"])
    pf_shares = p["acq_sh"] + deal["new_shares"]
    ni_zero = pf_net_income(p, deal, year_idx, 0.0, integ, tni)
    captured = safe_div(sa_eps * pf_shares - ni_zero, 1 - p["tax"])
    run_rate = safe_div(captured, p["phases"][year_idx])
    return dict(captured=captured, run_rate=run_rate, cushion=p["total_syn"] - run_rate)


def max_premium_eps_neutral(p: dict, base_price: float, year_idx: int, hi: float = 5.0, tol: float = 1e-6) -> float:
    """
    Highest premium over the base price that keeps the deal EPS-neutral in `year_idx` (bisection).
    NaN if the deal is already dilutive at a zero premium; `hi` if it is still accretive at `hi`.
    """
    syn, integ, tni = year_inputs(p, year_idx)

    def acc(prem: float) -> float:
        return scenario(p, build_deal(p, base_price, prem), syn, integ, tni, year_idx)["acc"]

    lo_v = acc(0.0)
    if pd.isna(lo_v) or lo_v < 0:
        return np.nan
    if acc(hi) >= 0:
        return hi
    lo = 0.0
    while hi - lo > tol:
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if acc(mid) >= 0 else (lo, mid)
    return lo


def ownership_contribution(p: dict, deal: dict) -> dict:
    """
    Pro-forma ownership (share of the combined company held by each shareholder base) versus each
    company's contribution of EBITDA, net income (Year 1) and market capitalisation. If Target
    shareholders receive less ownership than they contribute, the deal transfers value to the Acquirer.
    """
    pf_shares = p["acq_sh"] + deal["new_shares"]

    def split(a: float, t: float) -> tuple:
        tot = a + t
        return safe_div(a, tot), safe_div(t, tot)

    return dict(
        own_acq=safe_div(p["acq_sh"], pf_shares), own_tgt=safe_div(deal["new_shares"], pf_shares),
        ebitda=split(p["acq_ebitda"], p["tgt_ebitda"]),
        net_income=split(p["acq_ni"], p["tgt_ni_y"][0]),
        market_cap=split(p["acq_px"] * p["acq_sh"], p["tgt_px"] * p["tgt_sh"]),
    )


def leverage_metrics(p: dict, deal: dict, synergies_in_ebitda: float) -> dict:
    """
    Pro-forma Net Debt / EBITDA at closing. Pro-forma net debt = Acquirer net debt + Target net debt
    + cash deployed (balance sheet cash + new debt). Pro-forma EBITDA = Acquirer + Target (+ synergies).
    """
    ebitda_pf = p["acq_ebitda"] + p["tgt_ebitda"] + synergies_in_ebitda
    net_debt_pf = p["acq_netdebt"] + p["tgt_netdebt"] + deal["cash"]
    return dict(
        ebitda_pf=ebitda_pf,
        net_debt_pf=net_debt_pf,
        lev_pf=safe_div(net_debt_pf, ebitda_pf) if ebitda_pf > 0 else np.nan,
        lev_sa=safe_div(p["acq_netdebt"], p["acq_ebitda"]) if p["acq_ebitda"] > 0 else np.nan,
        coverage=safe_div(ebitda_pf, deal["interest"]) if ebitda_pf > 0 else np.nan,
    )
