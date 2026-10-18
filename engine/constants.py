"""Shared constants: colour palette, model horizons, credit thresholds and input caps."""

# Palette (shared by the UI and the Excel export so charts look the same everywhere)
GREEN = "#2e9e5b"   # accretive / positive
RED = "#d64545"     # dilutive / negative
AMBER = "#e0a030"   # watch zone
NAVY = "#1f4e79"    # totals / neutral
GREY = "#8a8f98"    # auxiliary

N_SIM = 5000                # Monte Carlo iterations
DCF_YEARS = 5               # explicit DCF forecast horizon
YEARS = ["Year 1", "Year 2", "Year 3"]
LEVERAGE_LIMIT = 4.0        # Net Debt / EBITDA above which the deal is high-risk
LEVERAGE_WARN = 3.0         # watch threshold
STAT_LABELS = ["Mean", "Median", "Std. deviation", "5th percentile", "95th percentile", "Minimum", "Maximum"]

# Input caps (prevent overflow and nonsensical values)
MAX_M = 10_000_000.0    # amounts in millions
MAX_SH = 1_000_000.0    # shares in millions
MAX_PX = 100_000.0      # price per share
MAX_SYN = 1_000_000.0   # synergies / integration costs (M)
