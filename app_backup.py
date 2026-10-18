"""
Merger Synergy Calculator
Ejecutar con:  streamlit run app.py
Dependencias:  pip install streamlit pandas numpy plotly
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# Configuración de página
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Merger Synergy Calculator", page_icon="📊", layout="wide")
st.title("📊 Merger Synergy Calculator")
st.caption("Análisis de accretion / dilution del EPS en una operación de M&A (importes en millones, salvo precios y EPS).")

# ---------------------------------------------------------------------------
# Sidebar: inputs
# ---------------------------------------------------------------------------
st.sidebar.header("Inputs de la operación")

st.sidebar.subheader("🏢 Empresa Compradora (Acquirer)")
acq_ni = st.sidebar.number_input("Beneficio Neto (M)", value=500.0, step=10.0, key="acq_ni")
acq_shares = st.sidebar.number_input("Acciones en circulación (M)", value=200.0, min_value=0.01, step=1.0, key="acq_sh")
acq_price = st.sidebar.number_input("Precio por acción actual", value=50.0, min_value=0.01, step=0.5, key="acq_px")

st.sidebar.subheader("🎯 Empresa Objetivo (Target)")
tgt_ni = st.sidebar.number_input("Beneficio Neto (M)", value=100.0, step=5.0, key="tgt_ni")
tgt_shares = st.sidebar.number_input("Acciones en circulación (M)", value=80.0, min_value=0.01, step=1.0, key="tgt_sh")
tgt_price = st.sidebar.number_input("Precio por acción actual", value=20.0, min_value=0.01, step=0.5, key="tgt_px")

st.sidebar.subheader("🤝 Estructura de la operación")
premium = st.sidebar.slider("Prima de adquisición (%)", 0.0, 100.0, 30.0, 1.0) / 100
cash_pct = st.sidebar.slider("Pago en efectivo (Cash %)", 0, 100, 50, 5)
stock_pct = 100 - cash_pct
st.sidebar.markdown(f"**Pago en acciones (Stock %):** {stock_pct}%")
cash_w, stock_w = cash_pct / 100, stock_pct / 100

st.sidebar.subheader("🏦 Condiciones de financiación")
interest_rate = st.sidebar.number_input("Tipo de interés de la nueva deuda (%)", value=6.0, min_value=0.0, step=0.25) / 100
tax_rate = st.sidebar.number_input("Tasa impositiva corporativa (%)", value=25.0, min_value=0.0, max_value=100.0, step=1.0) / 100

st.sidebar.subheader("⚡ Sinergias (Año 1)")
cost_syn = st.sidebar.number_input("Sinergias de costes, pre-tax (M)", value=60.0, step=5.0)
rev_syn = st.sidebar.number_input("Sinergias de ingresos, pre-tax (M)", value=20.0, step=5.0)
integration_costs = st.sidebar.number_input("Costes de integración, one-time (M)", value=30.0, min_value=0.0, step=5.0)

# ---------------------------------------------------------------------------
# Motor lógico
# ---------------------------------------------------------------------------
offer_price = tgt_price * (1 + premium)
deal_equity_value = offer_price * tgt_shares
cash_consideration = deal_equity_value * cash_w
stock_consideration = deal_equity_value * stock_w
new_shares = stock_consideration / acq_price
interest_expense = cash_consideration * interest_rate

total_synergies = cost_syn + rev_syn
net_synergies_after_tax = (total_synergies - integration_costs) * (1 - tax_rate)
interest_after_tax = interest_expense * (1 - tax_rate)

pf_net_income = acq_ni + tgt_ni + net_synergies_after_tax - interest_after_tax
pf_shares = acq_shares + new_shares

standalone_eps = acq_ni / acq_shares
pf_eps = pf_net_income / pf_shares
accretion_abs = pf_eps - standalone_eps
accretion_pct = accretion_abs / standalone_eps if standalone_eps != 0 else np.nan
is_accretive = accretion_abs >= 0

# ---------------------------------------------------------------------------
# Resultados: métricas
# ---------------------------------------------------------------------------
label = "ACCRETIVE ✅" if is_accretive else "DILUTIVE ❌"
if is_accretive:
    st.success(f"La operación es **{label}**: el EPS sube {accretion_abs:+.3f} ({accretion_pct:+.2%}).")
else:
    st.error(f"La operación es **{label}**: el EPS cae {accretion_abs:+.3f} ({accretion_pct:+.2%}).")

c1, c2, c3 = st.columns(3)
c1.metric("EPS Standalone (Acquirer)", f"{standalone_eps:,.3f}")
c2.metric(
    "EPS Pro-Forma",
    f"{pf_eps:,.3f}",
    delta=f"{accretion_abs:+.3f}",
    delta_color="normal",  # verde si positivo, rojo si negativo
)
c3.metric(
    "Accretion / Dilution (%)",
    f"{accretion_pct:+.2%}",
    delta=label,
    delta_color="normal" if is_accretive else "inverse",
)

st.divider()

# ---------------------------------------------------------------------------
# Tabla resumen
# ---------------------------------------------------------------------------
left, right = st.columns([1, 1.4])

with left:
    st.subheader("Resumen de la transacción")
    summary = pd.DataFrame(
        {
            "Métrica": [
                "Offer Price por acción",
                "Deal Equity Value (M)",
                "Cash Consideration / Cash Needed (M)",
                "Stock Consideration (M)",
                "New Shares Issued (M)",
                "Interest Expense nueva deuda (M)",
                "Sinergias totales pre-tax (M)",
                "Pro-Forma Net Income (M)",
                "Pro-Forma Shares Outstanding (M)",
                "Standalone EPS",
                "Pro-Forma EPS",
                "Accretion / Dilution ($)",
                "Accretion / Dilution (%)",
            ],
            "Valor": [
                f"{offer_price:,.2f}",
                f"{deal_equity_value:,.1f}",
                f"{cash_consideration:,.1f}",
                f"{stock_consideration:,.1f}",
                f"{new_shares:,.2f}",
                f"{interest_expense:,.1f}",
                f"{total_synergies:,.1f}",
                f"{pf_net_income:,.1f}",
                f"{pf_shares:,.2f}",
                f"{standalone_eps:,.3f}",
                f"{pf_eps:,.3f}",
                f"{accretion_abs:+,.3f}",
                f"{accretion_pct:+.2%}",
            ],
        }
    )
    st.dataframe(summary, hide_index=True, use_container_width=True)

# ---------------------------------------------------------------------------
# Waterfall: puente Standalone EPS -> Pro-Forma EPS
# ---------------------------------------------------------------------------
# Pasos calculados sobre las acciones originales del Acquirer; el último paso
# recoge el efecto dilutivo de las nuevas acciones emitidas.
step_target = tgt_ni / acq_shares
step_synergies = (total_synergies * (1 - tax_rate)) / acq_shares
step_integration = -(integration_costs * (1 - tax_rate)) / acq_shares
step_interest = -interest_after_tax / acq_shares
eps_before_dilution = standalone_eps + step_target + step_synergies + step_integration + step_interest
step_dilution = pf_eps - eps_before_dilution

labels = [
    "EPS Standalone",
    "Beneficio Target",
    "Sinergias (post-tax)",
    "Costes integración (post-tax)",
    "Intereses deuda (post-tax)",
    "Dilución por nuevas acciones",
    "EPS Pro-Forma",
]
values = [standalone_eps, step_target, step_synergies, step_integration, step_interest, step_dilution, pf_eps]
measures = ["absolute", "relative", "relative", "relative", "relative", "relative", "total"]

fig = go.Figure(
    go.Waterfall(
        x=labels,
        y=values,
        measure=measures,
        text=[f"{v:+.3f}" if m == "relative" else f"{v:.3f}" for v, m in zip(values, measures)],
        textposition="outside",
        connector={"line": {"color": "gray", "dash": "dot"}},
        increasing={"marker": {"color": "#2e9e5b"}},
        decreasing={"marker": {"color": "#d64545"}},
        totals={"marker": {"color": "#1f4e79"}},
    )
)
fig.update_layout(
    title="Puente de EPS: Standalone → Pro-Forma",
    yaxis_title="EPS",
    showlegend=False,
    height=500,
    margin=dict(t=60, b=40),
)

with right:
    st.subheader("Puente del EPS")
    st.plotly_chart(fig, use_container_width=True)

with st.expander("Ver metodología y fórmulas"):
    st.markdown(
        """
- **Offer Price** = Precio Target × (1 + Prima)
- **Deal Equity Value** = Offer Price × Acciones Target
- **Nuevas acciones** = Stock Consideration / Precio Acquirer
- **Intereses** = Cash Consideration × Tipo de interés
- **Pro-Forma NI** = NI Acquirer + NI Target + (Sinergias − Costes integración)·(1 − t) − Intereses·(1 − t)
- **Pro-Forma EPS** = Pro-Forma NI / (Acciones Acquirer + Nuevas acciones)
- **Accretion / Dilution** = Pro-Forma EPS − Standalone EPS
        """
    )