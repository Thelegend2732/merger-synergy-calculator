"""
app.py — Interfaz Streamlit del Merger Synergy Calculator (capa VISTA/CONTROLADOR)
===================================================================================
Ejecutar con:  streamlit run app.py
Dependencias:  pip install streamlit pandas numpy plotly xlsxwriter
Archivos:      app.py (UI) · engine.py (motor financiero puro) · exporter.py (Excel)
               .streamlit/config.toml (tema visual nativo)

Diseño: sin CSS inyectado. Los colores los gestiona el tema de Streamlit (config.toml) y el layout
se construye solo con componentes nativos:
  - Cada pestaña abre con un panel de métricas clave (dashboard) en un contenedor con borde.
  - Inputs, tablas y gráficos van en tarjetas (st.container(border=True)).
  - Columnas asimétricas ([2, 1], [3, 2]...) y separadores (st.divider) para dar aire.
  - Gráficos Plotly con fondo transparente: se funden con el fondo del tema.

Rendimiento:
  - st.cache_data en los cálculos pesados (matriz de sensibilidad, DCF WACC×g, Montecarlo).
  - El Excel NO se genera en cada rerun: el botón «Preparar Pitchbook» lo construye bajo demanda
    y lo guarda en st.session_state; el botón de descarga solo sirve esos bytes ya preparados.

Flujo de datos (fuente única de verdad):
  DCF -> valor por acción -> precio base del Target -> Offer Price
  DCF -> beneficio neto del Target por año -> EPS
  Estructura de capital (Caja / Senior / Mezzanine) -> intereses + coste de oportunidad de la caja
  Faseo + año de análisis (sidebar) -> misma base para Resumen, Sensibilidad y Montecarlo
"""
from __future__ import annotations

import hashlib
import inspect
import json
from contextlib import contextmanager
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engine import (
    AMBER, GREEN, GREY, NAVY, RED,
    DCF_YEARS, LEVERAGE_LIMIT, LEVERAGE_WARN, MAX_M, MAX_PX, MAX_SH, MAX_SYN, N_SIM, STAT_LABELS, YEARS,
    breakeven_synergies, build_deal, dcf_sensitivity, dcf_valuation, display_table, fmt_value, leverage_metrics,
    make_table, max_premium_eps_neutral, ownership_contribution, project_years, require, run_montecarlo,
    run_rate_synergies, safe_div, sensitivity_matrix,
)
from exporter import XLSX_AVAILABLE, build_pitchbook

st.set_page_config(page_title="Merger Synergy Calculator", page_icon=None, layout="wide")


# ---------------------------------------------------------------------------
# 0. Compatibilidad de versiones y utilidades de UI
# ---------------------------------------------------------------------------
def _stretch(fn) -> dict:
    """
    Ancho completo según versión. Se decide función a función: no todas incorporaron
    width="stretch" a la vez (p. ej. en 1.50 download_button sí y plotly_chart no).
    """
    has_width = "width" in inspect.signature(fn).parameters
    return {"width": "stretch"} if has_width and "stretch" in (fn.__doc__ or "") else {"use_container_width": True}


ST_PLOTLY = _stretch(st.plotly_chart)
ST_DF = _stretch(st.dataframe)
ST_DL = _stretch(st.download_button)
ST_BTN = _stretch(st.button)
# Streamlit >= 1.43: la descarga no provoca un rerun de la app (en versiones antiguas se omite)
ST_DL_NO_RERUN = {"on_click": "ignore"} if "ignore" in (st.download_button.__doc__ or "") else {}
# st.container(border=...) existe desde Streamlit 1.29
HAS_BORDER = "border" in inspect.signature(st.container).parameters

HEAT_COLORSCALE = [[0.0, RED], [0.5, "#ffffff"], [1.0, GREEN]]
BLUE_SCALE = [[0.0, "#ffffff"], [1.0, NAVY]]
GRID = "rgba(31, 45, 74, 0.08)"      # rejilla tenue, legible sobre cualquier fondo claro
PB_KEY = "pitchbook"                 # clave de st.session_state donde vive el Excel ya preparado


def card(parent=None):
    """Tarjeta nativa: contenedor con borde (sin borde en versiones < 1.29)."""
    target = st if parent is None else parent
    return target.container(border=True) if HAS_BORDER else target.container()


def card_title(text: str, caption: str | None = None) -> None:
    """Cabecera compacta dentro de una tarjeta."""
    st.markdown(f"**{text}**")
    if caption:
        st.caption(caption)


def gap() -> None:
    """Respiración vertical entre bloques."""
    st.write("")


def style_fig(fig: go.Figure, title: str, height: int = 440) -> go.Figure:
    """Estilo homogéneo: fondo transparente para fundirse con la tarjeta, rejilla tenue, título a la izquierda."""
    fig.update_layout(
        title=dict(text=title, font=dict(size=15, color=NAVY), x=0, xanchor="left"),
        template="plotly_white",
        height=height,
        margin=dict(t=56, b=40, l=50, r=20),
        font=dict(family="sans-serif", size=12),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID)
    return fig


def show_chart(fig: go.Figure) -> None:
    st.plotly_chart(fig, **ST_PLOTLY)


def show_table(df: pd.DataFrame) -> None:
    st.dataframe(display_table(df), hide_index=True, **ST_DF)


@contextmanager
def guarded(container, name: str):
    """
    Ejecuta el bloque dentro de `container` aislando los fallos: si algo revienta, se muestra
    un error en esa pestaña y el resto de la app (y el botón de exportación) sigue operativo.
    Las excepciones de control de Streamlit (st.stop / rerun) no son `Exception` y pasan de largo.
    """
    with container:
        try:
            yield
        except Exception as exc:  # noqa: BLE001
            st.error(f"Error en «{name}»: {type(exc).__name__}: {exc}. "
                     "Revisa los inputs; el resto de pestañas sigue operativo.")


# ---------------------------------------------------------------------------
# 1. Cálculos pesados con caché (solo se recalculan si cambian sus inputs)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def cached_dcf_sensitivity(dcf_inputs: dict) -> pd.DataFrame:
    """Rejilla WACC × g del DCF (25 valoraciones)."""
    return dcf_sensitivity(dcf_inputs)


@st.cache_data(show_spinner=False)
def cached_sensitivity_matrix(p: dict, base_price: float, premium: float, year_idx: int) -> dict:
    """Matriz de accretion/dilution prima × sinergias (63 escenarios)."""
    return sensitivity_matrix(p, base_price, premium, year_idx)


@st.cache_data(show_spinner=False)
def cached_montecarlo(p: dict, deal: dict, year_idx: int, vol: float, seed: int) -> dict:
    """Simulación Montecarlo (5.000 iteraciones). La caché se invalida si cambia cualquier input del modelo."""
    return run_montecarlo(p, deal, year_idx, vol, seed, N_SIM)


# ---------------------------------------------------------------------------
# 2. Cabecera y sidebar (inputs globales)
# ---------------------------------------------------------------------------
st.title("Merger Synergy Calculator")
st.caption("Valoración DCF, estructura de capital y accretion/dilution del EPS "
           "(importes en millones, salvo precios y EPS).")

sb = st.sidebar
export_box = card(sb)   # se rellena al final del script, cuando todas las tablas existen
sb.divider()
sb.header("Parámetros de la operación")

with card(sb):
    st.markdown("**Adquirente (Acquirer)**")
    acq_ni = st.number_input("Beneficio Neto (M)", value=500.0, min_value=-MAX_M, max_value=MAX_M, step=10.0,
                             key="acq_ni")
    acq_sh = st.number_input("Acciones en circulación (M)", value=200.0, min_value=0.01, max_value=MAX_SH, step=1.0,
                             key="acq_sh")
    acq_px = st.number_input("Precio por acción actual", value=50.0, min_value=0.01, max_value=MAX_PX, step=0.5,
                             key="acq_px")
    acq_ebitda = st.number_input("EBITDA (M)", value=900.0, min_value=-MAX_M, max_value=MAX_M, step=10.0,
                                 key="acq_ebitda")
    acq_netdebt = st.number_input("Deuda neta existente (M)", value=1200.0, min_value=-MAX_M, max_value=MAX_M,
                                  step=50.0, key="acq_netdebt")
    acq_cash = st.number_input("Caja disponible para la operación (M)", value=600.0, min_value=0.0, max_value=MAX_M,
                               step=50.0, key="acq_cash",
                               help="Límite de la caja propia que puede destinarse a pagar el efectivo de la operación.")

with card(sb):
    st.markdown("**Objetivo (Target): datos de mercado**")
    tgt_sh = st.number_input("Acciones en circulación (M)", value=80.0, min_value=0.01, max_value=MAX_SH, step=1.0,
                             key="tgt_sh")
    tgt_px = st.number_input("Precio por acción actual", value=20.0, min_value=0.01, max_value=MAX_PX, step=0.5,
                             key="tgt_px")
    tgt_book = st.number_input("Patrimonio neto contable (M)", value=600.0, min_value=-MAX_M, max_value=MAX_M,
                               step=10.0, key="tgt_book",
                               help="Valor en libros del equity del Target: base del Purchase Price Allocation.")
    st.caption("El beneficio neto del Target se deriva del DCF (pestaña Valoración DCF).")

