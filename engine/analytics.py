"""Heavier computations (sensitivity grid, Monte Carlo). The UI wraps them with st.cache_data."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .constants import N_SIM
from .deal import build_deal, pf_net_income, scenario, year_inputs
from .utils import describe, require, safe_div, safe_histogram


def sensitivity_matrix(p: dict, base_price: float, premium: float, year_idx: int,
                       n_x: int = 9, n_y: int = 7) -> dict:
    """
    Accretion/dilution grid for `year_idx`: X axis = run-rate synergies (±50%), Y axis = premium over
    the base price (±20%). If synergies or premium are zero a relative range would collapse, so
    absolute ranges are used instead (`fallback=True`). Without fallback, the centre cell equals the
    Summary base case.
    """
    total_syn = p["total_syn"]
    _, integ, tni = year_inputs(p, year_idx)
    phase = p["phases"][year_idx]

    fallback = total_syn <= 0 or premium <= 0
    syn_axis = np.linspace(0, 100, n_x) if total_syn <= 0 else total_syn * np.linspace(0.5, 1.5, n_x)
    prem_axis = np.linspace(0, 0.20, n_y) if premium <= 0 else premium * np.linspace(0.8, 1.2, n_y)

    z = np.zeros((n_y, n_x))
    for iy, prem_val in enumerate(prem_axis):
        deal_iy = build_deal(p, base_price, prem_val)
        for ix, syn_val in enumerate(syn_axis):
            z[iy, ix] = scenario(p, deal_iy, syn_val * phase, integ, tni, year_idx)["acc_pct"]
    return dict(z=z, syn_axis=syn_axis, prem_axis=prem_axis, fallback=fallback, n_x=n_x, n_y=n_y)


def run_montecarlo(p: dict, deal: dict, year_idx: int, vol: float, seed: int, n_sim: int = N_SIM) -> dict:
    """
    Monte Carlo on captured synergies for `year_idx`: normal distribution centred on the phased
    synergies with standard deviation = |synergies| × vol. Everything else (Target NI from the DCF,
    financing cost, amortisation) is held at the Summary base case.

    Uses a local generator (RandomState) instead of NumPy's global seed: deterministic, and no state
    shared between sessions.
    """
    cur_syn, cur_integ, cur_tni = year_inputs(p, year_idx)
    std = abs(cur_syn * vol)

    rs = np.random.RandomState(int(seed))
    syn_draws = rs.normal(loc=cur_syn, scale=std, size=n_sim)
    pf_ni = pf_net_income(p, deal, year_idx, syn_draws, cur_integ, cur_tni)
    pf_shares = p["acq_sh"] + deal["new_shares"]
    eps = pf_ni / pf_shares                          # acq_sh > 0 guaranteed by input caps
    require(bool(np.all(np.isfinite(eps))), "the simulation produced non-finite values; check extreme inputs.")

    sa_eps = safe_div(p["acq_ni"], p["acq_sh"])
    has_sa = not pd.isna(sa_eps) and sa_eps != 0
    acc = (eps - sa_eps) / abs(sa_eps) if has_sa else np.full(n_sim, np.nan)
    accretive = eps >= sa_eps

    # Histogram with shared edges for the accretive / dilutive zones
    counts, edges = safe_histogram(eps, bins=40)
    return dict(
        mean_syn=cur_syn, std_syn=std, integration=cur_integ, tgt_ni=cur_tni, sa_eps=sa_eps,
        syn_draws=syn_draws, eps=eps, acc=acc, prob_acc=float(np.mean(accretive)) * 100,
        eps_mean=float(np.mean(eps)), eps_p5=float(np.percentile(eps, 5)),
        eps_stats=describe(eps), acc_stats=describe(acc),
        counts=counts, edges=edges, mids=(edges[:-1] + edges[1:]) / 2, widths=np.diff(edges),
        cnt_acc=np.histogram(eps[accretive], bins=edges)[0],
        cnt_dil=np.histogram(eps[~accretive], bins=edges)[0],
    )
