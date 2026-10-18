"""Smoke tests: the Streamlit app runs end-to-end and the Excel export builds."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture(scope="module")
def app():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    return at


def test_app_runs_without_exceptions(app):
    assert not app.exception
    # st.error is also used for model verdicts (e.g. "DILUTIVE"); only guarded() failures are bugs
    crashes = [e.value for e in app.error if e.value.startswith("Error in")]
    assert not crashes, crashes


def test_pitchbook_export(app):
    btn = next(b for b in app.button if "pitchbook" in b.label.lower())
    btn.click().run()
    assert not app.exception
    data = app.session_state["pitchbook"]["data"]
    assert data[:2] == b"PK"   # xlsx is a zip archive


def test_every_tab_renders(app):
    labels = [t.label for t in app.tabs]
    assert labels == ["DCF Valuation", "Capital Structure & Risk", "Transaction Summary",
                      "Projections & Sensitivity", "Monte Carlo Risk"]
    for tab in app.tabs:
        assert len(tab.children) > 0, tab.label


def test_market_price_basis_and_all_stock(app):
    app.sidebar.radio(key="basis").set_value("Market price")
    app.sidebar.slider(key="cash_pct").set_value(0)
    app.run()
    assert not app.exception
    assert not [e.value for e in app.error if e.value.startswith("Error in")]


def test_synopsys_ansys_case_matches_public_terms():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.session_state["case_choice"] = "Synopsys / Ansys (announced Jan 2024)"
    next(b for b in at.button if b.label == "Load preset").click().run()
    assert not at.exception
    assert not [e.value for e in at.error if e.value.startswith("Error in")]
    summary = {m.label: m.value for m in at.metric}
    # Disclosed: Ansys holders own ~16.5% of the combined company
    own = float(summary["Pro-forma ownership: Target"].rstrip("%"))
    assert own == pytest.approx(16.5, abs=0.3)
    # Disclosed: $390.19 implied value per Ansys share
    table = next(df.value for df in at.dataframe if "Offer price per share" in df.value.iloc[:, 0].tolist())
    offer = table.set_index(table.columns[0]).loc["Offer price per share"].iloc[0]
    assert offer == "390.19"
