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


# --- Phase 1: deal mechanics ---------------------------------------------------------------
from engine import (  # noqa: E402
    breakeven_synergies, max_premium_eps_neutral, ownership_contribution, purchase_price_allocation,
    run_rate_synergies,
)


@pytest.fixture
def full_params(params):
    return {**params, "fee_adv": 0.015, "fee_fin": 0.02, "senior_term": 7,
            "tgt_book_equity": 600.0, "ppa_intang_pct": 0.30, "ppa_life": 10}


def test_revenue_synergies_flow_through_margin():
    assert run_rate_synergies(60.0, 20.0, 0.30) == pytest.approx(66.0)


def test_ppa_goodwill_identity(full_params):
    ppa = purchase_price_allocation(full_params, equity_value=2080.0)
    assert ppa["excess"] == pytest.approx(1480.0)
    assert ppa["intangibles"] == pytest.approx(444.0)
    assert ppa["dtl"] == pytest.approx(111.0)
    assert ppa["goodwill"] == pytest.approx(1480.0 - 444.0 + 111.0)
    assert ppa["ppa_amort"] == pytest.approx(44.4)
    # Book equity + intangibles + goodwill - DTL reconciles to the purchase price
    assert 600 + ppa["intangibles"] + ppa["goodwill"] - ppa["dtl"] == pytest.approx(2080.0)


def test_bargain_purchase_flag(full_params):
    ppa = purchase_price_allocation(full_params, equity_value=500.0)
    assert ppa["intangibles"] == 0.0
    assert ppa["bargain"]


def test_fees_sources_equal_uses(full_params):
    deal = build_deal(full_params, 20.0, 0.30)
    uses = deal["cash_consid"] + deal["adv_fees"] + deal["fin_fees"]
    assert deal["cash"] == pytest.approx(uses)
    assert deal["cash_bs"] + deal["senior"] + deal["mezz"] == pytest.approx(uses)
    assert deal["fin_fees"] == pytest.approx(0.02 * deal["debt"])


def test_senior_amortization_schedule(full_params):
    deal = build_deal(full_params, 20.0, 0.30)
    s = deal["senior"]
    np.testing.assert_allclose(deal["senior_beg"], [s, s * 6 / 7, s * 5 / 7])
    np.testing.assert_allclose(deal["int_senior_y"], deal["senior_beg"] * 0.055)
    assert deal["int_mezz_y"][0] == deal["int_mezz_y"][2]          # mezzanine is bullet
    np.testing.assert_allclose(deal["fee_amort_y"], deal["fin_fees"] / 7)


def test_ppa_amortization_reduces_eps(full_params):
    no_ppa = {**full_params, "ppa_intang_pct": 0.0}
    a = project_years(full_params, build_deal(full_params, 20.0, 0.30))[1][3]
    b = project_years(no_ppa, build_deal(no_ppa, 20.0, 0.30))[1][3]
    amort = build_deal(full_params, 20.0, 0.30)["ppa_amort"]
    assert b["pf_ni"] - a["pf_ni"] == pytest.approx(amort * (1 - full_params["tax"]))


@pytest.mark.parametrize("year", [0, 1, 2])
def test_breakeven_synergies_make_deal_eps_neutral(full_params, year):
    deal = build_deal(full_params, 20.0, 0.30)
    be = breakeven_synergies(full_params, deal, year)
    _, integ, tni, _ = project_years(full_params, deal)[year]
    sc = scenario(full_params, deal, be["captured"], integ, tni, year)
    assert sc["acc"] == pytest.approx(0.0, abs=1e-12)
    assert be["run_rate"] == pytest.approx(be["captured"] / full_params["phases"][year])


def test_max_premium_is_eps_neutral(full_params):
    prem = max_premium_eps_neutral(full_params, 20.0, 2)
    assert 0 < prem < 5
    syn, integ, tni = project_years(full_params, build_deal(full_params, 20.0, prem))[2][:3]
    sc = scenario(full_params, build_deal(full_params, 20.0, prem), syn, integ, tni, 2)
    assert sc["acc"] == pytest.approx(0.0, abs=1e-4)


def test_ownership_sums_to_one(full_params):
    deal = build_deal(full_params, 20.0, 0.30)
    oc = ownership_contribution(full_params, deal)
    assert oc["own_acq"] + oc["own_tgt"] == pytest.approx(1.0)
    assert sum(oc["ebitda"]) == pytest.approx(1.0)
    all_cash = {**full_params, "cash_w": 1.0}
    assert ownership_contribution(all_cash, build_deal(all_cash, 20.0, 0.3))["own_tgt"] == 0.0


def test_montecarlo_matches_deterministic_with_full_mechanics(full_params):
    deal = build_deal(full_params, 20.0, 0.30)
    flat = run_montecarlo(full_params, deal, 1, vol=0.0, seed=1, n_sim=100)
    np.testing.assert_allclose(flat["eps"], project_years(full_params, deal)[1][3]["pf_eps"])


def test_adjusted_eps_excludes_ppa_and_integration(full_params):
    adj = {**full_params, "adjusted_eps": True}
    deal = build_deal(full_params, 20.0, 0.30)
    gaap = project_years(full_params, deal)[0]
    cash = project_years(adj, deal)[0]
    assert cash[1] == 0.0                                    # no integration costs on adjusted basis
    t = full_params["tax"]
    expected = (deal["ppa_amort"] + full_params["integration"]) * (1 - t)
    assert cash[3]["pf_ni"] - gaap[3]["pf_ni"] == pytest.approx(expected)
    be = breakeven_synergies(adj, deal, 0)
    assert scenario(adj, deal, be["captured"], 0.0, cash[2], 0)["acc"] == pytest.approx(0.0, abs=1e-12)