with card(sb):
    st.markdown("**Estructura de la contraprestación**")
    price_basis = st.radio("Base del precio Target", ["Valor intrínseco (DCF)", "Precio de mercado"], index=0,
                           help="Con DCF, el Equity Value de la valoración alimenta el precio sobre el que se aplica la prima.")
    premium = st.slider("Prima sobre el precio base (%)", 0.0, 100.0, 30.0, 1.0) / 100
    cash_pct = st.slider("Pago en efectivo (Cash %)", 0, 100, 50, 5)
    st.caption(f"Pago en acciones (Stock %): {100 - cash_pct}%")
    tax = st.number_input("Tasa impositiva corporativa (%)", value=25.0, min_value=0.0, max_value=100.0,
                          step=1.0) / 100

with card(sb):
    st.markdown("**Sinergias (run-rate, pre-tax)**")
    cost_syn = st.number_input("Sinergias de costes (M)", value=60.0, min_value=0.0, max_value=MAX_SYN, step=5.0,
                               key="cost_syn")
    rev_syn = st.number_input("Sinergias de ingresos (M)", value=20.0, min_value=0.0, max_value=MAX_SYN, step=5.0,
                              key="rev_syn")
    rev_syn_margin = st.number_input("Margen EBITDA de las sinergias de ingresos (%)", value=30.0, min_value=0.0,
                                     max_value=100.0, step=1.0, key="rev_syn_mg",
                                     help="Solo el margen de las ventas adicionales llega al beneficio.") / 100
    integration_costs = st.number_input("Costes de integración, one-time (M)", value=30.0, min_value=0.0,
                                        max_value=MAX_SYN, step=5.0, key="integ")
    total_syn = run_rate_synergies(cost_syn, rev_syn, rev_syn_margin)
    st.caption(f"Sinergias run-rate a nivel EBITDA: {cost_syn:,.1f} + {rev_syn:,.1f} × {rev_syn_margin:.0%} "
               f"= **{total_syn:,.1f} M**")

with card(sb):
    st.markdown("**Purchase Price Allocation (PPA)**")
    ppa_intang_pct = st.slider("% del exceso de precio asignado a intangibles", 0, 100, 30, 5, key="ppa_pct",
                               help="Marcas, clientes, tecnología... Se amortizan; el resto del exceso es goodwill.") / 100
    ppa_life = st.number_input("Vida útil de los intangibles (años)", value=10, min_value=1, max_value=40, step=1,
                               key="ppa_life")

with card(sb):
    st.markdown("**Faseo y año de análisis**")
    st.caption("% de las sinergias run-rate capturado cada año. Resumen, Sensibilidad y Montecarlo leen esta base.")
    phase_pct = [
        st.slider("Año 1 (%)", 0, 100, 50, 5, key="ph1"),
        st.slider("Año 2 (%)", 0, 100, 75, 5, key="ph2"),
        st.slider("Año 3 (%)", 0, 100, 100, 5, key="ph3"),
    ]
    if any(b < a for a, b in zip(phase_pct, phase_pct[1:])):
        st.warning("El % de sinergias capturado debería ser no decreciente a lo largo de los años.")
    year_sel = st.selectbox("Año de análisis (Resumen, Sensibilidad y Montecarlo)", YEARS, index=0)
phases = [v / 100 for v in phase_pct]
yi = YEARS.index(year_sel)

# Parámetros compartidos por todo el motor (las pestañas de DCF y Estructura de Capital los completan)
P = dict(acq_ni=acq_ni, acq_sh=acq_sh, acq_px=acq_px, acq_ebitda=acq_ebitda, acq_netdebt=acq_netdebt,
         acq_cash=acq_cash, tgt_sh=tgt_sh, tgt_px=tgt_px, cash_w=cash_pct / 100, tax=tax,
         total_syn=total_syn, integration=integration_costs, phases=phases,
         tgt_book_equity=tgt_book, ppa_intang_pct=ppa_intang_pct, ppa_life=int(ppa_life))

alerts_box = st.container()   # alertas globales: se rellena al final, visible desde cualquier pestaña
tab_dcf, tab_cap, tab_sum, tab_sens, tab_mc = st.tabs([
    "Valoración DCF", "Estructura de Capital y Riesgo", "Resumen de la Transacción",
    "Proyecciones y Sensibilidad", "Análisis de Riesgo Montecarlo",
])

