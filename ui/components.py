"""
Reusable Streamlit building blocks: version-compatibility shims, cards, chart styling, error isolation
and the cached wrappers around the heavy engine calls.

Design: no injected CSS. Colours come from the Streamlit theme (.streamlit/config.toml) and layout is
built from native components only (bordered containers as cards, asymmetric columns, dividers).
"""
from __future__ import annotations

import inspect
from contextlib import contextmanager

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engine import (
    GREEN, N_SIM, NAVY, RED, dcf_sensitivity, display_table, fmt_value, run_montecarlo, sensitivity_matrix,
)


# ---------------------------------------------------------------------------
# Version compatibility
# ---------------------------------------------------------------------------
def _stretch(fn) -> dict:
    """
    Full-width kwarg for this Streamlit version. Decided per function: `width="stretch"` did not land
    everywhere at once (e.g. in 1.50 download_button had it and plotly_chart did not).
    """
    has_width = "width" in inspect.signature(fn).parameters
    return {"width": "stretch"} if has_width and "stretch" in (fn.__doc__ or "") else {"use_container_width": True}


ST_PLOTLY = _stretch(st.plotly_chart)
ST_DF = _stretch(st.dataframe)
ST_DL = _stretch(st.download_button)
ST_BTN = _stretch(st.button)
# Streamlit >= 1.43: downloading does not rerun the app (skipped on older versions)
ST_DL_NO_RERUN = {"on_click": "ignore"} if "ignore" in (st.download_button.__doc__ or "") else {}
# st.container(border=...) exists since Streamlit 1.29
HAS_BORDER = "border" in inspect.signature(st.container).parameters

HEAT_COLORSCALE = [[0.0, RED], [0.5, "#ffffff"], [1.0, GREEN]]
BLUE_SCALE = [[0.0, "#ffffff"], [1.0, NAVY]]
GRID = "rgba(31, 45, 74, 0.08)"      # faint grid, readable on any light background


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------
def card(parent=None):
    """Native card: bordered container (no border on versions < 1.29)."""
    target = st if parent is None else parent
    return target.container(border=True) if HAS_BORDER else target.container()


def card_title(text: str, caption: str | None = None) -> None:
    """Compact header inside a card."""
    st.markdown(f"**{text}**")
    if caption:
        st.caption(caption)


def gap() -> None:
    """Vertical breathing room between blocks."""
    st.write("")


def style_fig(fig: go.Figure, title: str, height: int = 440) -> go.Figure:
    """Consistent chart style: transparent background, faint grid, left-aligned title."""
    fig.update_layout(
        title=dict(text=title, font=dict(size=15, color=NAVY), x=0, xanchor="left"),
        template="plotly_white",
        height=height,
        margin=dict(t=56, b=40, l=50, r=20),
        font=dict(family="sans-serif", size=12),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID)
    return fig


def show_chart(fig: go.Figure) -> None:
    st.plotly_chart(fig, **ST_PLOTLY)


def show_table(df: pd.DataFrame) -> None:
    """Render a make_table table with its per-row formats."""
    st.dataframe(display_table(df), hide_index=True, **ST_DF)


def verdict_metric(col, label: str, value: float, fmt: str, accretive: bool) -> None:
    """Metric whose delta arrow and colour follow the accretive / dilutive verdict."""
    col.metric(label, "ACCRETIVE" if accretive else "DILUTIVE", delta=fmt_value(value, fmt),
               delta_color="normal")


@contextmanager
def guarded(container, name: str):
    """
    Run a block inside `container` and isolate failures: if it raises, an error is shown in that tab
    and the rest of the app (including the export button) keeps working. Streamlit control-flow
    exceptions (st.stop / rerun) are not `Exception` subclasses and pass through.
    """
    with container:
        try:
            yield
        except Exception as exc:  # noqa: BLE001
            st.error(f"Error in “{name}”: {type(exc).__name__}: {exc}. "
                     "Check the inputs; the other tabs keep working.")


# ---------------------------------------------------------------------------
# Cached heavy computations (recomputed only when their inputs change)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def cached_dcf_sensitivity(dcf_inputs: dict) -> pd.DataFrame:
    """DCF WACC × g grid (25 valuations)."""
    return dcf_sensitivity(dcf_inputs)


@st.cache_data(show_spinner=False)
def cached_sensitivity_matrix(p: dict, base_price: float, premium: float, year_idx: int) -> dict:
    """Accretion/dilution premium × synergies grid (63 scenarios)."""
    return sensitivity_matrix(p, base_price, premium, year_idx)


@st.cache_data(show_spinner=False)
def cached_montecarlo(p: dict, deal: dict, year_idx: int, vol: float, seed: int) -> dict:
    """Monte Carlo simulation (5,000 draws). The cache is invalidated when any model input changes."""
    return run_montecarlo(p, deal, year_idx, vol, seed, N_SIM)
