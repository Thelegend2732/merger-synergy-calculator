"""
Preset deal cases. A case is a full set of widget values (keyed by Streamlit widget key, in UI units:
millions, prices, percentages as 0–100) plus provenance metadata, so every number in a real case can
be traced to a source or is explicitly flagged as an assumption.
"""
from __future__ import annotations

BASIS_DCF = "Intrinsic value (DCF)"
BASIS_MARKET = "Market price"

# Illustrative case: the app's defaults. Every widget key must be present here.
DEFAULT_VALUES = dict(
    # Acquirer
    acq_ni=500.0, acq_sh=200.0, acq_px=50.0, acq_ebitda=900.0, acq_netdebt=1200.0, acq_cash=600.0,
    # Target market data
    tgt_sh=80.0, tgt_px=20.0, tgt_book=600.0,
    # Consideration
    basis=BASIS_DCF, premium=30.0, cash_pct=50, tax=25.0,
    # Synergies, PPA, phasing
    cost_syn=60.0, rev_syn=20.0, rev_syn_mg=30.0, integ=30.0, ppa_pct=30, ppa_life=10,
    ph1=50, ph2=75, ph3=100, year="Year 1", eps_basis="GAAP",
    # Target DCF
    dcf_rev=640.0, dcf_gr=6.0, dcf_mg=27.0, dcf_da=6.0, dcf_cx=7.0, dcf_nwc=10.0, dcf_wacc=8.5, dcf_g=2.5,
    dcf_nd=100.0, dcf_td=5.0,
    # Capital structure
    cap_cash=30, cap_sr=50, rate_cash=3.0, rate_sr=5.5, rate_mz=10.0, sr_term=7, fee_adv=1.5, fee_fin=2.0,
    incl_syn=False,
    # Monte Carlo
    mc_vol=20, mc_seed=42,
)

ILLUSTRATIVE = dict(
    name="Illustrative deal",
    description="Hypothetical mid-cap acquisition used to demonstrate the model.",
    sources=[],
    assumptions=["All figures are hypothetical."],
    values=DEFAULT_VALUES,
)

_ANSYS_PR = "https://www.sec.gov/Archives/edgar/data/1013462/000101346224000006/anssex991-pressrelease2023.htm"
_DEAL_PR = "https://www.ansys.com/news-center/press-releases/1-16-24-synopsys-acquires-ansys"

SYNOPSYS_ANSYS = dict(
    name="Synopsys / Ansys (announced Jan 2024)",
    description=(
        "Synopsys agreed to acquire Ansys for $197.00 in cash plus 0.3450 Synopsys shares per Ansys share "
        "(≈ $390.19, a ≈29% premium to the undisturbed price of 21 Dec 2023), ≈ $35 bn of enterprise value. "
        "The cash component was funded with cash on hand and $16 bn of committed debt. USD millions."
    ),
    sources=[
        ("Deal announcement (terms, synergies, financing, 16.5% pro-forma ownership)", _DEAL_PR),
        ("Ansys FY2023 results, SEC exhibit 99.1 (revenue, operating income, net income, shares, "
         "cash, debt, equity, interest)", _ANSYS_PR),
        ("Synopsys FY2023 (Oct-23) financials and 21 Dec 2023 close: Yahoo Finance via yfinance", None),
    ],
    assumptions=[
        "Ansys D&A (≈$132.5 M) and capex ($25.3 M) from its FY2023 10-K / data aggregators.",
        "Synopsys available cash of $3.0 bn: the $19 bn cash need less the $16 bn of committed debt.",
        "Cash consideration rounded to 50% (actual ≈50.5% of the $390.19 offer value).",
        "Integration costs (≈1× run-rate cost synergies), PPA split and life, fees, debt pricing, DCF growth, "
        "WACC and the 21% tax rate are analyst assumptions, not company disclosures.",
        "EPS basis set to Adjusted (excl. PPA amortisation and integration costs), the basis on which the "
        "deal was presented; switch to GAAP in the sidebar to see the reported-earnings impact.",
        "Leverage uses GAAP EBITDA (after stock-based compensation); on the adjusted EBITDA the companies "
        "report, pro-forma leverage is materially lower than shown.",
        "Revenue synergies ($400 M by year 4) are converted to EBITDA at a 35% margin; phasing reaches the "
        "full run-rate in Year 3.",
    ],
    values={
        **DEFAULT_VALUES,
        # Synopsys, FY ended 31 Oct 2023; price = close of 21 Dec 2023 (undisturbed date of the deal)
        "acq_ni": 1229.9, "acq_sh": 152.1, "acq_px": 559.96, "acq_ebitda": 1555.3, "acq_netdebt": -908.0,
        "acq_cash": 3000.0,
        # Ansys, FY ended 31 Dec 2023; undisturbed price implied by $390.19 / 1.29
        "tgt_sh": 87.39, "tgt_px": 302.47, "tgt_book": 5390.4,
        "basis": BASIS_MARKET, "premium": 29.0, "cash_pct": 50, "tax": 21.0,
        "cost_syn": 400.0, "rev_syn": 400.0, "rev_syn_mg": 35.0, "integ": 400.0, "ppa_pct": 30, "ppa_life": 10,
        "ph1": 25, "ph2": 60, "ph3": 100, "year": "Year 3", "eps_basis": "Adjusted",
        # Ansys DCF: revenue 2,269.9; EBITDA = operating income 626.1 + D&A 132.5; net debt = 753.9 − 860.4
        "dcf_rev": 2269.9, "dcf_gr": 9.0, "dcf_mg": 33.4, "dcf_da": 5.8, "dcf_cx": 1.1, "dcf_nwc": 5.0,
        "dcf_wacc": 9.0, "dcf_g": 3.5, "dcf_nd": -106.5, "dcf_td": 6.25,
        # Funding: ≈15% balance sheet cash, ≈85% new senior debt (bonds + term loans)
        "cap_cash": 15, "cap_sr": 85, "rate_cash": 4.5, "rate_sr": 5.25, "rate_mz": 8.0, "sr_term": 7,
        "fee_adv": 0.5, "fee_fin": 1.0,
        "mc_vol": 25,
    },
)

CASES = {c["name"]: c for c in (ILLUSTRATIVE, SYNOPSYS_ANSYS)}