# ---------------------------------------------------------------------------
# 3.1 Pestaña 1: Valoración DCF
# ---------------------------------------------------------------------------
with guarded(tab_dcf, "Valoración DCF"):
    gap()
    dash_dcf = card()   # dashboard: se rellena tras calcular el DCF, pero se muestra arriba
    gap()

    col_in, col_out = st.columns([2, 1], gap="medium")
    with col_in, card():
        card_title("Supuestos operativos y de valoración", "DCF a 5 años con Terminal Value de Gordon-Shapiro.")
        c1, c2, c3 = st.columns(3)
        rev0 = c1.number_input("Ingresos LTM (M)", value=640.0, min_value=0.0, max_value=MAX_M, step=10.0,
                               key="dcf_rev")
        growth = c1.number_input("Crecimiento anual de ingresos (%)", value=6.0, min_value=-50.0, max_value=100.0,
                                 step=0.5, key="dcf_gr") / 100
        margin = c2.number_input("Margen EBITDA (%)", value=27.0, min_value=0.0, max_value=100.0, step=0.5,
                                 key="dcf_mg") / 100
        da_pct = c2.number_input("D&A (% de ingresos)", value=6.0, min_value=0.0, max_value=100.0, step=0.5,
                                 key="dcf_da") / 100
        capex_pct = c3.number_input("Capex (% de ingresos)", value=7.0, min_value=0.0, max_value=100.0, step=0.5,
                                    key="dcf_cx") / 100
        nwc_pct = c3.number_input("Inversión en NWC (% del Δ ingresos)", value=10.0, min_value=0.0, max_value=100.0,
                                  step=1.0, key="dcf_nwc") / 100
        c4, c5, c6, c7 = st.columns(4)
        wacc = c4.number_input("WACC (%)", value=8.5, min_value=0.5, max_value=30.0, step=0.25, key="dcf_wacc") / 100
        g_perp = c5.number_input("Crecimiento a perpetuidad g (%)", value=2.5, min_value=-2.0, max_value=10.0,
                                 step=0.25, key="dcf_g") / 100
        tgt_netdebt = c6.number_input("Deuda neta del Target (M)", value=100.0, min_value=-MAX_M, max_value=MAX_M,
                                      step=10.0, key="dcf_nd")
        td_rate = c7.number_input("Tipo de interés de su deuda neta (%)", value=5.0, min_value=0.0, max_value=30.0,
                                  step=0.25, key="dcf_td",
                                  help="Se usa para derivar el beneficio neto del Target (EBIT − intereses, tras impuestos).") / 100

    dcf_inputs = dict(rev0=rev0, growth=growth, margin=margin, da_pct=da_pct, capex_pct=capex_pct,
                      nwc_pct=nwc_pct, wacc=wacc, g=g_perp, net_debt=tgt_netdebt, td_rate=td_rate,
                      shares=tgt_sh, tax=tax)
    dcf = dcf_valuation(dcf_inputs)

    # Magnitudes del Target que consumen el resto de pestañas (fuente única: el DCF)
    P["tgt_ebitda"] = rev0 * margin
    P["tgt_netdebt"] = tgt_netdebt
    P["tgt_ni_y"] = [float(v) for v in dcf["ni"][:3]]

    # Precio base que alimenta el resto de la app
    use_dcf = price_basis.startswith("Valor") and dcf["valid"]
    base_price = dcf["price"] if use_dcf else tgt_px
    base_label = "DCF (valor intrínseco)" if use_dcf else "precio de mercado"
    mkt_cap = tgt_px * tgt_sh

    with dash_dcf:
        card_title("Valoración del Target")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Enterprise Value", fmt_value(dcf["ev"], "m1"))
        k2.metric("Equity Value (DCF)", fmt_value(dcf["equity"], "m1"),
                  delta=fmt_value(safe_div(dcf["equity"], mkt_cap) - 1, "pct_s") + " vs. mercado"
                  if dcf["valid"] else None)
        k3.metric("Valor intrínseco por acción", fmt_value(dcf["price"], "m2"))
        k4.metric("Precio de mercado por acción", fmt_value(tgt_px, "m2"))
        if not dcf["valid"]:
            st.error(f"DCF no válido: {dcf['reason']} Se usa el precio de mercado como base del Target.")

    with col_out, card():
        card_title("Precio base de la operación")
        st.markdown(f"### {base_price:,.2f}")
        st.caption(f"Por acción, según {base_label}. Sobre él se aplica la prima del {premium:.0%}.")
        st.divider()
        card_title("Beneficio neto del Target (base del EPS)")
        n1, n2, n3 = st.columns(3)
        for col, yr, val in zip((n1, n2, n3), YEARS, P["tgt_ni_y"]):
            col.caption(yr)
            col.markdown(f"**{val:,.1f}**")
        st.caption("Millones. Derivado del DCF: (EBIT − intereses de su deuda neta) × (1 − t).")

    # --- Tablas ---
    yrs = [f"Año {i}" for i in dcf["years"]]
    dcf_proj = make_table("Concepto (M)", yrs, [
        ("Ingresos", dcf["rev"], "m1"),
        ("Crecimiento de ingresos", dcf["growth_row"], "pct"),
        ("EBITDA", dcf["ebitda"], "m1"),
        ("Memo: D&A", dcf["da"], "m1"),
        ("Memo: EBIT", dcf["ebit"], "m1"),
        ("(−) Impuestos s/ EBIT", -dcf["taxes"], "m1"),
        ("(−) Capex", -dcf["capex"], "m1"),
        ("(−) Inversión en NWC", -dcf["d_nwc"], "m1"),
        ("Free Cash Flow", dcf["fcf"], "m1"),
        ("Factor de descuento", dcf["disc"], "eps"),
        ("PV del FCF", dcf["pv_fcf"], "m1"),
        ("Memo: intereses s/ deuda neta del Target", np.full(DCF_YEARS, dcf["interest_td"]), "m1"),
        ("Memo: beneficio neto del Target (base del EPS)", dcf["ni"], "m1"),
    ])
    ebitda_ltm = P["tgt_ebitda"]
    dcf_bridge = make_table("Puente de valoración", ["Valor"], [
        ("Suma PV de los FCF (5 años)", dcf["sum_pv"], "m1"),
        ("Terminal Value (Año 5)", dcf["tv"], "m1"),
        ("PV del Terminal Value", dcf["pv_tv"], "m1"),
        ("Enterprise Value", dcf["ev"], "m1"),
        ("(−) Deuda neta del Target", -tgt_netdebt, "m1"),
        ("Equity Value", dcf["equity"], "m1"),
        ("Acciones del Target (M)", tgt_sh, "m2"),
        ("Valor intrínseco por acción", dcf["price"], "m2"),
        ("Precio de mercado por acción", tgt_px, "m2"),
        ("Prima / (descuento) del DCF vs. mercado", safe_div(dcf["price"], tgt_px) - 1, "pct_s"),
        ("Terminal Value como % del EV", safe_div(dcf["pv_tv"], dcf["ev"]), "pct"),
        ("EV / EBITDA LTM implícito", safe_div(dcf["ev"], ebitda_ltm), "x"),
        ("TV / EBITDA Año 5 implícito", safe_div(dcf["tv"], dcf["ebitda"][-1]), "x"),
    ])

    st.divider()
    left, right = st.columns([3, 2], gap="medium")
    with left, card():
        card_title("Proyección de Free Cash Flow y beneficio neto")
        show_table(dcf_proj)
    with right, card():
        card_title("Puente EV a Equity Value")
        show_table(dcf_bridge)

    # --- Gráficos ---
    gap()
    g1, g2 = st.columns([3, 2], gap="medium")
    fcf_fig = go.Figure()
    fcf_fig.add_trace(go.Bar(x=yrs, y=dcf["fcf"], name="FCF", marker_color=NAVY,
                             text=[f"{v:,.1f}" for v in dcf["fcf"]], textposition="outside"))
    fcf_fig.add_trace(go.Bar(x=yrs, y=dcf["pv_fcf"], name="PV del FCF", marker_color=GREY))
    fcf_fig.update_layout(barmode="group", yaxis_title="M", legend=dict(orientation="h", y=1.12, x=1, xanchor="right"))
    style_fig(fcf_fig, "Free Cash Flow proyectado", height=400)
    with g1, card():
        show_chart(fcf_fig)

    if dcf["valid"]:
        ev_fig = go.Figure(go.Waterfall(
            x=["PV FCF", "PV TV", "EV", "(−) Deuda neta", "Equity"],
            y=[dcf["sum_pv"], dcf["pv_tv"], dcf["ev"], -tgt_netdebt, dcf["equity"]],
            measure=["relative", "relative", "total", "relative", "total"],
            text=[f"{v:,.0f}" for v in [dcf["sum_pv"], dcf["pv_tv"], dcf["ev"], -tgt_netdebt, dcf["equity"]]],
            textposition="outside",
            connector={"line": {"color": GREY, "dash": "dot"}},
            increasing={"marker": {"color": GREEN}}, decreasing={"marker": {"color": RED}},
            totals={"marker": {"color": NAVY}},
        ))
        ev_fig.update_layout(showlegend=False, yaxis_title="M")
        style_fig(ev_fig, "De Enterprise Value a Equity Value", height=400)
        with g2, card():
            show_chart(ev_fig)

    st.divider()
    with st.expander("Sensibilidad del valor intrínseco por acción (WACC × g)"):
        dcf_sens = cached_dcf_sensitivity(dcf_inputs)
        sens_fig = go.Figure(go.Heatmap(
            z=dcf_sens.values, x=[f"{v:.1%}" for v in dcf_sens.columns], y=[f"{v:.1%}" for v in dcf_sens.index],
            colorscale=BLUE_SCALE, texttemplate="%{z:,.2f}",
            hovertemplate="g: %{x}<br>WACC: %{y}<br>Valor por acción: %{z:,.2f}<extra></extra>",
            colorbar=dict(title="Por acción"),
        ))
        sens_fig.update_layout(xaxis_title="Crecimiento a perpetuidad (g)", yaxis_title="WACC")
        style_fig(sens_fig, "Valor intrínseco por acción", height=420)
        show_chart(sens_fig)

    with st.expander("Metodología DCF"):
        st.markdown(
            """
- **Ingresos** crecen a tasa constante; **EBITDA** = Ingresos × margen; **EBIT** = EBITDA − D&A.
- **FCF** = EBITDA − impuestos sobre EBIT − Capex − inversión en NWC (% del incremento de ingresos).
- **Terminal Value** (Gordon-Shapiro) = FCF₅ × (1 + g) / (WACC − g), descontado con el factor del Año 5.
- **Enterprise Value** = Σ PV(FCF) + PV(TV); **Equity Value** = EV − deuda neta del Target.
- **Beneficio neto del Target** = (EBIT − intereses sobre su deuda neta) × (1 − t): es el que entra en el EPS
  pro-forma, de modo que cambiar márgenes, crecimiento o Capex altera a la vez el precio y el beneficio.
- Convención de fin de año; sin ajuste de mid-year ni de normalización del FCF terminal.
            """
        )

