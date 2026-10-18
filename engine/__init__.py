"""
Pure financial engine of the Merger Synergy Calculator.

No Streamlit or Plotly imports: every function is pure (same inputs, same outputs), so the model can
be unit-tested, reused from a notebook and cached by the UI. Amounts are in millions except prices
and EPS.

Modules:
  constants  palette, horizons, credit thresholds, input caps
  utils      safe maths and the formatted-table convention shared with the Excel export
  dcf        Target DCF and WACC × g sensitivity
  deal       synergies, PPA, funding & debt schedule, pro-forma EPS, breakeven, ownership, leverage
  analytics  accretion/dilution sensitivity grid and Monte Carlo
"""
from .analytics import run_montecarlo, sensitivity_matrix
from .constants import (
    AMBER, DCF_YEARS, GREEN, GREY, LEVERAGE_LIMIT, LEVERAGE_WARN, MAX_M, MAX_PX, MAX_SH, MAX_SYN, N_SIM, NAVY,
    RED, STAT_LABELS, YEARS,
)
from .dcf import dcf_sensitivity, dcf_valuation
from .deal import (
    breakeven_synergies, build_deal, leverage_metrics, max_premium_eps_neutral, ownership_contribution,
    pf_net_income, project_years, purchase_price_allocation, run_rate_synergies, scenario, year_inputs,
)
from .utils import (
    FMT_PY, ModelError, display_table, fmt_value, make_table, require, safe_div, safe_histogram,
)
