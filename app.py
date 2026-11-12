"""
Merger Synergy Calculator — Streamlit entry point.

Run:    streamlit run app.py
Layout: engine/   pure financial model (no Streamlit)
        reports/  Excel pitchbook export
        ui/       sidebar, one module per tab, shared components, visual system (theme.py)

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

from engine import fmt_value, project_years, require
from ui import alerts, pitchbook, tab_capital, tab_dcf, tab_montecarlo, tab_sensitivity, tab_summary, tab_valuation
from ui.cases import INFO_KEY, init_state, render_case_banner
from ui.components import guarded
from ui.sidebar import render_sidebar
from ui.theme import icon, inject_css, render_header, scope

st.set_page_config(page_title="Merger Synergy Calculator", page_icon=":material/handshake:", layout="wide",
                   initial_sidebar_state="expanded")
inject_css()
init_state()   # seed widget values (illustrative case) on the first run

# Tab labels: icon + text. TAB_NAMES (without icons) is what tests and the screenshot script use.
TAB_NAMES = ["DCF Valuation", "Comps & Football", "Capital & Risk", "Summary", "Sensitivity", "Monte Carlo"]
TAB_ICONS = ["dcf", "comps", "capital", "summary", "sensitivity", "montecarlo"]
TAB_LABELS = [f"{icon(ic)} {name}" for ic, name in zip(TAB_ICONS, TAB_NAMES)]

header_box = st.container()   # filled at the end: the chips need the verdict
export_box, inp = render_sidebar()
render_case_banner()
P = inp.P
alerts_box = st.container()   # global alerts: filled at the end, visible from every tab
t_dcf, t_val, t_cap, t_sum, t_sens, t_mc = st.tabs(TAB_LABELS)
out: dict = {}
NEEDS_MODEL = "the model could not be computed; check the DCF and Capital Structure tabs."

with guarded(t_dcf, "DCF Valuation"), scope("dcf"):
    out["dcf"] = tab_dcf.render(inp)
    P.update(out["dcf"]["target"])

with guarded(t_cap, "Capital Structure & Risk"), scope("capital"):
    require("dcf" in out, "the DCF tab failed; fix it first.")
    out["cap"] = tab_capital.render(inp, out["dcf"]["base_price"])

# Drawn in the second tab, but computed here because the football field needs the offer price
with guarded(t_val, "Comps & Football Field"), scope("comps"):
    require("cap" in out, "the Capital Structure tab failed; fix it first.")
    out["val"] = tab_valuation.render(inp, out["dcf"], out["cap"]["deal"])

# Model core: ONE base (phased synergies + DCF Target net income) for Summary, Sensitivity and Monte Carlo
model, model_err = None, ""
try:
    require("cap" in out, "the Capital Structure tab failed")
    proj = project_years(P, out["cap"]["deal"])
    cur_syn, cur_integ, cur_tni, base = proj[inp.yi]
    model = dict(proj=proj, cur_syn=cur_syn, cur_integ=cur_integ, cur_tni=cur_tni, base=base)
except Exception as exc:  # noqa: BLE001 - an earlier tab failed; reported in the alerts box
    model_err = f"{type(exc).__name__}: {exc}"

with guarded(t_sum, "Transaction Summary"), scope("summary"):
    require(model is not None, NEEDS_MODEL)
    out["summary"] = tab_summary.render(inp, out["dcf"]["base_price"], out["dcf"]["base_label"],
                                        out["cap"]["deal"], model)

with guarded(t_sens, "Projections & Sensitivity"), scope("sensitivity"):
    require(model is not None, NEEDS_MODEL)
    out["sens"] = tab_sensitivity.render(inp, out["dcf"]["base_price"], out["cap"]["deal"], model)

with guarded(t_mc, "Monte Carlo Risk"), scope("montecarlo"):
    require(model is not None, NEEDS_MODEL)
    out["mc"] = tab_montecarlo.render(inp, out["cap"]["deal"], model)

with guarded(alerts_box, "Model alerts"):
    alerts.render(inp, out, model_err)

pitchbook.render(export_box, inp, out)

# Header band with live status chips (case, analysis year, EPS basis, verdict)
with header_box:
    info = st.session_state.get(INFO_KEY) or {}
    chips = [("case", info.get("name", "Custom inputs"), ""),
             ("year", f"{inp.year_sel} · {inp.eps_basis} EPS", "")]
    if model is not None:
        acc = model["base"]
        if acc.get("accretive") is not None and acc["acc_pct"] == acc["acc_pct"]:   # not NaN
            chips.append((
                "accretive" if acc["accretive"] else "dilutive",
                f"{'Accretive' if acc['accretive'] else 'Dilutive'} {fmt_value(acc['acc_pct'], 'pct_s')}",
                "ok" if acc["accretive"] else "bad",
            ))
    render_header("Merger Synergy Calculator",
                  "DCF valuation, capital structure and EPS accretion / dilution. Amounts in millions, "
                  "except per-share data.", chips, eyebrow="M&A analytics · accretion / dilution model")