# ---------------------------------------------------------------------------
# 3.2 Pestaña 2: Estructura de Capital y Riesgo
# ---------------------------------------------------------------------------
with guarded(tab_cap, "Estructura de Capital y Riesgo"):
    gap()
    dash_cap = card()   # dashboard: se rellena cuando la operación está construida
    gap()

    col_in, col_side = st.columns([2, 1], gap="medium")
    with col_in, card():
        card_title("Financiación de la parte en efectivo",
                   "El efectivo se cubre con caja propia y dos tramos de deuda; la parte en acciones, "
                   "con nuevas acciones del Acquirer.")
        a, b = st.columns(2)
        with a:
            cash_share = st.slider("% Caja disponible (sobre el efectivo a pagar)", 0, 100, 30, 5, key="cap_cash")
            senior_share = st.slider("% Deuda Senior", 0, 100, 50, 5, key="cap_sr")
        with b:
            rate_cash = st.number_input("Coste de oportunidad de la caja (%)", value=3.0, min_value=0.0,
                                        max_value=20.0, step=0.25, key="rate_cash",
                                        help="Ingreso financiero perdido (antes de impuestos) por usar caja propia.") / 100
            senior_rate = st.number_input("Tipo de interés Senior (%)", value=5.5, min_value=0.0, max_value=30.0,
                                          step=0.25, key="rate_sr") / 100
            mezz_rate = st.number_input("Tipo de interés Mezzanine (%)", value=10.0, min_value=0.0, max_value=40.0,
                                        step=0.25, key="rate_mz") / 100
        f1, f2, f3 = st.columns(3)
        senior_term = f1.number_input("Plazo de amortización Senior (años)", value=7, min_value=0, max_value=30,
                                      step=1, key="sr_term",
                                      help="Amortización lineal; 0 = bullet. La Mezzanine es siempre bullet.")
        fee_adv = f2.number_input("Comisiones de asesoramiento (% del equity)", value=1.5, min_value=0.0,
                                  max_value=10.0, step=0.25, key="fee_adv",
                                  help="M&A advisory, legal, due diligence: gasto one-time, fuera del EPS recurrente.") / 100
        fee_fin = f3.number_input("Comisiones de financiación (% de la deuda)", value=2.0, min_value=0.0,
                                  max_value=10.0, step=0.25, key="fee_fin",
                                  help="Se capitalizan y se amortizan durante el plazo Senior.") / 100

    # Validación: caja + senior no pueden superar el 100%; el resto es Mezzanine
    raw_total = cash_share + senior_share
    if raw_total > 100:
        scale = 100 / raw_total
        cap_cash, cap_senior = cash_share * scale / 100, senior_share * scale / 100
    else:
        cap_cash, cap_senior = cash_share / 100, senior_share / 100
    cap_mezz = max(0.0, 1.0 - cap_cash - cap_senior)

    P.update(cap_cash=cap_cash, cap_senior=cap_senior, cap_mezz=cap_mezz,
             rate_senior=senior_rate, rate_mezz=mezz_rate, rate_cash=rate_cash,
             senior_term=int(senior_term), fee_adv=fee_adv, fee_fin=fee_fin)

    # La operación base se construye aquí, una vez conocidos el precio base y los tramos
    base_deal = build_deal(P, base_price, premium)

    with col_side, card():
        card_title("Reparto resultante")
        st.metric("% Deuda Subordinada / Mezzanine (resto)", f"{cap_mezz:.0%}")
        st.caption(f"Caja {cap_cash:.0%} · Senior {cap_senior:.0%} · Mezzanine {cap_mezz:.0%}")
        if raw_total > 100:
            st.error(f"Caja ({cash_share}%) + Senior ({senior_share}%) suman {raw_total}%. "
                     "Se reescalan proporcionalmente a 100% (Mezzanine = 0%).")
        if mezz_rate < senior_rate:
            st.warning("El tipo Mezzanine es inferior al Senior: lo habitual es que la deuda subordinada pague más.")
        if base_deal["cash_bs"] > acq_cash + 1e-9:
            st.error(f"La caja propia necesaria ({base_deal['cash_bs']:,.1f} M) supera la caja disponible del "
                     f"Acquirer ({acq_cash:,.1f} M).")
        else:
            st.caption(f"Caja propia utilizada: {base_deal['cash_bs']:,.1f} M de {acq_cash:,.1f} M disponibles "
                       f"({safe_div(base_deal['cash_bs'], acq_cash, 0.0):.0%}).")

    with dash_cap:
        card_title("Financiación de la operación")
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Efectivo necesario (con comisiones)", fmt_value(base_deal["cash"], "m1"))
        k2.metric("Deuda nueva (Senior + Mezz)", fmt_value(base_deal["debt"], "m1"))
        k3.metric("Coste medio de la deuda", fmt_value(base_deal["avg_cost_debt"], "pct"))
        k4.metric("Intereses anuales (deuda)", fmt_value(base_deal["interest"], "m1"))
        k5.metric("Coste oportunidad caja", fmt_value(base_deal["opp_cost"], "m1"),
                  help="Coste de oportunidad anual de la caja propia utilizada (M, antes de impuestos).")

    cash_total = base_deal["cash"]
    tranches = pd.DataFrame({
        "Fuente": ["Caja propia", "Deuda Senior", "Deuda Mezzanine", "Total"],
        "Importe (M)": [base_deal["cash_bs"], base_deal["senior"], base_deal["mezz"], cash_total],
        "% del efectivo": [cap_cash, cap_senior, cap_mezz, cap_cash + cap_senior + cap_mezz],
        "Tipo / coste": [rate_cash, senior_rate, mezz_rate, safe_div(base_deal["fin_cost"], cash_total)],
        "Coste anual (M)": [base_deal["opp_cost"], base_deal["int_senior"], base_deal["int_mezz"],
                            base_deal["fin_cost"]],
    })
    eq = base_deal["equity_value"]
    total_uses = eq + base_deal["adv_fees"] + base_deal["fin_fees"]
    su_rows = [
        ("Fuente", "Caja del balance", base_deal["cash_bs"]),
        ("Fuente", "Deuda Senior", base_deal["senior"]),
        ("Fuente", "Deuda Mezzanine", base_deal["mezz"]),
        ("Fuente", "Nuevas acciones emitidas", base_deal["stock"]),
        ("Fuente", "Total fuentes", base_deal["cash"] + base_deal["stock"]),
        ("Uso", "Compra del equity del Target", eq),
        ("Uso", "Comisiones de asesoramiento", base_deal["adv_fees"]),
        ("Uso", "Comisiones de financiación", base_deal["fin_fees"]),
        ("Uso", "Total usos", total_uses),
    ]
    sources_uses = pd.DataFrame({
        "Tipo": [r[0] for r in su_rows],
        "Concepto": [r[1] for r in su_rows],
        "Importe (M)": [r[2] for r in su_rows],
        "% del total": [safe_div(r[2], total_uses) for r in su_rows],
    })
    debt_schedule = make_table("Calendario de deuda (M)", YEARS, [
        ("Saldo inicial Senior", base_deal["senior_beg"], "m1"),
        ("Amortización Senior", -base_deal["senior_repay"], "m1"),
        ("Saldo Mezzanine (bullet)", np.full(len(YEARS), base_deal["mezz"]), "m1"),
        ("Intereses Senior", base_deal["int_senior_y"], "m1"),
        ("Intereses Mezzanine", base_deal["int_mezz_y"], "m1"),
        ("Coste de oportunidad de la caja", np.full(len(YEARS), base_deal["opp_cost"]), "m1"),
        ("Amortización comisiones de financiación", base_deal["fee_amort_y"], "m1"),
        ("Total cargo financiero pre-tax", base_deal["fin_cost_y"] + base_deal["fee_amort_y"], "m1"),
    ])

    gap()
    t1, t2 = st.columns([1, 1], gap="medium")
    with t1, card():
        card_title("Tramos de financiación")
        # Versión compacta para pantalla (el Excel recibe `tranches` completo)
        st.dataframe(
            tranches.rename(columns={"% del efectivo": "% efectivo", "Tipo / coste": "Coste %",
                                     "Coste anual (M)": "Coste (M)"})
            .style.format({"Importe (M)": "{:,.1f}", "% efectivo": "{:.1%}", "Coste %": "{:.2%}",
                           "Coste (M)": "{:,.1f}"}, na_rep="–"),
            hide_index=True, **ST_DF)
    with t2, card():
        card_title("Sources & Uses")
        st.dataframe(
            sources_uses.drop(columns="Tipo").rename(columns={"% del total": "%"})
            .style.format({"Importe (M)": "{:,.1f}", "%": "{:.0%}"}, na_rep="–"),
            hide_index=True, **ST_DF)
    gap()
    with card():
        card_title("Calendario de deuda y cargo financiero",
                   f"Senior amortizable en {int(senior_term)} años (intereses sobre saldo inicial)"
                   if senior_term else "Senior bullet (sin amortización); comisiones de financiación en el Año 1.")
        show_table(debt_schedule)

    st.divider()
    st.subheader("Riesgo de apalancamiento")
    incl_syn = st.checkbox("Incluir sinergias run-rate en el EBITDA pro-forma", value=False,
                           help="Por defecto se excluyen (criterio conservador de las agencias de rating).")
    lev = leverage_metrics(P, base_deal, total_syn if incl_syn else 0.0)
    lp = lev["lev_pf"]

    with card():
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Deuda Neta / EBITDA Standalone", fmt_value(lev["lev_sa"], "x"))
        delta_lev = lev["lev_pf"] - lev["lev_sa"]
        m2.metric("Deuda Neta / EBITDA Pro-Forma", fmt_value(lev["lev_pf"], "x"),
                  delta=fmt_value(delta_lev, "x") if not pd.isna(delta_lev) else None, delta_color="inverse")
        m3.metric("EBITDA pro-forma (M)", fmt_value(lev["ebitda_pf"], "m1"))
        m4.metric("Cobertura EBITDA / intereses nuevos", fmt_value(lev["coverage"], "x"))

        if pd.isna(lp):
            st.warning("No se puede calcular el apalancamiento: el EBITDA pro-forma no es positivo.")
        elif lp > LEVERAGE_LIMIT:
            st.error(f"Deuda Neta / EBITDA pro-forma de **{lp:.2f}x**, por encima de {LEVERAGE_LIMIT:.1f}x: "
                     "alto riesgo de **rebaja de rating crediticio** y de estrés de apalancamiento "
                     "(covenants, coste de refinanciación). Considera más pago en acciones o una prima menor.")
        elif lp > LEVERAGE_WARN:
            st.warning(f"Deuda Neta / EBITDA pro-forma de **{lp:.2f}x**: zona de vigilancia "
                       f"({LEVERAGE_WARN:.1f}x–{LEVERAGE_LIMIT:.1f}x). Sin estrés inmediato, pero con poco margen.")
        else:
            st.success(f"Deuda Neta / EBITDA pro-forma de **{lp:.2f}x**: apalancamiento holgado "
                       f"(< {LEVERAGE_WARN:.1f}x).")

    lev_fig = go.Figure()
    bar_color = GREY if pd.isna(lp) else (RED if lp > LEVERAGE_LIMIT else AMBER if lp > LEVERAGE_WARN else GREEN)
    lev_vals = [0 if pd.isna(v) else v for v in (lev["lev_sa"], lev["lev_pf"])]
    lev_fig.add_trace(go.Bar(x=["Standalone", "Pro-Forma"], y=lev_vals, marker_color=[GREY, bar_color],
                             text=[fmt_value(v, "x") for v in (lev["lev_sa"], lev["lev_pf"])], textposition="outside"))
    lev_fig.add_hline(y=LEVERAGE_LIMIT, line_dash="dash", line_color=RED,
                      annotation_text=f"Límite {LEVERAGE_LIMIT:.1f}x", annotation_position="top left")
    lev_fig.update_layout(showlegend=False, yaxis_title="Deuda Neta / EBITDA (x)",
                          yaxis_range=[0, max(LEVERAGE_LIMIT * 1.25, max(lev_vals) * 1.2)])
    style_fig(lev_fig, "Apalancamiento: Standalone vs. Pro-Forma", height=420)

    credit = make_table("Métricas de crédito", ["Valor"], [
        ("Deuda neta Acquirer (pre-deal, M)", acq_netdebt, "m1"),
        ("Deuda neta Target (M)", tgt_netdebt, "m1"),
        ("(+) Efectivo desembolsado (caja + deuda nueva, M)", base_deal["cash"], "m1"),
        ("Deuda neta pro-forma (M)", lev["net_debt_pf"], "m1"),
        ("EBITDA Acquirer (M)", acq_ebitda, "m1"),
        ("EBITDA Target LTM (M)", P["tgt_ebitda"], "m1"),
        ("Sinergias incluidas en EBITDA (M)", total_syn if incl_syn else 0.0, "m1"),
        ("EBITDA pro-forma (M)", lev["ebitda_pf"], "m1"),
        ("Deuda Neta / EBITDA Standalone", lev["lev_sa"], "x"),
        ("Deuda Neta / EBITDA Pro-Forma", lev["lev_pf"], "x"),
        ("Límite de apalancamiento", LEVERAGE_LIMIT, "x"),
        ("Cobertura EBITDA / intereses nuevos", lev["coverage"], "x"),
    ])
    gap()
    cl, cr = st.columns([2, 3], gap="medium")
    with cl, card():
        card_title("Métricas de crédito")
        show_table(credit)
    with cr, card():
        show_chart(lev_fig)

    st.divider()
    with st.expander("Notas sobre la estructura de capital"):
        st.markdown(
            """
- El efectivo pagado (caja propia + deuda nueva) **aumenta la deuda neta** en el mismo importe; por eso el reparto
  entre Caja, Senior y Mezzanine modifica el **coste financiero** (y el EPS), pero no el ratio Deuda Neta / EBITDA.
- **Coste medio de la deuda** = (Senior × tipo Senior + Mezzanine × tipo Mezzanine) / deuda total.
- **Coste de oportunidad de la caja** = caja propia usada × rendimiento perdido; se resta del beneficio pro-forma
  tras impuestos, igual que los intereses, de modo que la caja no sale «gratis».
- La caja propia no puede superar la caja disponible del Acquirer (alerta en rojo si se excede).
- **Comisiones**: las de asesoramiento se pagan al cierre y no entran en el EPS recurrente; las de financiación
  (% de la deuda nueva) se capitalizan y se amortizan a lo largo del plazo Senior.
- **Deuda Senior** amortizable linealmente (intereses sobre el saldo inicial de cada año); **Mezzanine** bullet.
  El repago se financia con el cash flow de la combinada, por lo que el ratio Deuda Neta / EBITDA se muestra al cierre.
            """
        )

