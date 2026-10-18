"""
Relative valuation and the football field.

Peer multiples (trading comparables or precedent transactions) are applied to the Target's LTM
metrics to get implied values per share, which the football field compares with the DCF range,
the 52-week trading range and the offer price.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .utils import safe_div

# Multiples supported, mapped to the Target metric they apply to. All are enterprise-value based.
MULTIPLES = {"EV/EBITDA": "ebitda", "EV/Revenue": "revenue"}


def implied_price(multiple: float, metric: float, net_debt: float, shares: float) -> float:
    """Value per share implied by an EV multiple: (multiple × metric − net debt) / shares."""
    return safe_div(multiple * metric - net_debt, shares)


def multiple_stats(values) -> dict:
    """25th percentile, median and 75th percentile of the positive, finite multiples."""
    v = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype=float)
    v = v[np.isfinite(v) & (v > 0)]
    if v.size == 0:
        return dict(n=0, p25=np.nan, median=np.nan, p75=np.nan)
    return dict(n=int(v.size), p25=float(np.percentile(v, 25)), median=float(np.median(v)),
                p75=float(np.percentile(v, 75)))


def implied_multiples(target: dict, offer_equity_value: float | None = None, market_price: float | None = None) -> dict:
    """
    The Target's own multiples at market and at the offer, for comparison with peers.
    `target` holds: ebitda, revenue, net_debt, shares.
    """
    out = {}
    for label, price_ev in (("market", None if market_price is None else market_price * target["shares"]),
                            ("offer", offer_equity_value)):
        if price_ev is None:
            continue
        ev = price_ev + target["net_debt"]
        out[label] = {m: safe_div(ev, target[k]) for m, k in MULTIPLES.items()}
    return out


def football_field(target: dict, comps: pd.DataFrame | None, precedents: pd.DataFrame | None,
                   dcf_grid: pd.DataFrame | None, range_52w: tuple | None) -> pd.DataFrame:
    """
    Valuation ranges per share. `target` holds ebitda, revenue, net_debt, shares.
    - Trading comps / precedents: interquartile range of each multiple (median as midpoint).
    - DCF: min–max of the central 3×3 block of the WACC × g grid (±0.5 pp around the base case).
    - 52-week trading range: as given.
    Returns a DataFrame with columns Method, Low, Mid, High, Basis (rows with no data are dropped).
    """
    rows = []
    for name, df in (("Trading comps", comps), ("Precedent transactions", precedents)):
        if df is None or df.empty:
            continue
        for mult, key in MULTIPLES.items():
            if mult not in df.columns:
                continue
            s = multiple_stats(df[mult])
            if s["n"] == 0:
                continue
            px = [implied_price(s[q], target[key], target["net_debt"], target["shares"]) for q in ("p25", "median", "p75")]
            rows.append((f"{name} — {mult}", min(px[0], px[2]), px[1], max(px[0], px[2]),
                         f"{s['p25']:.1f}x–{s['p75']:.1f}x (median {s['median']:.1f}x, n={s['n']})"))
    if dcf_grid is not None and dcf_grid.shape[0] >= 3 and dcf_grid.shape[1] >= 3:
        r0, c0 = dcf_grid.shape[0] // 2, dcf_grid.shape[1] // 2
        core = dcf_grid.iloc[r0 - 1:r0 + 2, c0 - 1:c0 + 2].to_numpy(dtype=float)
        core = core[np.isfinite(core)]
        if core.size:
            rows.append(("DCF (WACC ±0.5 pp, g ±0.5 pp)", float(core.min()), float(dcf_grid.iat[r0, c0]),
                         float(core.max()), "Gordon growth terminal value"))
    if range_52w and all(v is not None and np.isfinite(v) for v in range_52w):
        lo, hi = sorted(range_52w)
        rows.append(("52-week trading range", lo, (lo + hi) / 2, hi, "Unaffected share price"))
    return pd.DataFrame(rows, columns=["Method", "Low", "Mid", "High", "Basis"])
