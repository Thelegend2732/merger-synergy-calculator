"""
exporter.py — Exportación del Pitchbook a Excel
================================================
Capa de EXPORTACIÓN: toma las tablas ya calculadas (DataFrames) y las escribe en un libro de
Excel en memoria (io.BytesIO) con xlsxwriter. No importa Streamlit ni recalcula nada del modelo.

Uso:
    from exporter import XLSX_AVAILABLE, build_pitchbook
    data: bytes = build_pitchbook(tables)      # `tables`: ver claves en build_pitchbook

Es la operación más pesada de la app (escribe además las 5.000 simulaciones Montecarlo),
por eso la UI solo la invoca cuando el usuario pide explícitamente preparar el archivo.
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd

from engine import DCF_YEARS, GREEN, GREY, N_SIM, NAVY, RED

try:
    import xlsxwriter

    XLSX_AVAILABLE = True
except ImportError:  # la app sigue funcionando; solo se desactiva la exportación
    xlsxwriter = None
    XLSX_AVAILABLE = False

# Formatos numéricos de Excel por clave (equivalentes a engine.FMT_PY)
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
    """Wrapper de xlsxwriter que escribe en memoria (io.BytesIO) con formato homogéneo."""

    def __init__(self):
        if not XLSX_AVAILABLE:
            raise ImportError("Falta la librería `xlsxwriter`: instálala con `pip install xlsxwriter`.")
        self.buf = io.BytesIO()
        self.wb = xlsxwriter.Workbook(self.buf, {"in_memory": True})
        base = {"font_name": "Arial", "font_size": 10}
        self.f_title = self.wb.add_format({**base, "bold": True, "font_size": 14, "font_color": NAVY})
        self.f_sub = self.wb.add_format({**base, "bold": True, "font_color": NAVY, "bottom": 1})
        self.f_note = self.wb.add_format({**base, "italic": True, "font_color": GREY})
        self.f_hdr = self.wb.add_format({**base, "bold": True, "font_color": "#ffffff", "bg_color": NAVY,
                                         "border": 1, "align": "center", "valign": "vcenter", "text_wrap": True})
        self.f_lbl = self.wb.add_format({**base, "border": 1})
        self.f_txt = self.wb.add_format({**base, "border": 1, "align": "right"})
        self.f_num = {k: self.wb.add_format({**base, "border": 1, "num_format": v}) for k, v in FMT_XL.items()}

    def sheet(self, name: str, title: str, note: str = ""):
        ws = self.wb.add_worksheet(name)
        ws.hide_gridlines(2)
        ws.set_column(0, 0, 40)
        ws.set_column(1, 16, 16)
        ws.write(0, 0, title, self.f_title)
        if note:
            ws.write(1, 0, note, self.f_note)
        return ws

    def subtitle(self, ws, row: int, text: str) -> int:
        ws.write(row, 0, text, self.f_sub)
        return row + 1

    def _cell(self, ws, r: int, c: int, v, key: str | None):
        if isinstance(v, str):
            ws.write_string(r, c, v, self.f_txt if c else self.f_lbl)
        elif v is None or pd.isna(v) or not np.isfinite(v):
            ws.write_string(r, c, "n/a", self.f_txt)
        else:
            ws.write_number(r, c, float(v), self.f_num.get(key, self.f_num["m2"]))

    def table(self, ws, row: int, df: pd.DataFrame) -> int:
        """Escribe una tabla de make_table (formato por fila). Devuelve la siguiente fila libre."""
        cols = list(df.columns[:-1])
        for j, name in enumerate(cols):
            ws.write(row, j, name, self.f_hdr)
        for i in range(len(df)):
            key = df.iat[i, len(df.columns) - 1]
            ws.write_string(row + 1 + i, 0, str(df.iat[i, 0]), self.f_lbl)
            for j in range(1, len(cols)):
                self._cell(ws, row + 1 + i, j, df.iat[i, j], key)
        return row + len(df) + 2

    def frame(self, ws, row: int, df: pd.DataFrame, formats: dict | None = None, col: int = 0) -> int:
        """Escribe un DataFrame con formato por columna (formats: {columna: clave})."""
        formats = formats or {}
        for j, name in enumerate(df.columns):
            ws.write(row, col + j, str(name), self.f_hdr)
        for i in range(len(df)):
            for j, name in enumerate(df.columns):
                v = df.iat[i, j]
                if not isinstance(v, str) and (v is None or pd.isna(v)):
                    ws.write_string(row + 1 + i, col + j, "–", self.f_txt)
                else:
                    self._cell(ws, row + 1 + i, col + j, v, formats.get(name))
        return row + len(df) + 2

    def close(self) -> bytes:
        self.wb.close()
        return self.buf.getvalue()


def build_pitchbook(x: dict) -> bytes:
    """
    Genera el Excel completo y devuelve sus bytes.
    Claves de `x`: year_label, assumptions, dcf_proj, dcf_bridge, dcf_sens, tranches, sources_uses,
    credit, summary, waterfall, projection, heat, mc_params, mc_stats, mc_hist, mc_sim.
    """
    pb = Pitchbook()
    wb = pb.wb
    year = x["year_label"]

    # --- Supuestos -----------------------------------------------------------------------
    ws = pb.sheet("Supuestos", "Supuestos del modelo", "Importes en millones, salvo precios y EPS.")
    pb.table(ws, 3, x["assumptions"])

    # --- DCF -----------------------------------------------------------------------------
    ws = pb.sheet("DCF", "Valoración DCF del Target", "FCF = EBITDA - impuestos s/ EBIT - Capex - inversión en NWC.")
    r = pb.subtitle(ws, 3, "Proyección de Free Cash Flow y beneficio neto del Target")
    r0 = r
    r = pb.table(ws, r, x["dcf_proj"])
    fcf_row = r0 + 1 + int(x["dcf_proj"].index[x["dcf_proj"].iloc[:, 0] == "Free Cash Flow"][0])
    pv_row = r0 + 1 + int(x["dcf_proj"].index[x["dcf_proj"].iloc[:, 0] == "PV del FCF"][0])
    r = pb.subtitle(ws, r, "Puente Enterprise Value -> Equity Value")
    r = pb.table(ws, r, x["dcf_bridge"])
    r = pb.subtitle(ws, r, "Sensibilidad: valor intrínseco por acción (filas: WACC, columnas: g)")
    sens = x["dcf_sens"]
    ws.write(r, 0, "WACC \\ g", pb.f_hdr)
    for j, gval in enumerate(sens.columns):
        ws.write_number(r, 1 + j, float(gval), wb.add_format({"bold": True, "font_color": "#ffffff", "bg_color": NAVY,
                                                               "border": 1, "align": "center", "num_format": "0.0%"}))
    for i, wval in enumerate(sens.index):
        ws.write_number(r + 1 + i, 0, float(wval), pb.f_num["pct"])
        for j in range(sens.shape[1]):
            pb._cell(ws, r + 1 + i, 1 + j, sens.iat[i, j], "m2")
    ch = wb.add_chart({"type": "column"})
    n = DCF_YEARS
    ch.add_series({"name": "FCF", "categories": ["DCF", r0, 1, r0, n], "values": ["DCF", fcf_row, 1, fcf_row, n],
                   "fill": {"color": NAVY}})
    ch.add_series({"name": "PV del FCF", "categories": ["DCF", r0, 1, r0, n], "values": ["DCF", pv_row, 1, pv_row, n],
                   "fill": {"color": GREY}})
    ch.set_title({"name": "Free Cash Flow proyectado (M)"})
    ch.set_size({"width": 560, "height": 300})
    ws.insert_chart(3, 8, ch)

    # --- Estructura de Capital -----------------------------------------------------------
    ws = pb.sheet("Estructura de Capital", "Estructura de capital y riesgo de apalancamiento",
                  "La parte en efectivo se financia con caja propia (con coste de oportunidad) y dos tramos de deuda.")
    r = pb.subtitle(ws, 3, "Fuentes de financiación del efectivo")
    r = pb.frame(ws, r, x["tranches"], {"Importe (M)": "m1", "% del efectivo": "pct", "Tipo / coste": "pct",
                                        "Coste anual (M)": "m1"})
    r = pb.subtitle(ws, r, "Sources & Uses")
    r = pb.frame(ws, r, x["sources_uses"], {"Importe (M)": "m1", "% del total": "pct"})
    r = pb.subtitle(ws, r, "Métricas de crédito")
    pb.table(ws, r, x["credit"])

    # --- Resumen -------------------------------------------------------------------------
    ws = pb.sheet("Resumen", f"Resumen de la transacción ({year})",
                  "Misma base que Sensibilidad y Montecarlo: sinergias faseadas y beneficio del Target derivado del DCF.")
    r = pb.subtitle(ws, 3, "Métricas de la operación")
    r = pb.table(ws, r, x["summary"])
    r = pb.subtitle(ws, r, "Puente del EPS (Standalone -> Pro-Forma)")
    pb.table(ws, r, x["waterfall"])

    # --- Sensibilidad --------------------------------------------------------------------
    ws = pb.sheet("Sensibilidad", "Proyecciones y matriz de sensibilidad",
                  f"Matriz: accretion/dilution del {year} (verde = accretive, rojo = dilutive).")
    r = pb.subtitle(ws, 3, "Proyección a 3 años")
    r = pb.table(ws, r, x["projection"])
    r = pb.subtitle(ws, r, f"Matriz ({year}): filas = prima sobre precio base, columnas = sinergias totales run-rate (M)")
    heat = x["heat"]
    ws.write(r, 0, "Prima \\ Sinergias (M)", pb.f_hdr)
    hdr_num = wb.add_format({"bold": True, "font_color": "#ffffff", "bg_color": NAVY, "border": 1,
                             "align": "center", "num_format": "#,##0.0"})
    for j, sval in enumerate(heat.columns):
        ws.write_number(r, 1 + j, float(sval), hdr_num)
    for i, pval in enumerate(heat.index):
        ws.write_number(r + 1 + i, 0, float(pval), pb.f_num["pct"])
        for j in range(heat.shape[1]):
            pb._cell(ws, r + 1 + i, 1 + j, heat.iat[i, j], "pct_s")
    ws.conditional_format(r + 1, 1, r + heat.shape[0], heat.shape[1], {
        "type": "3_color_scale", "min_color": RED, "mid_color": "#ffffff", "max_color": GREEN,
        "mid_type": "num", "mid_value": 0,
    })

    # --- Montecarlo ----------------------------------------------------------------------
    ws = pb.sheet("Montecarlo", "Análisis de riesgo Montecarlo",
                  f"{N_SIM:,} iteraciones con distribución normal sobre las sinergias capturadas ({year}).")
    r = pb.subtitle(ws, 3, "Parámetros y resultado clave")
    r = pb.table(ws, r, x["mc_params"])
    r = pb.subtitle(ws, r, "Estadísticos")
    r = pb.frame(ws, r, x["mc_stats"], {"EPS Pro-Forma": "eps", "Accretion / Dilution (%)": "pct_s"})
    r = pb.subtitle(ws, r, "Distribución del EPS pro-forma (histograma)")
    h0 = r
    r = pb.frame(ws, r, x["mc_hist"], {"EPS pro-forma (punto medio)": "eps", "Frecuencia": "m1"})
    ch = wb.add_chart({"type": "column"})
    last = h0 + len(x["mc_hist"])
    ch.add_series({"name": "Frecuencia", "categories": ["Montecarlo", h0 + 1, 0, last, 0],
                   "values": ["Montecarlo", h0 + 1, 1, last, 1], "fill": {"color": NAVY}, "gap": 20})
    ch.set_title({"name": "Distribución del EPS pro-forma"})
    ch.set_legend({"none": True})
    ch.set_size({"width": 560, "height": 300})
    ws.insert_chart(3, 4, ch)
    ws.write(3, 12, "Simulaciones individuales", pb.f_sub)
    pb.frame(ws, 4, x["mc_sim"], {"Sinergias simuladas (M)": "m2", "EPS pro-forma": "eps"}, col=12)
    ws.set_column(12, 14, 22)

    return pb.close()