# ---------------------------------------------------------------------------
# Núcleo del modelo: UNA sola base (sinergias faseadas + beneficio del Target del DCF)
# para Resumen, Sensibilidad y Montecarlo.
# ---------------------------------------------------------------------------
model_ok, model_err = False, ""
try:
    proj = project_years(P, base_deal)   # [(sinergias, integración, beneficio Target, escenario)] Año 1..3
    cur_syn, cur_integ, cur_tni, base = proj[yi]
    model_ok = True
except Exception as exc:  # noqa: BLE001 - una pestaña previa falló: se informa más abajo
    model_err = f"{type(exc).__name__}: {exc}"

# ---------------------------------------------------------------------------
# 3.3 Pestaña 3: Resumen de la Transacción (año de análisis seleccionado)
# ---------------------------------------------------------------------------
with guarded(tab_sum, "Resumen de la Transacción"):
    require(model_ok, "el modelo no pudo calcularse; revisa las pestañas de DCF y Estructura de Capital.")
    label = "ACCRETIVE" if base["accretive"] else "DILUTIVE"
    be = breakeven_synergies(P, base_deal, yi)
    max_prem = max_premium_eps_neutral(P, base_price, yi)
    oc = ownership_contribution(P, base_deal)
    gap()
    with card():
        card_title(f"Impacto en el EPS: {year_sel}",
                   f"{phases[yi]:.0%} de las sinergias run-rate ({cur_syn:,.1f} M), costes de integración "
                   f"{cur_integ:,.1f} M y beneficio del Target derivado del DCF ({cur_tni:,.1f} M). "
                   f"Precio base del Target: {base_label}.")
        c1, c2, c3 = st.columns(3)
        c1.metric("EPS Standalone (Acquirer)", fmt_value(base["sa_eps"], "eps"))
        c2.metric("EPS Pro-Forma", fmt_value(base["pf_eps"], "eps"), delta=fmt_value(base["acc"], "eps_s"),
                  delta_color="normal")
        c3.metric("Accretion / Dilution (%)", fmt_value(base["acc_pct"], "pct_s"), delta=label,
                  delta_color="normal" if base["accretive"] else "inverse")

        if pd.isna(base["acc"]):
            st.warning("No se puede calcular el EPS: revisa que las acciones en circulación sean mayores que cero.")
        elif base["accretive"]:
            st.success(f"La operación es **{label}**: el EPS sube {fmt_value(base['acc'], 'eps_s')} "
                       f"({fmt_value(base['acc_pct'], 'pct_s')}).")
        else:
            st.error(f"La operación es **{label}**: el EPS cae {fmt_value(base['acc'], 'eps_s')} "
                     f"({fmt_value(base['acc_pct'], 'pct_s')}).")

    gap()
    with card():
        card_title("Umbrales de la operación",
                   f"{year_sel}: qué tendría que pasar para que la operación fuera EPS-neutral.")
        b1, b2, b3, b4 = st.columns(4)
        b1.metric("Sinergias breakeven (run-rate)", fmt_value(be["run_rate"], "m1"),
                  delta=(fmt_value(be["cushion"], "m1") + " de colchón") if np.isfinite(be["cushion"]) else None,
                  help="Sinergias run-rate pre-tax mínimas para que el EPS pro-forma iguale al standalone, "
                       "con el faseo del año seleccionado.")
        b2.metric("Prima máxima EPS-neutral", fmt_value(max_prem, "pct"),
                  delta=fmt_value(max_prem - premium, "pct_s") + " vs. prima actual" if np.isfinite(max_prem) else None,
                  help="Prima más alta sobre el precio base que mantiene la operación sin dilución.")
        b3.metric("Propiedad pro-forma: Acquirer", fmt_value(oc["own_acq"], "pct"))
        b4.metric("Propiedad pro-forma: Target", fmt_value(oc["own_tgt"], "pct"))
        if not np.isfinite(max_prem):
            st.caption("La operación es dilutiva incluso sin prima: no existe una prima EPS-neutral.")

    implied_premium = safe_div(base_deal["offer_price"], tgt_px) - 1
    summary = make_table("Métrica", ["Valor"], [
        ("Año de análisis", year_sel, "txt"),
        ("Precio base del Target por acción", base_price, "m2"),
        ("Offer Price por acción", base_deal["offer_price"], "m2"),
        ("Prima implícita vs. precio de mercado", implied_premium, "pct_s"),
        ("Deal Equity Value (M)", base_deal["equity_value"], "m1"),
        ("Enterprise Value implícito (M)", base_deal["equity_value"] + tgt_netdebt, "m1"),
        ("EV / EBITDA LTM implícito", safe_div(base_deal["equity_value"] + tgt_netdebt, P["tgt_ebitda"]), "x"),
        ("Cash Consideration (M)", base_deal["cash_consid"], "m1"),
        ("Stock Consideration (M)", base_deal["stock"], "m1"),
        ("Comisiones de asesoramiento (M)", base_deal["adv_fees"], "m1"),
        ("Comisiones de financiación (M)", base_deal["fin_fees"], "m1"),
        ("Cash Needed total (M)", base_deal["cash"], "m1"),
        ("New Shares Issued (M)", base_deal["new_shares"], "m2"),
        ("Exchange ratio (acciones Acquirer por acción Target)", base_deal["exchange_ratio"], "eps"),
        ("Caja propia utilizada (M)", base_deal["cash_bs"], "m1"),
        ("Deuda Senior (M)", base_deal["senior"], "m1"),
        ("Deuda Mezzanine (M)", base_deal["mezz"], "m1"),
        ("Interest Expense deuda del año (M)", base_deal["interest_y"][yi], "m1"),
        ("Coste de oportunidad de la caja (M)", base_deal["opp_cost"], "m1"),
        ("Amortización comisiones de financiación (M)", base_deal["fee_amort_y"][yi], "m1"),
        ("Amortización intangibles PPA (M)", base_deal["ppa_amort"], "m1"),
        ("% de sinergias capturadas", phases[yi], "pct"),
        ("Sinergias capturadas pre-tax (M)", cur_syn, "m1"),
        ("Costes de integración (M)", cur_integ, "m1"),
        ("Beneficio neto del Target — DCF (M)", cur_tni, "m1"),
        ("Pro-Forma Net Income (M)", base["pf_ni"], "m1"),
        ("Pro-Forma Shares Outstanding (M)", base["pf_shares"], "m2"),
        ("Standalone EPS", base["sa_eps"], "eps"),
        ("Pro-Forma EPS", base["pf_eps"], "eps"),
        ("Accretion / Dilution (por acción)", base["acc"], "eps_s"),
        ("Accretion / Dilution (%)", base["acc_pct"], "pct_s"),
        ("Sinergias breakeven run-rate (M)", be["run_rate"], "m1"),
        ("Prima máxima EPS-neutral", max_prem, "pct"),
    ])

    # Waterfall: pasos sobre las acciones originales; el último recoge la dilución por nuevas acciones
    tax_f = 1 - tax

    def per_share(v: float) -> float:
        return safe_div(v * tax_f, acq_sh, 0.0)

    wf_steps = [
        ("Beneficio Target (DCF)", safe_div(cur_tni, acq_sh, 0.0)),
        ("Sinergias (post-tax)", per_share(cur_syn)),
        ("Costes integración (post-tax)", -per_share(cur_integ)),
        ("Intereses Senior (post-tax)", -per_share(base_deal["int_senior_y"][yi])),
        ("Intereses Mezzanine (post-tax)", -per_share(base_deal["int_mezz_y"][yi])),
        ("Coste oportunidad caja (post-tax)", -per_share(base_deal["opp_cost"])),
        ("Amort. comisiones financiación (post-tax)", -per_share(base_deal["fee_amort_y"][yi])),
        ("Amort. intangibles PPA (post-tax)", -per_share(base_deal["ppa_amort"])),
    ]
    eps_pre_dilution = base["sa_eps"] + sum(v for _, v in wf_steps)
    wf_steps.append(("Dilución por nuevas acciones", base["pf_eps"] - eps_pre_dilution))

    wf_labels = ["EPS Standalone", *[lb for lb, _ in wf_steps], "EPS Pro-Forma"]
    wf_values = [base["sa_eps"], *[v for _, v in wf_steps], base["pf_eps"]]
    wf_measures = ["absolute"] + ["relative"] * len(wf_steps) + ["total"]
    waterfall_tbl = make_table("Paso", ["EPS"], [(lb, v, "eps" if m != "relative" else "eps_s")
                                                  for lb, v, m in zip(wf_labels, wf_values, wf_measures)])

    wf = go.Figure(go.Waterfall(
        x=wf_labels, y=wf_values, measure=wf_measures,
        text=[f"{v:+.3f}" if m == "relative" else f"{v:.3f}" for v, m in zip(wf_values, wf_measures)],
        textposition="outside", connector={"line": {"color": GREY, "dash": "dot"}},
        increasing={"marker": {"color": GREEN}}, decreasing={"marker": {"color": RED}},
        totals={"marker": {"color": NAVY}},
    ))
    wf.update_layout(yaxis_title="EPS", showlegend=False)
    style_fig(wf, f"Puente del EPS ({year_sel}): Standalone a Pro-Forma", height=560)

    st.divider()
    left, right = st.columns([2, 3], gap="medium")
    with left, card():
        card_title("Resumen de la transacción")
        show_table(summary)
    with right, card():
        show_chart(wf)

    # --- PPA y contribución ---
    ppa_tbl = make_table("Purchase Price Allocation (M)", ["Valor"], [
        ("Precio pagado por el equity", base_deal["equity_value"], "m1"),
        ("(−) Patrimonio neto contable del Target", -base_deal["book_equity"], "m1"),
        ("Exceso del precio sobre valor contable", base_deal["excess"], "m1"),
        ("(−) Intangibles identificables", -base_deal["intangibles"], "m1"),
        ("(+) Pasivo por impuesto diferido (DTL)", base_deal["dtl"], "m1"),
        ("Goodwill", base_deal["goodwill"], "m1"),
        ("Goodwill como % del precio", safe_div(base_deal["goodwill"], base_deal["equity_value"]), "pct"),
        ("Amortización anual de intangibles", base_deal["ppa_amort"], "m1"),
    ])
    contribution = make_table("Contribución vs. propiedad", ["Acquirer", "Target"], [
        ("EBITDA", list(oc["ebitda"]), "pct"),
        ("Beneficio neto (Año 1)", list(oc["net_income"]), "pct"),
        ("Capitalización bursátil", list(oc["market_cap"]), "pct"),
        ("Propiedad pro-forma", [oc["own_acq"], oc["own_tgt"]], "pct"),
    ])
    contrib_labels = ["EBITDA", "Beneficio neto (Año 1)", "Capitalización", "Propiedad pro-forma"]
    contrib_acq = [oc["ebitda"][0], oc["net_income"][0], oc["market_cap"][0], oc["own_acq"]]
    contrib_fig = go.Figure()
    contrib_fig.add_trace(go.Bar(y=contrib_labels, x=contrib_acq, name="Acquirer", orientation="h",
                                 marker_color=NAVY, text=[fmt_value(v, "pct") for v in contrib_acq],
                                 textposition="inside"))
    contrib_fig.add_trace(go.Bar(y=contrib_labels, x=[1 - v for v in contrib_acq], name="Target",
                                 orientation="h", marker_color=GREY,
                                 text=[fmt_value(1 - v, "pct") for v in contrib_acq], textposition="inside"))
    contrib_fig.update_layout(barmode="stack", xaxis_tickformat=".0%", xaxis_range=[0, 1],
                              yaxis_autorange="reversed",
                              legend=dict(orientation="h", y=1.15, x=1, xanchor="right", traceorder="normal"))
    style_fig(contrib_fig, "Análisis de contribución vs. propiedad pro-forma", height=360)

    st.divider()
    pl, pr = st.columns([2, 3], gap="medium")
    with pl, card():
        card_title("Purchase Price Allocation", "Goodwill = precio − valor contable − intangibles + DTL.")
        show_table(ppa_tbl)
    with pr, card():
        show_chart(contrib_fig)
        st.caption("Si la propiedad que reciben los accionistas del Target es inferior a lo que aportan, "
                   "la operación transfiere valor al Acquirer (y viceversa).")

    st.divider()
    with st.expander("Ver metodología y fórmulas"):
        st.markdown(
            """
- **Offer Price** = Precio base del Target (DCF o mercado) × (1 + Prima)
- **Deal Equity Value** = Offer Price × Acciones Target
- **Nuevas acciones** = Stock Consideration / Precio Acquirer
- **Sinergias run-rate** = Sinergias de costes + Sinergias de ingresos × margen EBITDA
- **Coste financiero** = intereses Senior (saldo amortizable) + intereses Mezzanine + Caja propia × coste de oportunidad
  \\+ amortización de comisiones de financiación
- **PPA**: Exceso = Precio − valor contable; Intangibles = % del exceso (amortizables); DTL = Intangibles × t;
  Goodwill = Exceso − Intangibles + DTL (no amortizable)
- **Beneficio del Target** = (EBIT − intereses de su deuda neta) × (1 − t), derivado del DCF para cada año
- **Pro-Forma NI** = NI Acquirer + NI Target(DCF) + (Sinergias capturadas − Costes integración − Coste financiero
  − Amortización intangibles)·(1 − t)
- **Pro-Forma EPS** = Pro-Forma NI / (Acciones Acquirer + Nuevas acciones)
- **Accretion / Dilution** = Pro-Forma EPS − Standalone EPS
- **Sinergias breakeven**: sinergias que igualan Pro-Forma EPS y Standalone EPS (solución cerrada, el NI es lineal
  en las sinergias). **Prima máxima EPS-neutral**: por bisección sobre la prima.
- Las comisiones de asesoramiento son un gasto one-time de cierre y se excluyen del EPS recurrente.
            """
        )

