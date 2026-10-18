"""
Pitchbook export, built ON DEMAND: the “Prepare” button builds the workbook and stores it in
st.session_state; the download button only serves those bytes. A signature of every input tells
whether the prepared file is still current.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

import streamlit as st

from engine import make_table
from reports import XLSX_AVAILABLE, build_pitchbook

from .components import ST_BTN, ST_DL, ST_DL_NO_RERUN

PB_KEY = "pitchbook"   # st.session_state key holding the prepared workbook


def _assumptions(inp, out: dict):
    P, d, c = inp.P, out["dcf"]["dcf_inputs"], out["cap"]["params"]
    return make_table("Assumption", ["Value"], [
        ("ACQUIRER", "", "txt"),
        ("Net income (M)", P["acq_ni"], "m1"), ("Shares outstanding (M)", P["acq_sh"], "m2"),
        ("Share price", P["acq_px"], "m2"), ("EBITDA (M)", P["acq_ebitda"], "m1"),
        ("Existing net debt (M)", P["acq_netdebt"], "m1"), ("Cash available (M)", P["acq_cash"], "m1"),
        ("TARGET (MARKET)", "", "txt"),
        ("Shares outstanding (M)", P["tgt_sh"], "m2"), ("Market price per share", P["tgt_px"], "m2"),
        ("Book value of equity (M)", P["tgt_book_equity"], "m1"),
        *[(f"Net income from DCF, Year {i + 1} (M)", v, "m1") for i, v in enumerate(P["tgt_ni_y"])],
        ("TRANSACTION", "", "txt"),
        ("Target price basis", out["dcf"]["base_label"], "txt"), ("Target base price", out["dcf"]["base_price"], "m2"),
        ("Premium over base price", inp.premium, "pct"), ("Cash consideration", inp.cash_pct / 100, "pct"),
        ("Stock consideration", 1 - inp.cash_pct / 100, "pct"), ("Tax rate", inp.tax, "pct"),
        ("SYNERGIES AND ANALYSIS", "", "txt"),
        ("Cost synergies (M)", inp.cost_syn, "m1"), ("Revenue synergies (M)", inp.rev_syn, "m1"),
        ("EBITDA margin on revenue synergies", inp.rev_syn_margin, "pct"),
        ("Run-rate synergies at EBITDA level (M)", inp.total_syn, "m1"),
        ("Integration costs (M)", inp.integration, "m1"),
        *[(f"Phasing Year {i + 1}", v, "pct") for i, v in enumerate(inp.phases)],
        ("Analysis year", inp.year_sel, "txt"),
        ("DCF", "", "txt"),
        ("LTM revenue (M)", d["rev0"], "m1"), ("Revenue growth", d["growth"], "pct"),
        ("EBITDA margin", d["margin"], "pct"), ("D&A (% of revenue)", d["da_pct"], "pct"),
        ("Capex (% of revenue)", d["capex_pct"], "pct"), ("NWC (% of Δ revenue)", d["nwc_pct"], "pct"),
        ("WACC", d["wacc"], "pct"), ("Perpetual growth (g)", d["g"], "pct"),
        ("Target net debt (M)", d["net_debt"], "m1"), ("Interest rate on its net debt", d["td_rate"], "pct"),
        ("CAPITAL STRUCTURE", "", "txt"),
        ("Balance sheet cash", c["cap_cash"], "pct"), ("Senior debt", c["cap_senior"], "pct"),
        ("Mezzanine debt", c["cap_mezz"], "pct"), ("Opportunity cost of cash", c["rate_cash"], "pct"),
        ("Senior rate", c["rate_senior"], "pct"), ("Mezzanine rate", c["rate_mezz"], "pct"),
        ("Senior amortisation term (years)", str(c["senior_term"]), "txt"),
        ("Advisory fees (% of equity value)", c["fee_adv"], "pct"),
        ("Financing fees (% of new debt)", c["fee_fin"], "pct"),
        ("PPA", "", "txt"),
        ("Excess price allocated to intangibles", P["ppa_intang_pct"], "pct"),
        ("Useful life of intangibles (years)", str(P["ppa_life"]), "txt"),
    ])


def _collect_tables(inp, out: dict) -> dict:
    """Gather the tables the tabs have already computed. Only runs when the user clicks “Prepare”."""
    return dict(year_label=inp.year_sel, assumptions=_assumptions(inp, out),
                **{k: out["dcf"][k] for k in ("dcf_proj", "dcf_bridge", "dcf_sens")},
                **{k: out["cap"][k] for k in ("tranches", "sources_uses", "debt_schedule", "credit")},
                **out["summary"], **out["sens"],
                **{k: out["mc"][k] for k in ("mc_params", "mc_stats", "mc_hist", "mc_sim")})


def _signature(inp, out: dict) -> str:
    """Fingerprint of every input that affects the workbook."""
    payload = dict(P=inp.P, dcf=out["dcf"]["dcf_inputs"], premium=inp.premium, basis=inp.price_basis,
                   year=inp.year_sel, vol=out["mc"]["vol"], seed=out["mc"]["seed"], incl_syn=out["cap"]["incl_syn"])
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]


def render(box, inp, out: dict) -> None:
    with box:
        st.markdown("**Pitchbook**")
        if not XLSX_AVAILABLE:
            st.error("Missing `xlsxwriter`: install it with `pip install xlsxwriter`.")
            return
        try:
            sig = _signature(inp, out)
            ready = st.session_state.get(PB_KEY)
            is_fresh = bool(ready) and ready["sig"] == sig

            # 1) Prepare: the only place the workbook is built (only when the user asks)
            if st.button("Prepare pitchbook (Excel)", type="secondary" if is_fresh else "primary",
                         help="Builds the workbook in memory with the current inputs. It is not rebuilt on every "
                              "interaction.", **ST_BTN):
                with st.spinner("Building the workbook…"):
                    ready = dict(sig=sig, data=build_pitchbook(_collect_tables(inp, out)),
                                 stamp=datetime.now().strftime("%H:%M:%S"))
                st.session_state[PB_KEY] = ready
                is_fresh = True

            # 2) Download: serves the prepared bytes only (recomputes nothing)
            if is_fresh:
                st.download_button(
                    "Download pitchbook (.xlsx)", data=ready["data"], file_name="Merger_Synergy_Pitchbook.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary",
                    **ST_DL, **ST_DL_NO_RERUN,
                )
                st.caption(f"Prepared at {ready['stamp']} with the current inputs.")
            elif ready:
                st.warning("The prepared pitchbook reflects earlier inputs. Click “Prepare” again for the "
                           "current version.")
            else:
                st.caption("The workbook is only built when you click “Prepare”, so the app stays fast while "
                           "you explore.")
        except Exception as exc:  # the export must never break the app
            st.warning("The pitchbook could not be prepared: a tab has errors or data is missing "
                       f"({type(exc).__name__}: {exc}).")
