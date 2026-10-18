import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture
def dcf_inputs():
    return dict(rev0=640.0, growth=0.06, margin=0.27, da_pct=0.06, capex_pct=0.07, nwc_pct=0.10,
                wacc=0.085, g=0.025, net_debt=100.0, td_rate=0.05, shares=80.0, tax=0.25)


@pytest.fixture
def params(dcf_inputs):
    """Deal parameters matching the app defaults."""
    from engine import dcf_valuation

    dcf = dcf_valuation(dcf_inputs)
    return dict(
        acq_ni=500.0, acq_sh=200.0, acq_px=50.0, acq_ebitda=900.0, acq_netdebt=1200.0, acq_cash=600.0,
        tgt_sh=80.0, tgt_px=20.0, cash_w=0.5, tax=0.25, total_syn=80.0, integration=30.0,
        phases=[0.5, 0.75, 1.0], tgt_ebitda=640.0 * 0.27, tgt_netdebt=100.0,
        tgt_ni_y=[float(v) for v in dcf["ni"][:3]],
        cap_cash=0.3, cap_senior=0.5, cap_mezz=0.2, rate_senior=0.055, rate_mezz=0.10, rate_cash=0.03,
    )