# ---------------------------------------------------------------------------
# 3.4 Pestaña 4: Proyecciones a 3 años y sensibilidad
# ---------------------------------------------------------------------------
with guarded(tab_sens, "Proyecciones y Sensibilidad"):
    require(model_ok, "el modelo no pudo calcularse; revisa las pestañas de DCF y Estructura de Capital.")
    gap()
    with card():
        card_title("Accretion / Dilution por año",
                   "Faseo del sidebar: " + " · ".join(f"{y} {p_:.0%}" for y, p_ in zip(YEARS, phases))
                   + ". Los costes de integración se imputan al Año 1.")
        y_cols = st.columns(3)
        for col, yr, p_ in zip(y_cols, YEARS, proj):
            sc = p_[3]
            col.metric(f"{yr}: EPS Pro-Forma", fmt_value(sc["pf_eps"], "eps"),
                       delta=fmt_value(sc["acc_pct"], "pct_s"),
                       delta_color="normal" if sc["accretive"] else "inverse")

    projection = make_table("Concepto", YEARS, [
        ("% sinergias capturadas", phases, "pct"),
        ("Sinergias capturadas pre-tax (M)", [p_[0] for p_ in proj], "m1"),
        ("Costes de integración (M)", [p_[1] for p_ in proj], "m1"),
        ("Beneficio neto del Target — DCF (M)", [p_[2] for p_ in proj], "m1"),
        ("Cargo financiero pre-tax (M)", base_deal["fin_cost_y"] + base_deal["fee_amort_y"], "m1"),
        ("Amortización intangibles PPA (M)", [base_deal["ppa_amort"]] * len(YEARS), "m1"),
        ("Pro-Forma Net Income (M)", [p_[3]["pf_ni"] for p_ in proj], "m1"),
        ("Pro-Forma Shares (M)", [p_[3]["pf_shares"] for p_ in proj], "m2"),
        ("Standalone EPS", [p_[3]["sa_eps"] for p_ in proj], "eps"),
        ("Pro-Forma EPS", [p_[3]["pf_eps"] for p_ in proj], "eps"),
        ("Accretion / Dilution (por acción)", [p_[3]["acc"] for p_ in proj], "eps_s"),
        ("Accretion / Dilution (%)", [p_[3]["acc_pct"] for p_ in proj], "pct_s"),
        ("Resultado", ["Accretive" if p_[3]["accretive"] else "Dilutive" for p_ in proj], "txt"),
    ])

    gap()
    col_t, col_c = st.columns([3, 2], gap="medium")
    with col_t, card():
        card_title("Proyección a 3 años")
        show_table(projection)
    with col_c, card():
        acc_pcts = [p_[3]["acc_pct"] for p_ in proj]
        bar = go.Figure(go.Bar(
            x=YEARS, y=[0 if pd.isna(v) else v for v in acc_pcts],
            marker_color=[GREEN if (not pd.isna(v) and v >= 0) else RED for v in acc_pcts],
            text=[fmt_value(v, "pct_s") for v in acc_pcts], textposition="outside",
        ))
        bar.update_layout(yaxis_title="Accretion / Dilution", yaxis_tickformat=".1%", showlegend=False)
        style_fig(bar, "Accretion / Dilution por año", height=400)
        show_chart(bar)

    st.divider()
    st.subheader(f"Matriz de sensibilidad: {year_sel}")

    hm = cached_sensitivity_matrix(P, base_price, premium, yi)   # 63 escenarios, cacheados
    z, syn_axis, prem_axis, fallback = hm["z"], hm["syn_axis"], hm["prem_axis"], hm["fallback"]
    n_x, n_y = hm["n_x"], hm["n_y"]
    heat_df = pd.DataFrame(z, index=prem_axis, columns=syn_axis)

    z_limit = max(float(np.nanmax(np.abs(z))) if np.isfinite(z).any() else 1e-9, 1e-9)  # escala simétrica
    heat = go.Figure(go.Heatmap(
        z=z, x=[f"{v:,.0f}" for v in syn_axis], y=[f"{v:.1%}" for v in prem_axis],
        colorscale=HEAT_COLORSCALE, zmin=-z_limit, zmax=z_limit, zmid=0, texttemplate="%{z:+.1%}",
        hovertemplate="Sinergias: %{x} M<br>Prima: %{y}<br>Accretion/Dilution: %{z:+.2%}<extra></extra>",
        colorbar=dict(title="Acc./Dil.", tickformat=".0%"),
    ))
    if not fallback:  # marca el caso base (celda central)
        heat.add_shape(type="rect", xref="x", yref="y",
                       x0=n_x // 2 - 0.5, x1=n_x // 2 + 0.5, y0=n_y // 2 - 0.5, y1=n_y // 2 + 0.5,
                       line=dict(color=NAVY, width=3))
    heat.update_layout(xaxis_title="Sinergias run-rate pre-tax (M)", yaxis_title="Prima sobre precio base")
    style_fig(heat, f"Accretion / Dilution del EPS, {year_sel}", height=520)

    col_h, col_n = st.columns([3, 1], gap="medium")
    with col_h, card():
        show_chart(heat)
    with col_n, card():
        card_title("Cómo leer la matriz")
        st.caption("Eje X: sinergias run-rate a nivel EBITDA (±50% del caso base).")
        st.caption("Eje Y: prima sobre el precio base (±20% del valor introducido).")
        st.caption("Verde = accretive; rojo = dilutive. El recuadro marca el caso base, que coincide con el Resumen.")
        if fallback:
            st.info("Sinergias o prima iguales a cero: la matriz usa rangos absolutos "
                    "(sinergias 0–100 M; prima 0–20%).")
        st.divider()
        st.metric("Caso base", fmt_value(base["acc_pct"], "pct_s"))
        st.caption(f"Prima {premium:.0%} · Sinergias {total_syn:,.0f} M")

