"""Unit tests for the pure financial engine (hand-checkable cases)."""
import numpy as np
import pytest

from engine import (
    build_deal, dcf_sensitivity, dcf_valuation, leverage_metrics, project_years, run_montecarlo, scenario,
    sensitivity_matrix,
)


# --- DCF -----------------------------------------------------------------------------------
def test_dcf_flat_case_matches_closed_form():
    # No growth, no D&A/capex/NWC, no tax: FCF is a flat annuity of rev0 * margin
    d = dict(rev0=100.0, growth=0.0, margin=0.2, da_pct=0.0, capex_pct=0.0, nwc_pct=0.0,
             wacc=0.10, g=0.0, net_debt=10.0, td_rate=0.0, shares=10.0, tax=0.0)
    r = dcf_valuation(d)
    fcf = 20.0
    pv_fcf = sum(fcf / 1.1 ** t for t in range(1, 6))
    pv_tv = fcf / 0.10 / 1.1 ** 5
    assert r["valid"]
    assert r["ev"] == pytest.approx(pv_fcf + pv_tv)
    assert r["ev"] == pytest.approx(200.0)          # flat perpetuity: FCF / WACC
    assert r["equity"] == pytest.approx(190.0)
    assert r["price"] == pytest.approx(19.0)


def test_dcf_invalid_when_wacc_below_g(dcf_inputs):
    r = dcf_valuation(dcf_inputs, wacc=0.02, g=0.03)
    assert not r["valid"]
    assert np.isnan(r["price"])


def test_dcf_fcf_components(dcf_inputs):
    r = dcf_valuation(dcf_inputs)
    expected = r["ebitda"] - r["taxes"] - r["capex"] - r["d_nwc"]
    np.testing.assert_allclose(r["fcf"], expected)
    assert r["rev"][0] == pytest.approx(640.0 * 1.06)


def test_dcf_sensitivity_center_equals_base(dcf_inputs):
    grid = dcf_sensitivity(dcf_inputs)
    assert grid.shape == (5, 5)
    assert grid.iat[2, 2] == pytest.approx(dcf_valuation(dcf_inputs)["price"])
    # Higher WACC -> lower value; higher g -> higher value
    assert grid.iat[0, 2] > grid.iat[4, 2]
    assert grid.iat[2, 4] > grid.iat[2, 0]


# --- Deal structure ------------------------------------------------------------------------
def test_build_deal_sources_equal_uses(params):
    deal = build_deal(params, base_price=20.0, premium=0.30)
    assert deal["offer_price"] == pytest.approx(26.0)
    assert deal["equity_value"] == pytest.approx(26.0 * 80)
    assert deal["cash"] + deal["stock"] == pytest.approx(deal["equity_value"])
    assert deal["cash_bs"] + deal["senior"] + deal["mezz"] == pytest.approx(deal["cash"])
    assert deal["new_shares"] == pytest.approx(deal["stock"] / 50.0)


def test_scenario_eps_by_hand(params):
    deal = build_deal(params, base_price=20.0, premium=0.30)
    sc = scenario(params, deal, synergies=40.0, integration=30.0, tgt_ni=100.0)
    t = params["tax"]
    pf_ni = 500 + 100 + (40 - 30) * (1 - t) - deal["fin_cost"] * (1 - t)
    assert sc["pf_ni"] == pytest.approx(pf_ni)
    assert sc["pf_eps"] == pytest.approx(pf_ni / (200 + deal["new_shares"]))
    assert sc["sa_eps"] == pytest.approx(2.5)


def test_project_years_phasing(params):
    deal = build_deal(params, 20.0, 0.30)
    proj = project_years(params, deal)
    assert [p[0] for p in proj] == pytest.approx([40.0, 60.0, 80.0])
    assert [p[1] for p in proj] == pytest.approx([30.0, 0.0, 0.0])


def test_leverage(params):
    deal = build_deal(params, 20.0, 0.30)
    lev = leverage_metrics(params, deal, 0.0)
    assert lev["net_debt_pf"] == pytest.approx(1200 + 100 + deal["cash"])
    assert lev["lev_pf"] == pytest.approx(lev["net_debt_pf"] / (900 + 640 * 0.27))


# --- Heavy computations --------------------------------------------------------------------
def test_sensitivity_center_matches_base_case(params):
    deal = build_deal(params, 20.0, 0.30)
    base = project_years(params, deal)[0][3]
    hm = sensitivity_matrix(params, 20.0, 0.30, 0)
    assert hm["z"][hm["n_y"] // 2, hm["n_x"] // 2] == pytest.approx(base["acc_pct"])


def test_montecarlo_deterministic_and_zero_vol(params):
    deal = build_deal(params, 20.0, 0.30)
    a = run_montecarlo(params, deal, 0, vol=0.2, seed=7, n_sim=2000)
    b = run_montecarlo(params, deal, 0, vol=0.2, seed=7, n_sim=2000)
    np.testing.assert_array_equal(a["eps"], b["eps"])
    flat = run_montecarlo(params, deal, 0, vol=0.0, seed=7, n_sim=500)
    base = project_years(params, deal)[0][3]
    np.testing.assert_allclose(flat["eps"], base["pf_eps"])
