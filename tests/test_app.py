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
    crashes = [e.value for e in app.error if e.value.startswith("Error en")]
    assert not crashes, crashes


def test_pitchbook_export(app):
    btn = next(b for b in app.button if "Pitchbook" in b.label)
    btn.click().run()
    assert not app.exception
    data = app.session_state["pitchbook"]["data"]
    assert data[:2] == b"PK"   # xlsx is a zip archive
