"""Offline tests for the market-data mapping and the preset cases."""
import pytest

from marketdata.cases import CASES, DEFAULT_VALUES
from marketdata.yahoo import acquirer_inputs, estimate_wacc, revenue_cagr, target_inputs

COMPANY = dict(  # shaped like fetch_company() output, in millions
    ticker="TGT", name="Target Co", currency="USD", financial_currency="USD", fiscal_year_end="2025-12-31",
    price=40.0, shares=100.0, revenue=1000.0, revenue_hist=[1000.0, 900.0, 810.0], ebitda=300.0,
    net_income=150.0, da=50.0, capex=60.0, interest=20.0, tax_rate=0.21, debt=400.0, cash=100.0,
    book_equity=900.0, beta=1.2,
)


def test_revenue_cagr():
    assert revenue_cagr([1000.0, 900.0, 810.0]) == pytest.approx((1000 / 810) ** 0.5 - 1)
    assert revenue_cagr([121.0, 110.0, 100.0]) == pytest.approx(0.10)
    assert revenue_cagr([100.0]) is None


def test_wacc_capm():
    w = estimate_wacc(COMPANY, tax=0.25)
    ke = 0.0425 + 1.2 * 0.05
    w_d = 400 / (4000 + 400)
    assert w["kd"] == pytest.approx(0.05)
    assert w["wacc"] == pytest.approx((1 - w_d) * ke + w_d * 0.05 * 0.75)


def test_acquirer_mapping():
    a = acquirer_inputs(COMPANY)
    assert a == dict(acq_ni=150.0, acq_sh=100.0, acq_px=40.0, acq_ebitda=300.0, acq_netdebt=300.0, acq_cash=100.0)


def test_target_mapping_ratios_and_bounds():
    t, _ = target_inputs(COMPANY, tax=0.25)
    assert t["dcf_mg"] == 30.0 and t["dcf_da"] == 5.0 and t["dcf_cx"] == 6.0
    assert t["dcf_nd"] == 300.0 and t["dcf_td"] == 5.0
    assert t["dcf_gr"] == pytest.approx(11.1, abs=0.05)
    assert t["dcf_wacc"] % 0.25 == 0
    huge, _ = target_inputs({**COMPANY, "price": 700_000.0}, tax=0.25)
    assert huge["tgt_px"] == 100_000.0     # clipped to the widget's max


@pytest.mark.parametrize("name", list(CASES))
def test_cases_define_every_widget(name):
    values = CASES[name]["values"]
    assert set(values) == set(DEFAULT_VALUES)
    for k, v in values.items():   # widget types must match the defaults (float vs int vs str)
        assert type(v) is type(DEFAULT_VALUES[k]), k
