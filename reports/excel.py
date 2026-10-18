"""
Pitchbook export to Excel.

Takes the tables the UI has already computed (DataFrames) and writes them to an in-memory workbook
(io.BytesIO) with xlsxwriter. It imports no Streamlit and recomputes nothing from the model.

Usage:
    from reports import XLSX_AVAILABLE, build_pitchbook
    data: bytes = build_pitchbook(tables)      # keys listed in build_pitchbook

It is the heaviest operation in the app (it also writes every Monte Carlo draw), so the UI only
calls it when the user explicitly asks for the file.
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd

from engine import DCF_YEARS, GREEN, GREY, N_SIM, NAVY, RED

try:
    import xlsxwriter

    XLSX_AVAILABLE = True
except ImportError:  # the app keeps working; only the export is disabled
    xlsxwriter = None
    XLSX_AVAILABLE = False

# Excel number formats per format key (equivalent to engine.FMT_PY)
FMT_XL = {
    "m1": "#,##0.0",
    "m2": "#,##0.00",
    "eps": "0.000",
    "eps_s": "+0.000;-0.000;0.000",
    "pct": "0.00%",
    "pct_s": "+0.00%;-0.00%;0.00%",
    "x": '0.00"x"',
    "txt": "@",
}


class Pitchbook:
    """Thin xlsxwriter wrapper that writes to memory with consistent formatting."""

    def __init__(self):
        if not XLSX_AVAILABLE:
            raise ImportError("Missing `xlsxwriter`: install it with `pip install xlsxwriter`.")
        self.buf = io.BytesIO()
        self.wb = xlsxwriter.Workbook(self.buf, {"in_memory": True})
        base = {"font_name": "Arial", "font_size": 10}
        self.f_title = self.wb.add_format({**base, "bold": True, "font_size": 14, "font_color": NAVY})
        self.f_sub = self.wb.add_format({**base, "bold": True, "font_color": NAVY, "bottom": 1})
        self.f_note = self.wb.add_format({**base, "italic": True, "font_color": GREY})
        hdr = {**base, "bold": True, "font_color": "#ffffff", "bg_color": NAVY, "border": 1, "align": "center"}
        self.f_hdr = self.wb.add_format({**hdr, "valign": "vcenter", "text_wrap": True})
        self.f_hdr_pct = self.wb.add_format({**hdr, "num_format": "0.0%"})
        self.f_hdr_num = self.wb.add_format({**hdr, "num_format": "#,##0.0"})
        self.f_lbl = self.wb.add_format({**base, "border": 1})
        self.f_txt = self.wb.add_format({**base, "border": 1, "align": "right"})
        self.f_num = {k: self.wb.add_format({**base, "border": 1, "num_format": v}) for k, v in FMT_XL.items()}

    def sheet(self, name: str, title: str, note: str = ""):
        ws = self.wb.add_worksheet(name)
        ws.hide_gridlines(2)
        ws.set_column(0, 0, 44)
        ws.set_column(1, 16, 16)
        ws.write(0, 0, title, self.f_title)
        if note:
            ws.write(1, 0, note, self.f_note)
        return ws

    def subtitle(self, ws, row: int, text: str) -> int:
        ws.write(row, 0, text, self.f_sub)
        return row + 1

    def cell(self, ws, r: int, c: int, v, key: str | None):
        if isinstance(v, str):
            ws.write_string(r, c, v, self.f_txt if c else self.f_lbl)
        elif v is None or pd.isna(v) or not np.isfinite(v):
            ws.write_string(r, c, "n/a", self.f_txt)
        else:
            ws.write_number(r, c, float(v), self.f_num.get(key, self.f_num["m2"]))

    def table(self, ws, row: int, df: pd.DataFrame) -> int:
        """Write a make_table table (one format per row). Returns the next free row."""
        cols = list(df.columns[:-1])
        for j, name in enumerate(cols):
            ws.write(row, j, name, self.f_hdr)
        for i in range(len(df)):
            key = df.iat[i, len(df.columns) - 1]
            ws.write_string(row + 1 + i, 0, str(df.iat[i, 0]), self.f_lbl)
            for j in range(1, len(cols)):
                self.cell(ws, row + 1 + i, j, df.iat[i, j], key)
        return row + len(df) + 2

    def frame(self, ws, row: int, df: pd.DataFrame, formats: dict | None = None, col: int = 0) -> int:
        """Write a DataFrame with one format per column (formats: {column: key})."""
        formats = formats or {}
        for j, name in enumerate(df.columns):
            ws.write(row, col + j, str(name), self.f_hdr)
        for i in range(len(df)):
            for j, name in enumerate(df.columns):
                v = df.iat[i, j]
                if not isinstance(v, str) and (v is None or pd.isna(v)):
                    ws.write_string(row + 1 + i, col + j, "–", self.f_txt)
                else:
                    self.cell(ws, row + 1 + i, col + j, v, formats.get(name))
        return row + len(df) + 2

    def grid(self, ws, row: int, df: pd.DataFrame, corner: str, hdr_fmt, idx_key: str, val_key: str) -> int:
        """Write a 2-D grid (index × columns), e.g. a sensitivity table. Returns the last data row."""
        ws.write(row, 0, corner, self.f_hdr)
        for j, v in enumerate(df.columns):
            ws.write_number(row, 1 + j, float(v), hdr_fmt)
        for i, v in enumerate(df.index):
            ws.write_number(row + 1 + i, 0, float(v), self.f_num[idx_key])
            for j in range(df.shape[1]):
                self.cell(ws, row + 1 + i, 1 + j, df.iat[i, j], val_key)
        return row + df.shape[0]

    def close(self) -> bytes:
        self.wb.close()
        return self.buf.getvalue()


def _row_of(df: pd.DataFrame, label: str) -> int:
    return int(df.index[df.iloc[:, 0] == label][0])


def build_pitchbook(x: dict) -> bytes:
    """
    Build the full workbook and return its bytes.
    Keys of `x`: year_label, assumptions, dcf_proj, dcf_bridge, dcf_sens, comps, precedents, football,
    multiples, target_multiples, tranches, sources_uses, debt_schedule, credit, summary, waterfall, ppa,
    contribution, projection, heat, mc_params, mc_stats, mc_hist, mc_sim, mc_tornado.
    """
    pb = Pitchbook()
    wb = pb.wb
    year = x["year_label"]

    # --- Assumptions ---------------------------------------------------------------------
    ws = pb.sheet("Assumptions", "Model assumptions", "Amounts in millions, except per-share data.")
    pb.table(ws, 3, x["assumptions"])

    # --- DCF -----------------------------------------------------------------------------
    ws = pb.sheet("DCF", "Target DCF valuation", "FCF = EBITDA − taxes on EBIT − Capex − investment in NWC.")
    r = pb.subtitle(ws, 3, "Free cash flow and Target net income forecast")
    r0 = r
    r = pb.table(ws, r, x["dcf_proj"])
    fcf_row = r0 + 1 + _row_of(x["dcf_proj"], "Free cash flow")
    pv_row = r0 + 1 + _row_of(x["dcf_proj"], "PV of FCF")
    r = pb.subtitle(ws, r, "Enterprise value to equity value bridge")
    r = pb.table(ws, r, x["dcf_bridge"])
    r = pb.subtitle(ws, r, "Sensitivity: intrinsic value per share (rows: WACC, columns: g)")
    pb.grid(ws, r, x["dcf_sens"], "WACC \\ g", pb.f_hdr_pct, "pct", "m2")
    ch = wb.add_chart({"type": "column"})
    n = DCF_YEARS
    ch.add_series({"name": "FCF", "categories": ["DCF", r0, 1, r0, n], "values": ["DCF", fcf_row, 1, fcf_row, n],
                   "fill": {"color": NAVY}})
    ch.add_series({"name": "PV of FCF", "categories": ["DCF", r0, 1, r0, n], "values": ["DCF", pv_row, 1, pv_row, n],
                   "fill": {"color": GREY}})
    ch.set_title({"name": "Projected free cash flow (M)"})
    ch.set_size({"width": 560, "height": 300})
    ws.insert_chart(3, 8, ch)

    # --- Relative valuation --------------------------------------------------------------
    ws = pb.sheet("Valuation", "Relative valuation and football field",
                  "Implied value per share = (multiple × Target LTM metric − net debt) / shares.")
    r = pb.subtitle(ws, 3, "Football field (value per Target share)")
    f0 = r
    r = pb.frame(ws, r, x["football"], {"Low": "m2", "Mid": "m2", "High": "m2"})
    r = pb.subtitle(ws, r, "Peer multiples (interquartile range)")
    r = pb.table(ws, r, x["multiples"])
    r = pb.table(ws, r, x["target_multiples"])
    r = pb.subtitle(ws, r, "Trading comparables")
    r = pb.frame(ws, r, x["comps"], {"EV/EBITDA": "x", "EV/Revenue": "x"})
    if not x["precedents"].empty:
        r = pb.subtitle(ws, r, "Precedent transactions")
        pb.frame(ws, r, x["precedents"], {"EV/EBITDA": "x", "EV/Revenue": "x", "Year": "txt"})
    n_ff = len(x["football"])
    if n_ff:
        ch = wb.add_chart({"type": "bar", "subtype": "stacked"})
        cats = ["Valuation", f0 + 1, 0, f0 + n_ff, 0]
        ch.add_series({"categories": cats, "values": ["Valuation", f0 + 1, 1, f0 + n_ff, 1],
                       "fill": {"none": True}, "border": {"none": True}})
        ws.write(f0, 6, "Range", pb.f_hdr)
        for i in range(n_ff):
            ws.write_formula(f0 + 1 + i, 6, f"=D{f0 + 2 + i}-B{f0 + 2 + i}", pb.f_num["m2"])
        ch.add_series({"name": "Range", "categories": cats, "values": ["Valuation", f0 + 1, 6, f0 + n_ff, 6],
                       "fill": {"color": NAVY}})
        ch.set_title({"name": "Football field (per share)"})
        ch.set_legend({"none": True})
        ch.set_y_axis({"reverse": True})
        ch.set_size({"width": 620, "height": 80 + 45 * n_ff})
        ws.insert_chart(3, 8, ch)

    # --- Capital structure ---------------------------------------------------------------
    ws = pb.sheet("Capital Structure", "Capital structure and leverage risk",
                  "Cash uses are funded with balance sheet cash (at an opportunity cost) and two debt tranches.")
    r = pb.subtitle(ws, 3, "Funding of the cash component")
    r = pb.frame(ws, r, x["tranches"], {"Amount (M)": "m1", "% of cash": "pct", "Rate / cost": "pct",
                                        "Annual cost (M)": "m1"})
    r = pb.subtitle(ws, r, "Sources & uses")
    r = pb.frame(ws, r, x["sources_uses"], {"Amount (M)": "m1", "% of total": "pct"})
    r = pb.subtitle(ws, r, "Debt schedule and financing charge")
    r = pb.table(ws, r, x["debt_schedule"])
    r = pb.subtitle(ws, r, "Credit metrics")
    pb.table(ws, r, x["credit"])

    # --- Summary -------------------------------------------------------------------------
    ws = pb.sheet("Summary", f"Transaction summary ({year})",
                  "Same base as Sensitivity and Monte Carlo: phased synergies and DCF-derived Target net income.")
    r = pb.subtitle(ws, 3, "Deal metrics")
    r = pb.table(ws, r, x["summary"])
    r = pb.subtitle(ws, r, "EPS bridge (standalone to pro forma)")
    r = pb.table(ws, r, x["waterfall"])
    r = pb.subtitle(ws, r, "Purchase price allocation")
    r = pb.table(ws, r, x["ppa"])
    r = pb.subtitle(ws, r, "Contribution vs. pro-forma ownership")
    pb.table(ws, r, x["contribution"])

    # --- Sensitivity ---------------------------------------------------------------------
    ws = pb.sheet("Sensitivity", "Projections and sensitivity",
                  f"Grid: {year} accretion/dilution (green = accretive, red = dilutive).")
    r = pb.subtitle(ws, 3, "Three-year projection")
    r = pb.table(ws, r, x["projection"])
    r = pb.subtitle(ws, r, f"Grid ({year}): rows = premium over base price, columns = run-rate synergies (M)")
    heat = x["heat"]
    last = pb.grid(ws, r, heat, "Premium \\ Synergies (M)", pb.f_hdr_num, "pct", "pct_s")
    ws.conditional_format(r + 1, 1, last, heat.shape[1], {
        "type": "3_color_scale", "min_color": RED, "mid_color": "#ffffff", "max_color": GREEN,
        "mid_type": "num", "mid_value": 0,
    })

    # --- Monte Carlo ---------------------------------------------------------------------
    ws = pb.sheet("Monte Carlo", "Monte Carlo risk analysis",
                  f"{N_SIM:,} draws ({year}): synergies, Target earnings, rate shock and integration overrun.")
    r = pb.subtitle(ws, 3, "Parameters and key result")
    r = pb.table(ws, r, x["mc_params"])
    r = pb.subtitle(ws, r, "Statistics")
    r = pb.frame(ws, r, x["mc_stats"], {"Pro-forma EPS": "eps", "Accretion / (dilution) %": "pct_s"})
    r = pb.subtitle(ws, r, "Pro-forma EPS distribution (histogram)")
    h0 = r
    r = pb.frame(ws, r, x["mc_hist"], {"Pro-forma EPS (bin mid)": "eps", "Frequency": "m1"})
    r = pb.subtitle(ws, r, "EPS tornado (±1 std. dev., one driver at a time)")
    pb.frame(ws, r, x["mc_tornado"], {"1 std. dev.": "m2", "EPS low": "eps", "EPS high": "eps"})
    ch = wb.add_chart({"type": "column"})
    last = h0 + len(x["mc_hist"])
    ch.add_series({"name": "Frequency", "categories": ["Monte Carlo", h0 + 1, 0, last, 0],
                   "values": ["Monte Carlo", h0 + 1, 1, last, 1], "fill": {"color": NAVY}, "gap": 20})
    ch.set_title({"name": "Pro-forma EPS distribution"})
    ch.set_legend({"none": True})
    ch.set_size({"width": 560, "height": 300})
    ws.insert_chart(3, 4, ch)
    ws.write(3, 12, "Individual draws", pb.f_sub)
    pb.frame(ws, 4, x["mc_sim"], {"Simulated synergies (M)": "m2", "Target net income (M)": "m2",
                                  "Rate shock": "pct", "Integration costs (M)": "m2", "Pro-forma EPS": "eps"}, col=12)
    ws.set_column(12, 16, 22)

    return pb.close()