# ---------------------------------------------------------------------------
# 3.5 Pestaña 5: Montecarlo
# ---------------------------------------------------------------------------
with guarded(tab_mc, "Análisis de Riesgo Montecarlo"):
    require(model_ok, "el modelo no pudo calcularse; revisa las pestañas de DCF y Estructura de Capital.")
    gap()
    dash_mc = card()   # dashboard: se rellena tras la simulación, pero se muestra arriba
    gap()

    col_p, col_h = st.columns([1, 2], gap="medium")
    with col_p, card():
        card_title("Parámetros de la simulación",
                   f"{N_SIM:,} iteraciones sobre el {year_sel}. Las sinergias siguen una normal centrada en "
                   f"{cur_syn:,.1f} M; el resto de variables se mantienen fijas.")
        vol = st.slider("Volatilidad esperada de las sinergias (desv. estándar, %)", 0, 100, 20, 1) / 100
        seed = st.number_input("Semilla aleatoria (reproducibilidad)", value=42, min_value=0, max_value=2**31 - 1,
                               step=1)
        if cur_syn * vol == 0:
            st.info("Desviación estándar nula (volatilidad o sinergias esperadas = 0): la simulación es determinista.")

    mc = cached_montecarlo(P, base_deal, yi, vol, int(seed))   # 5.000 iteraciones, cacheadas
    sa_eps, prob_acc = mc["sa_eps"], mc["prob_acc"]

    with dash_mc:
        card_title(f"Riesgo de la operación: {year_sel}")
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Probabilidad Accretive", f"{prob_acc:.1f}%",
                  help="Probabilidad de que la transacción sea Accretive (%).")
        k2.metric("EPS Pro-Forma medio", fmt_value(mc["eps_mean"], "eps"),
                  delta=fmt_value(mc["eps_mean"] - sa_eps, "eps_s"))
        k3.metric("EPS determinista (Resumen)", fmt_value(base["pf_eps"], "eps"))
        k4.metric("EPS Standalone", fmt_value(sa_eps, "eps"))
        k5.metric("Peor caso (P5) del EPS", fmt_value(mc["eps_p5"], "eps"))
        if prob_acc >= 50:
            st.success(f"En {prob_acc:.1f}% de las {N_SIM:,} simulaciones la operación resulta accretive.")
        else:
            st.error(f"Solo en {prob_acc:.1f}% de las {N_SIM:,} simulaciones la operación resulta accretive.")

    # Histograma con los mismos bordes para las dos zonas (accretive en verde, dilutive en rojo)
    hist = go.Figure()
    hist.add_trace(go.Bar(x=mc["mids"], y=mc["cnt_acc"], width=mc["widths"], name="Accretive",
                          marker_color=GREEN, opacity=0.9))
    hist.add_trace(go.Bar(x=mc["mids"], y=mc["cnt_dil"], width=mc["widths"], name="Dilutive",
                          marker_color=RED, opacity=0.9))
    hist.add_vline(x=sa_eps, line_dash="dash", line_color=NAVY, line_width=2,
                   annotation_text=f"EPS Standalone {sa_eps:.3f}", annotation_position="top")
    hist.update_layout(barmode="stack", bargap=0.02, xaxis_title="EPS Pro-Forma", yaxis_title="Frecuencia",
                       legend=dict(orientation="h", y=1.1, x=1, xanchor="right"))
    style_fig(hist, f"Distribución del EPS Pro-Forma ({N_SIM:,} simulaciones)", height=460)
    with col_h, card():
        show_chart(hist)

    # Versión numérica (para Excel) y versión formateada (para la UI): EPS en 3 decimales, acreción en %
    mc_stats_x = pd.DataFrame({"Estadístico": STAT_LABELS, "EPS Pro-Forma": mc["eps_stats"],
                               "Accretion / Dilution (%)": mc["acc_stats"]})
    with col_p, card():
        card_title("Estadísticos de la simulación")
        st.dataframe(
            pd.DataFrame({"Estadístico": STAT_LABELS,
                          "EPS Pro-Forma": [fmt_value(e, "eps") for e in mc["eps_stats"]],
                          "Acc./Dil.": [fmt_value(a_, "pct_s") for a_ in mc["acc_stats"]]}),
            hide_index=True, **ST_DF)

    # Datos para Excel: parámetros, histograma y simulaciones
    mc_params = make_table("Parámetro", ["Valor"], [
        ("Año simulado", year_sel, "txt"),
        ("Sinergias esperadas (M)", cur_syn, "m1"),
        ("Volatilidad (desv. estándar)", vol, "pct"),
        ("Semilla aleatoria", str(int(seed)), "txt"),
        ("Iteraciones", f"{N_SIM:,}", "txt"),
        ("EPS Standalone", sa_eps, "eps"),
        ("EPS Pro-Forma determinista (Resumen)", base["pf_eps"], "eps"),
        ("Probabilidad de que la transacción sea Accretive", prob_acc / 100, "pct"),
    ])
    mc_hist = pd.DataFrame({"EPS pro-forma (punto medio)": mc["mids"], "Frecuencia": mc["counts"],
                            "Zona": np.where(mc["mids"] >= sa_eps, "Accretive", "Dilutive")})
    mc_sim = pd.DataFrame({"Sinergias simuladas (M)": mc["syn_draws"], "EPS pro-forma": mc["eps"]})

