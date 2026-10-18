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


def _pf_eps(p: dict, deal: dict, year_idx: int, syn, integ, tni, rate_shock):
    """Pro-forma EPS with an extra rate shock on the (floating) Senior balance; vectorised."""
    extra = deal["senior_beg"][year_idx] * rate_shock * (1 - p["tax"])
    return (pf_net_income(p, deal, year_idx, syn, integ, tni) - extra) / (p["acq_sh"] + deal["new_shares"])


def run_montecarlo(p: dict, deal: dict, year_idx: int, vol: float, seed: int, n_sim: int = N_SIM,
                   tni_vol: float = 0.0, rate_vol: float = 0.0, integ_vol: float = 0.0, corr: float = 0.0) -> dict:
    """
    Multi-variable Monte Carlo on the selected year's pro-forma EPS. Four independent standard normal
    draws per iteration (always drawn in the same order, so a seed reproduces the same scenarios):
      - synergies captured ~ N(phased synergies, |synergies| × vol)
      - Target net income  ~ base × (1 + tni_vol × z), with correlation `corr` to the synergy draw
        (both depend on how well the integration is executed)
      - interest-rate shock on the Senior balance ~ N(0, rate_vol), i.e. floating-rate debt
      - integration cost overrun ~ base × max(0, 1 + integ_vol × z) (only where integration costs apply)
    With every volatility but `vol` at zero it reduces to the single-variable synergy simulation.

    Uses a local generator (RandomState) instead of NumPy's global seed: deterministic, and no state
    shared between sessions.
    """
    cur_syn, cur_integ, cur_tni = year_inputs(p, year_idx)
    require(-1.0 <= corr <= 1.0, "correlation must be between -1 and 1.")
    std = abs(cur_syn * vol)

    rs = np.random.RandomState(int(seed))
    z_syn = rs.standard_normal(n_sim)
    z_tni = corr * z_syn + np.sqrt(1 - corr ** 2) * rs.standard_normal(n_sim)
    z_rate, z_integ = rs.standard_normal(n_sim), rs.standard_normal(n_sim)

    syn_draws = cur_syn + std * z_syn
    tni_draws = cur_tni + abs(cur_tni) * tni_vol * z_tni
    rate_draws = rate_vol * z_rate
    integ_draws = cur_integ * np.maximum(0.0, 1 + integ_vol * z_integ)
    eps = _pf_eps(p, deal, year_idx, syn_draws, integ_draws, tni_draws, rate_draws)
    require(bool(np.all(np.isfinite(eps))), "the simulation produced non-finite values; check extreme inputs.")

    sa_eps = safe_div(p["acq_ni"], p["acq_sh"])
    has_sa = not pd.isna(sa_eps) and sa_eps != 0
    acc = (eps - sa_eps) / abs(sa_eps) if has_sa else np.full(n_sim, np.nan)
    accretive = eps >= sa_eps

    # Histogram with shared edges for the accretive / dilutive zones
    counts, edges = safe_histogram(eps, bins=40)
    return dict(
        mean_syn=cur_syn, std_syn=std, integration=cur_integ, tgt_ni=cur_tni, sa_eps=sa_eps,
        syn_draws=syn_draws, tni_draws=tni_draws, rate_draws=rate_draws, integ_draws=integ_draws,
        eps=eps, acc=acc, prob_acc=float(np.mean(accretive)) * 100,
        eps_mean=float(np.mean(eps)), eps_p5=float(np.percentile(eps, 5)),
        eps_stats=describe(eps), acc_stats=describe(acc),
        counts=counts, edges=edges, mids=(edges[:-1] + edges[1:]) / 2, widths=np.diff(edges),
        cnt_acc=np.histogram(eps[accretive], bins=edges)[0],
        cnt_dil=np.histogram(eps[~accretive], bins=edges)[0],
    )


def eps_tornado(p: dict, deal: dict, year_idx: int, vol: float, tni_vol: float = 0.0, rate_vol: float = 0.0,
                integ_vol: float = 0.0) -> pd.DataFrame:
    """
    One-at-a-time sensitivity: pro-forma EPS with each risk driver moved ±1 standard deviation while the
    others stay at the base case. Sorted by swing (largest first), as plotted in a tornado chart.
    """
    syn, integ, tni = year_inputs(p, year_idx)
    base = float(_pf_eps(p, deal, year_idx, syn, integ, tni, 0.0))
    shocks = [
        ("Synergies captured", abs(syn) * vol, lambda d: (syn + d, integ, tni, 0.0)),
        ("Target net income", abs(tni) * tni_vol, lambda d: (syn, integ, tni + d, 0.0)),
        ("Interest rate on Senior debt", rate_vol, lambda d: (syn, integ, tni, d)),
        ("Integration cost overrun", integ * integ_vol, lambda d: (syn, integ + d, tni, 0.0)),
    ]
    rows = []
    for name, sd, args in shocks:
        down = float(_pf_eps(p, deal, year_idx, *args(-sd)))
        up = float(_pf_eps(p, deal, year_idx, *args(sd)))
        rows.append((name, sd, min(down, up), max(down, up), abs(up - down)))
    df = pd.DataFrame(rows, columns=["Driver", "1 std. dev.", "EPS low", "EPS high", "Swing"])
    df.attrs["base_eps"] = base
    return df.sort_values("Swing", ascending=False, ignore_index=True)
