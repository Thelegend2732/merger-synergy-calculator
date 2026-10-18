"""Numeric helpers and the formatted-table convention shared by the UI and the Excel export."""
from __future__ import annotations

import numpy as np
import pandas as pd


def safe_div(num: float, den: float, default: float = np.nan) -> float:
    """Division guarded against zero or NaN denominators."""
    if den is None or pd.isna(den) or den == 0:
        return default
    return num / den


class ModelError(Exception):
    """Controlled model error (unavailable dependency, non-finite result...)."""


def require(cond: bool, msg: str) -> None:
    """Raise ModelError with a clear message when a model precondition does not hold."""
    if not cond:
        raise ModelError(msg)


# Format keys: every table row carries one, and it drives both on-screen text and Excel number formats
FMT_PY = {
    "m1": lambda v: f"{v:,.1f}",
    "m2": lambda v: f"{v:,.2f}",
    "eps": lambda v: f"{v:,.3f}",
    "eps_s": lambda v: f"{v:+,.3f}",
    "pct": lambda v: f"{v:.2%}",
    "pct_s": lambda v: f"{v:+.2%}",
    "x": lambda v: f"{v:.2f}x",
    "txt": str,
}


def fmt_value(v, key: str) -> str:
    """Format a value with its key; tolerates NaN/None/inf."""
    if isinstance(v, str):
        return v
    if v is None or pd.isna(v) or not np.isfinite(v):
        return "n/a"
    return FMT_PY[key](float(v))


def make_table(first_col: str, columns: list, rows: list) -> pd.DataFrame:
    """
    Numeric table with one format key per row.
    rows = [(label, value | [values], format_key), ...]
    Resulting columns: [first_col, *columns, "fmt"].
    """
    data = []
    for label, vals, key in rows:
        vals = list(vals) if isinstance(vals, (list, tuple, np.ndarray)) else [vals]
        data.append([label, *vals, key])
    return pd.DataFrame(data, columns=[first_col, *columns, "fmt"])


def display_table(df: pd.DataFrame) -> pd.DataFrame:
    """Formatted-text version (for display) of a table built with make_table."""
    out = df.drop(columns="fmt").astype(object)
    for i, key in enumerate(df["fmt"]):
        for c in out.columns[1:]:
            out.iat[i, out.columns.get_loc(c)] = fmt_value(df.iat[i, df.columns.get_loc(c)], key)
    return out


def safe_histogram(values, bins: int = 40):
    """
    Robust histogram: drops non-finite values and handles degenerate distributions (all draws equal,
    or a range that is tiny relative to the magnitude), where np.histogram fails. Returns (counts, edges).
    """
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return np.array([0]), np.array([0.0, 1.0])
    lo, hi = float(v.min()), float(v.max())
    if hi - lo <= max(1e-12, 1e-9 * max(abs(lo), abs(hi))):
        w = max(1e-6, abs(lo) * 1e-6)
        return np.array([v.size]), np.array([lo - w, lo + w])
    return np.histogram(v, bins=bins, range=(lo, hi))


def describe(v: np.ndarray) -> list:
    """Summary statistics in the order of constants.STAT_LABELS."""
    return [np.mean(v), np.median(v), np.std(v), np.percentile(v, 5), np.percentile(v, 95), v.min(), v.max()]
