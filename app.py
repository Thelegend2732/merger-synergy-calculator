"""
Merger Synergy Calculator — Streamlit entry point.

Run:    streamlit run app.py
Layout: engine/   pure financial model (no Streamlit)
        reports/  Excel pitchbook export
        ui/       sidebar, one module per tab, shared components

Data flow (single source of truth):
  DCF -> value per share -> Target base price -> offer price
  DCF -> Target net income per year -> pro-forma EPS
  Capital structure (cash / Senior / Mezzanine, fees, amortisation) -> financing cost per year
  PPA -> intangible amortisation -> pro-forma EPS
  Phasing + analysis year (sidebar) -> same base for Summary, Sensitivity and Monte Carlo

Each tab runs inside `guarded`: if one fails, it shows an error and the others keep working.
"""
from __future__ import annotations

import streamlit as st

from engine import project_years, require
from ui import alerts, pitchbook, tab_capital, tab_dcf, tab_montecarlo, tab_sensitivity, tab_summary
from ui.cases import init_state, render_case_banner
from ui.components import guarded
from ui.sidebar import render_sidebar

st.set_page_config(page_title="Merger Synergy Calculator", layout="wide")
init_state()   # seed widget values (illustrative case) on the first run

st.title("Merger Synergy Calculator")
st.caption("DCF valuation, capital structure and EPS accretion/dilution "
           "(amounts in millions, except per-share data).")

export_box, inp = render_sidebar()
render_case_banner()
P = inp.P
alerts_box = st.container()   # global alerts: filled at the end, visible from every tab
t_dcf, t_cap, t_sum, t_sens, t_mc = st.tabs([
    "DCF Valuation", "Capital Structure & Risk", "Transaction Summary",
    "Projections & Sensitivity", "Monte Carlo Risk",
])
out: dict = {}
NEEDS_MODEL = "the model could not be computed; check the DCF and Capital Structure tabs."

with guarded(t_dcf, "DCF Valuation"):
    out["dcf"] = tab_dcf.render(inp)
    P.update(out["dcf"]["target"])

with guarded(t_cap, "Capital Structure & Risk"):
    require("dcf" in out, "the DCF tab failed; fix it first.")
    out["cap"] = tab_capital.render(inp, out["dcf"]["base_price"])

# Model core: ONE base (phased synergies + DCF Target net income) for Summary, Sensitivity and Monte Carlo
model, model_err = None, ""
try:
    require("cap" in out, "the Capital Structure tab failed")
    proj = project_years(P, out["cap"]["deal"])
    cur_syn, cur_integ, cur_tni, base = proj[inp.yi]
    model = dict(proj=proj, cur_syn=cur_syn, cur_integ=cur_integ, cur_tni=cur_tni, base=base)
except Exception as exc:  # noqa: BLE001 - an earlier tab failed; reported in the alerts box
    model_err = f"{type(exc).__name__}: {exc}"

with guarded(t_sum, "Transaction Summary"):
    require(model is not None, NEEDS_MODEL)
    out["summary"] = tab_summary.render(inp, out["dcf"]["base_price"], out["dcf"]["base_label"],
                                        out["cap"]["deal"], model)

with guarded(t_sens, "Projections & Sensitivity"):
    require(model is not None, NEEDS_MODEL)
    out["sens"] = tab_sensitivity.render(inp, out["dcf"]["base_price"], out["cap"]["deal"], model)

with guarded(t_mc, "Monte Carlo Risk"):
    require(model is not None, NEEDS_MODEL)
    out["mc"] = tab_montecarlo.render(inp, out["cap"]["deal"], model)

with guarded(alerts_box, "Model alerts"):
    alerts.render(inp, out, model_err)

pitchbook.render(export_box, inp, out)