# ---------------------------------------------------------------------------
# 4. Alertas globales (visibles desde cualquier pestaña)
# ---------------------------------------------------------------------------
with guarded(alerts_box, "Alertas del modelo"):
    if not model_ok:
        st.error(f"El modelo no pudo calcularse ({model_err}). Revisa las pestañas de DCF y Estructura de Capital.")
    else:
        if price_basis.startswith("Valor") and not dcf["valid"]:
            st.warning("**DCF no válido**: el precio base del Target es el de mercado, no el valor intrínseco. "
                       f"Motivo: {dcf['reason']}")
        alert_premium = safe_div(base_deal["offer_price"], tgt_px) - 1
        if alert_premium < 0:
            st.warning(f"**Oferta por debajo del precio de mercado**: {base_deal['offer_price']:,.2f} por acción frente a "
                       f"{tgt_px:,.2f} (prima implícita {alert_premium:+.1%}). Es improbable que los accionistas "
                       "del Target la acepten; revisa la prima o la base del precio.")
        if base_deal["cash_bs"] > acq_cash + 1e-9:
            st.error(f"**Caja insuficiente**: la operación usa {base_deal['cash_bs']:,.1f} M de caja propia y el "
                     f"Acquirer dispone de {acq_cash:,.1f} M.")
        if base_deal["bargain"]:
            st.warning(f"**Goodwill negativo** ({base_deal['goodwill']:,.1f} M): el precio es inferior al valor "
                       "contable del Target (bargain purchase). Revisa el patrimonio neto contable o el precio.")
        alert_lev = leverage_metrics(P, base_deal, 0.0)["lev_pf"]   # criterio conservador, independiente de la pestaña 2
        if not pd.isna(alert_lev) and alert_lev > LEVERAGE_LIMIT:
            st.error(f"**Apalancamiento pro-forma {alert_lev:.2f}x** > {LEVERAGE_LIMIT:.1f}x: riesgo de rebaja de rating.")


# ---------------------------------------------------------------------------
# 5. Exportación del Pitchbook: BAJO DEMANDA (lazy) + session_state
# ---------------------------------------------------------------------------
def collect_pitchbook_tables() -> dict:
    """
    Reúne las tablas que las pestañas ya han calculado. Solo se invoca cuando el usuario pulsa
    «Preparar Pitchbook»; en un rerun normal no se ejecuta.
    """
    assumptions = make_table("Supuesto", ["Valor"], [
        ("ACQUIRER", "", "txt"),
        ("Beneficio neto (M)", acq_ni, "m1"), ("Acciones en circulación (M)", acq_sh, "m2"),
        ("Precio por acción", acq_px, "m2"), ("EBITDA (M)", acq_ebitda, "m1"),
        ("Deuda neta existente (M)", acq_netdebt, "m1"), ("Caja disponible (M)", acq_cash, "m1"),
        ("TARGET (MERCADO)", "", "txt"),
        ("Acciones en circulación (M)", tgt_sh, "m2"), ("Precio de mercado por acción", tgt_px, "m2"),
        ("Beneficio neto — derivado del DCF, Año 1 (M)", P["tgt_ni_y"][0], "m1"),
        ("Beneficio neto — derivado del DCF, Año 2 (M)", P["tgt_ni_y"][1], "m1"),
        ("Beneficio neto — derivado del DCF, Año 3 (M)", P["tgt_ni_y"][2], "m1"),
        ("OPERACIÓN", "", "txt"),
        ("Base del precio Target", base_label, "txt"), ("Precio base del Target", base_price, "m2"),
        ("Prima sobre el precio base", premium, "pct"), ("Pago en efectivo", cash_pct / 100, "pct"),
        ("Pago en acciones", 1 - cash_pct / 100, "pct"), ("Tasa impositiva", tax, "pct"),
        ("SINERGIAS Y ANÁLISIS", "", "txt"),
        ("Sinergias de costes (M)", cost_syn, "m1"), ("Sinergias de ingresos (M)", rev_syn, "m1"),
        ("Margen EBITDA de las sinergias de ingresos", rev_syn_margin, "pct"),
        ("Sinergias run-rate a nivel EBITDA (M)", total_syn, "m1"),
        ("Costes de integración (M)", integration_costs, "m1"),
        ("Faseo Año 1", phases[0], "pct"), ("Faseo Año 2", phases[1], "pct"), ("Faseo Año 3", phases[2], "pct"),
        ("Año de análisis", year_sel, "txt"),
        ("DCF", "", "txt"),
        ("Ingresos LTM (M)", rev0, "m1"), ("Crecimiento de ingresos", growth, "pct"),
        ("Margen EBITDA", margin, "pct"), ("D&A (% ingresos)", da_pct, "pct"),
        ("Capex (% ingresos)", capex_pct, "pct"), ("NWC (% del Δ ingresos)", nwc_pct, "pct"),
        ("WACC", wacc, "pct"), ("Crecimiento a perpetuidad (g)", g_perp, "pct"),
        ("Deuda neta del Target (M)", tgt_netdebt, "m1"), ("Tipo de interés de su deuda neta", td_rate, "pct"),
        ("ESTRUCTURA DE CAPITAL", "", "txt"),
        ("% Caja", cap_cash, "pct"), ("% Deuda Senior", cap_senior, "pct"), ("% Deuda Mezzanine", cap_mezz, "pct"),
        ("Coste de oportunidad de la caja", rate_cash, "pct"),
        ("Tipo Senior", senior_rate, "pct"), ("Tipo Mezzanine", mezz_rate, "pct"),
        ("Plazo de amortización Senior (años)", str(int(senior_term)), "txt"),
        ("Comisiones de asesoramiento (% del equity)", fee_adv, "pct"),
        ("Comisiones de financiación (% de la deuda)", fee_fin, "pct"),
        ("PPA", "", "txt"),
        ("Patrimonio neto contable del Target (M)", tgt_book, "m1"),
        ("% del exceso asignado a intangibles", ppa_intang_pct, "pct"),
        ("Vida útil de los intangibles (años)", str(int(ppa_life)), "txt"),
    ])
    return dict(
        year_label=year_sel, assumptions=assumptions, dcf_proj=dcf_proj, dcf_bridge=dcf_bridge,
        dcf_sens=dcf_sens, tranches=tranches, sources_uses=sources_uses, debt_schedule=debt_schedule,
        credit=credit, summary=summary, ppa=ppa_tbl, contribution=contribution,
        waterfall=waterfall_tbl, projection=projection, heat=heat_df, mc_params=mc_params,
        mc_stats=mc_stats_x, mc_hist=mc_hist, mc_sim=mc_sim,
    )


def inputs_signature() -> str:
    """Huella de TODOS los inputs que afectan al Excel: sirve para saber si el Pitchbook preparado sigue vigente."""
    payload = dict(P=P, dcf=dcf_inputs, premium=premium, basis=price_basis, year=year_sel,
                   vol=vol, seed=int(seed), incl_syn=incl_syn)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]


with export_box:
    st.markdown("**Pitchbook**")
    if not XLSX_AVAILABLE:
        st.error("Falta la librería `xlsxwriter`: instálala con `pip install xlsxwriter`.")
    else:
        try:
            sig = inputs_signature()
            ready = st.session_state.get(PB_KEY)
            is_fresh = bool(ready) and ready["sig"] == sig

            # 1) Preparar: único punto donde se construye el Excel (solo cuando el usuario lo pide)
            if st.button("Preparar Pitchbook (Excel)", type="secondary" if is_fresh else "primary",
                         help="Genera el Excel en memoria con los inputs actuales. No se regenera en cada interacción.",
                         **ST_BTN):
                with st.spinner("Generando el Excel…"):
                    ready = dict(sig=sig, data=build_pitchbook(collect_pitchbook_tables()),
                                 stamp=datetime.now().strftime("%H:%M:%S"))
                st.session_state[PB_KEY] = ready
                is_fresh = True

            # 2) Descargar: solo sirve los bytes ya preparados (no recalcula nada)
            if is_fresh:
                st.download_button(
                    "Descargar Pitchbook (.xlsx)", data=ready["data"], file_name="Pitchbook_Merger_Synergy.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary",
                    **ST_DL, **ST_DL_NO_RERUN,
                )
                st.caption(f"Preparado a las {ready['stamp']} con los inputs actuales.")
            elif ready:
                st.warning("El Pitchbook preparado corresponde a inputs anteriores. "
                           "Pulsa «Preparar» de nuevo para descargar la versión vigente.")
            else:
                st.caption("El Excel solo se genera al pulsar «Preparar»: así la app responde rápido mientras exploras.")
        except Exception as exc:  # la exportación nunca debe romper la app
            st.warning("No se pudo preparar el Pitchbook: alguna pestaña tiene errores o faltan datos "
                       f"({type(exc).__name__}: {exc}).")