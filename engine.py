"""
engine.py — Motor financiero puro del Merger Synergy Calculator
================================================================
Capa MODELO: solo matemáticas. No importa Streamlit ni Plotly, de modo que se puede
testear, reutilizar desde un notebook o ejecutar desde un script.

Contenido:
  1. Constantes compartidas (paleta, topes lógicos, horizontes)
  2. Utilidades numéricas y de tablas (safe_div, make_table, safe_histogram...)
  3. DCF (dcf_valuation, dcf_sensitivity)
  4. Operación (build_deal, year_inputs, scenario, project_years, leverage_metrics)
  5. Cálculos pesados, listos para cachear desde la UI (sensitivity_matrix, run_montecarlo)

Convenciones: importes en millones, salvo precios y EPS. Todas las funciones son puras
(sin estado global): la misma entrada produce siempre la misma salida, lo que permite
envolverlas con st.cache_data en la capa de interfaz.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# 1. Constantes compartidas
# ---------------------------------------------------------------------------
# Paleta (la comparten la UI y el Excel para que los gráficos sean coherentes)
GREEN = "#2e9e5b"   # accretive / positivo
RED = "#d64545"     # dilutive / negativo
AMBER = "#e0a030"   # zona de vigilancia
NAVY = "#1f4e79"    # totales / neutro
GREY = "#8a8f98"    # auxiliares

N_SIM = 5000                # iteraciones Montecarlo
DCF_YEARS = 5               # horizonte explícito del DCF
YEARS = ["Año 1", "Año 2", "Año 3"]
LEVERAGE_LIMIT = 4.0        # Deuda Neta / EBITDA: por encima, riesgo alto
LEVERAGE_WARN = 3.0         # umbral de vigilancia
STAT_LABELS = ["Media", "Mediana", "Desv. estándar", "Percentil 5", "Percentil 95", "Mínimo", "Máximo"]

# Topes lógicos de los inputs (evitan desbordamientos y valores absurdos)
MAX_M = 10_000_000.0    # importes en millones
MAX_SH = 1_000_000.0    # acciones en millones
MAX_PX = 100_000.0      # precio por acción
MAX_SYN = 1_000_000.0   # sinergias / costes de integración (M)


# ---------------------------------------------------------------------------
# 2. Utilidades numéricas y de tablas
# ---------------------------------------------------------------------------
def safe_div(num: float, den: float, default: float = np.nan) -> float:
    """División protegida frente a denominadores nulos o NaN."""
    if den is None or pd.isna(den) or den == 0:
        return default
    return num / den


class ModelError(Exception):
    """Error de modelo controlado (dependencia no disponible, resultado no finito...)."""


def require(cond: bool, msg: str) -> None:
    """Lanza ModelError con un mensaje claro si no se cumple una condición del modelo."""
    if not cond:
        raise ModelError(msg)


# Claves de formato: cada fila de una tabla lleva su clave y sirve igual para la UI y para Excel
FMT_PY = {
    "m1": lambda v: f"{v:,.1f}",
    "m2": lambda v: f"{v:,.2f}",
    "eps": lambda v: f"{v:,.3f}",
    "eps_s": lambda v: f"{v:+,.3f}",
    "pct": lambda v: f"{v:.2%}",
    "pct_s": lambda v: f"{v:+.2%}",
    "x": lambda v: f"{v:.2f}x",
    "txt": str,
}


def fmt_value(v, key: str) -> str:
    """Formatea un valor según su clave; tolera NaN/None/inf."""
    if isinstance(v, str):
        return v
    if v is None or pd.isna(v) or not np.isfinite(v):
        return "n/a"
    return FMT_PY[key](float(v))


def make_table(first_col: str, columns: list, rows: list) -> pd.DataFrame:
    """
    Tabla numérica con una clave de formato por fila.
    rows = [(etiqueta, valor | [valores], clave_formato), ...]
    Columnas resultantes: [first_col, *columns, "fmt"].
    """
    data = []
    for label, vals, key in rows:
        vals = list(vals) if isinstance(vals, (list, tuple, np.ndarray)) else [vals]
        data.append([label, *vals, key])
    return pd.DataFrame(data, columns=[first_col, *columns, "fmt"])


def display_table(df: pd.DataFrame) -> pd.DataFrame:
    """Versión de texto formateado (para mostrar) de una tabla creada con make_table."""
    out = df.drop(columns="fmt").astype(object)
    for i, key in enumerate(df["fmt"]):
        for c in out.columns[1:]:
            out.iat[i, out.columns.get_loc(c)] = fmt_value(df.iat[i, df.columns.get_loc(c)], key)
    return out


def safe_histogram(values, bins: int = 40):
    """
    Histograma robusto: ignora no finitos y tolera distribuciones degeneradas (todas las
    iteraciones iguales o rango minúsculo respecto a la magnitud), donde np.histogram falla.
    Devuelve (conteos, bordes).
    """
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return np.array([0]), np.array([0.0, 1.0])
    lo, hi = float(v.min()), float(v.max())
    if hi - lo <= max(1e-12, 1e-9 * max(abs(lo), abs(hi))):
        w = max(1e-6, abs(lo) * 1e-6)
        return np.array([v.size]), np.array([lo - w, lo + w])
    return np.histogram(v, bins=bins, range=(lo, hi))


# ---------------------------------------------------------------------------
# 3. DCF
# ---------------------------------------------------------------------------
def dcf_valuation(d: dict, wacc: float | None = None, g: float | None = None) -> dict:
    """
    DCF a 5 años del Target. `d` contiene: rev0, growth, margin, da_pct, capex_pct, nwc_pct,
    wacc, g, net_debt, td_rate, shares, tax. wacc/g opcionales para barridos de sensibilidad.
    FCF = EBITDA - impuestos s/ EBIT - Capex - inversión en NWC.
    Además deriva el beneficio neto del Target (EBIT - intereses sobre deuda neta, tras impuestos),
    que es el que alimenta el EPS pro-forma: así el DCF y la acreción/dilución comparten motor.
    """
    wacc = d["wacc"] if wacc is None else wacc
    g = d["g"] if g is None else g
    t = np.arange(1, DCF_YEARS + 1)

    with np.errstate(all="ignore"):
        rev = d["rev0"] * (1 + d["growth"]) ** t
        rev_prev = np.concatenate(([d["rev0"]], rev[:-1]))
        growth_row = np.divide(rev, rev_prev, out=np.full(rev.shape, np.nan), where=rev_prev != 0) - 1
        ebitda = rev * d["margin"]
        da = rev * d["da_pct"]
        ebit = ebitda - da
        taxes = np.maximum(ebit, 0.0) * d["tax"]
        capex = rev * d["capex_pct"]
        d_nwc = (rev - rev_prev) * d["nwc_pct"]
        fcf = ebitda - taxes - capex - d_nwc

        # Beneficio neto del Target (nivelado): EBIT - intereses de su deuda neta, tras impuestos
        interest_td = d["net_debt"] * d["td_rate"]
        pretax = ebit - interest_td
        ni = pretax - np.maximum(pretax, 0.0) * d["tax"]

        disc = (1 + wacc) ** -t
        pv_fcf = fcf * disc

        reason = ""
        if wacc <= g:
            reason = "El WACC debe ser mayor que la tasa de crecimiento a perpetuidad (g): el Terminal Value no está definido."
        tv = pv_tv = ev = equity = price = np.nan
        if not reason:
            tv = fcf[-1] * (1 + g) / (wacc - g)
            pv_tv = tv * disc[-1]
            ev = float(pv_fcf.sum() + pv_tv)
            equity = ev - d["net_debt"]
            price = safe_div(equity, d["shares"])
            if not np.isfinite(equity) or equity <= 0:
                reason = "El Equity Value resultante es nulo, negativo o no finito: revisa márgenes, WACC o deuda neta."
    return dict(
        valid=not reason, reason=reason, years=t, rev=rev, rev_prev=rev_prev, growth_row=growth_row,
        ebitda=ebitda, da=da, ebit=ebit, taxes=taxes, capex=capex, d_nwc=d_nwc, fcf=fcf, disc=disc,
        pv_fcf=pv_fcf, sum_pv=float(pv_fcf.sum()), tv=tv, pv_tv=pv_tv, ev=ev, equity=equity, price=price,
        interest_td=interest_td, ni=ni, wacc=wacc, g=g,
    )


def dcf_sensitivity(d: dict) -> pd.DataFrame:
    """Valor intrínseco por acción para una rejilla WACC x g (±1 pp, paso 0,5 pp; WACC mínimo 0,5%)."""
    waccs = np.maximum(d["wacc"] + np.arange(-0.01, 0.0101, 0.005), 0.005)
    gs = d["g"] + np.arange(-0.01, 0.0101, 0.005)
    grid = np.full((len(waccs), len(gs)), np.nan)
    for i, w in enumerate(waccs):
        for j, gg in enumerate(gs):
            r = dcf_valuation(d, wacc=w, g=gg)
            grid[i, j] = r["price"] if r["valid"] else np.nan
    return pd.DataFrame(grid, index=waccs, columns=gs)


# ---------------------------------------------------------------------------
# 4. Operación: estructura, escenarios y apalancamiento
# ---------------------------------------------------------------------------
def build_deal(p: dict, base_price: float, premium: float) -> dict:
    """
    Estructura de la operación. El precio base del Target procede del DCF (o del mercado).
    La parte en efectivo se financia con caja propia + Senior + Mezzanine (p['cap_*'] suman 1).
    Coste financiero = intereses de la deuda + coste de oportunidad de la caja propia.
    """
    offer_price = base_price * (1 + premium)
    equity_value = offer_price * p["tgt_sh"]
    cash = equity_value * p["cash_w"]
    stock = equity_value - cash
    new_shares = safe_div(stock, p["acq_px"], default=0.0)

    cash_bs = cash * p["cap_cash"]
    senior = cash * p["cap_senior"]
    mezz = cash * p["cap_mezz"]
    int_senior = senior * p["rate_senior"]
    int_mezz = mezz * p["rate_mezz"]
    opp_cost = cash_bs * p["rate_cash"]
    debt = senior + mezz
    interest = int_senior + int_mezz
    return dict(
        premium=premium, base_price=base_price, offer_price=offer_price, equity_value=equity_value,
        cash=cash, stock=stock, new_shares=new_shares, cash_bs=cash_bs, senior=senior, mezz=mezz,
        debt=debt, int_senior=int_senior, int_mezz=int_mezz, interest=interest, opp_cost=opp_cost,
        fin_cost=interest + opp_cost, avg_cost_debt=safe_div(interest, debt),
    )


def year_inputs(p: dict, i: int) -> tuple:
    """
    Fuente única de las magnitudes del año i (0..2): sinergias capturadas (faseadas),
    costes de integración (solo Año 1) y beneficio neto del Target derivado del DCF.
    """
    syn = p["total_syn"] * p["phases"][i]
    integ = p["integration"] if i == 0 else 0.0
    return syn, integ, p["tgt_ni_y"][i]


def scenario(p: dict, deal: dict, synergies: float, integration: float, tgt_ni: float) -> dict:
    """EPS pro-forma y accretion/dilution para unas sinergias, integración y beneficio del Target dados."""
    tax = p["tax"]
    fin_at = deal["fin_cost"] * (1 - tax)
    pf_ni = p["acq_ni"] + tgt_ni + (synergies - integration) * (1 - tax) - fin_at
    pf_shares = p["acq_sh"] + deal["new_shares"]
    sa_eps = safe_div(p["acq_ni"], p["acq_sh"])
    pf_eps = safe_div(pf_ni, pf_shares)
    acc = pf_eps - sa_eps
    return dict(
        pf_ni=pf_ni, pf_shares=pf_shares, sa_eps=sa_eps, pf_eps=pf_eps, acc=acc,
        acc_pct=safe_div(acc, abs(sa_eps)), fin_at=fin_at,
        accretive=bool(acc >= 0) if not pd.isna(acc) else False,
    )


def project_years(p: dict, deal: dict) -> list:
    """Escenario de cada uno de los 3 años: [(sinergias, integración, beneficio Target, escenario), ...]."""
    out = []
    for i in range(len(YEARS)):
        syn, integ, tni = year_inputs(p, i)
        out.append((syn, integ, tni, scenario(p, deal, syn, integ, tni)))
    return out


def leverage_metrics(p: dict, deal: dict, synergies_in_ebitda: float) -> dict:
    """
    Deuda Neta / EBITDA pro-forma. Deuda neta PF = deuda neta Acquirer + deuda neta Target
    + efectivo desembolsado (caja usada + deuda nueva). EBITDA PF = Acquirer + Target (+ sinergias).
    """
    ebitda_pf = p["acq_ebitda"] + p["tgt_ebitda"] + synergies_in_ebitda
    net_debt_pf = p["acq_netdebt"] + p["tgt_netdebt"] + deal["cash"]
    return dict(
        ebitda_pf=ebitda_pf,
        net_debt_pf=net_debt_pf,
        lev_pf=safe_div(net_debt_pf, ebitda_pf) if ebitda_pf > 0 else np.nan,
        lev_sa=safe_div(p["acq_netdebt"], p["acq_ebitda"]) if p["acq_ebitda"] > 0 else np.nan,
        coverage=safe_div(ebitda_pf, deal["interest"]) if ebitda_pf > 0 else np.nan,
    )


# ---------------------------------------------------------------------------
# 5. Cálculos pesados (la UI los envuelve con st.cache_data)
# ---------------------------------------------------------------------------
def sensitivity_matrix(p: dict, base_price: float, premium: float, year_idx: int,
                       n_x: int = 9, n_y: int = 7) -> dict:
    """
    Matriz de accretion/dilution del año `year_idx`: eje X = sinergias totales run-rate (±50%),
    eje Y = prima sobre el precio base (±20%). Si sinergias o prima son cero, un rango relativo
    colapsaría el eje y se usan rangos absolutos (`fallback=True`).
    El centro de la matriz (cuando no hay fallback) coincide con el caso base del Resumen.
    """
    total_syn = p["total_syn"]
    _, integ, tni = year_inputs(p, year_idx)
    phase = p["phases"][year_idx]

    fallback = total_syn <= 0 or premium <= 0
    if fallback:
        syn_axis = np.linspace(0, 100, n_x) if total_syn <= 0 else total_syn * np.linspace(0.5, 1.5, n_x)
        prem_axis = np.linspace(0, 0.20, n_y) if premium <= 0 else premium * np.linspace(0.8, 1.2, n_y)
    else:
        syn_axis = total_syn * np.linspace(0.5, 1.5, n_x)
        prem_axis = premium * np.linspace(0.8, 1.2, n_y)

    z = np.zeros((n_y, n_x))
    for iy, prem_val in enumerate(prem_axis):
        deal_iy = build_deal(p, base_price, prem_val)
        for ix, syn_val in enumerate(syn_axis):
            z[iy, ix] = scenario(p, deal_iy, syn_val * phase, integ, tni)["acc_pct"]
    return dict(z=z, syn_axis=syn_axis, prem_axis=prem_axis, fallback=fallback, n_x=n_x, n_y=n_y)


def _describe(v: np.ndarray) -> list:
    return [np.mean(v), np.median(v), np.std(v), np.percentile(v, 5), np.percentile(v, 95), v.min(), v.max()]


def run_montecarlo(p: dict, deal: dict, year_idx: int, vol: float, seed: int, n_sim: int = N_SIM) -> dict:
    """
    Montecarlo sobre las sinergias capturadas del año `year_idx`: normal centrada en las sinergias
    faseadas con desviación estándar = |sinergias| × vol. El resto de variables (beneficio del Target
    del DCF, coste financiero y de oportunidad) es fijo, igual que en el Resumen.

    Usa un generador local (RandomState) en lugar de la semilla global de NumPy: es determinista,
    reproduce exactamente np.random.seed + np.random.normal y no comparte estado entre sesiones.
    """
    cur_syn, cur_integ, cur_tni = year_inputs(p, year_idx)
    tax = p["tax"]
    std = abs(cur_syn * vol)

    rs = np.random.RandomState(int(seed))
    syn_draws = rs.normal(loc=cur_syn, scale=std, size=n_sim)
    pf_ni = p["acq_ni"] + cur_tni + (syn_draws - cur_integ) * (1 - tax) - deal["fin_cost"] * (1 - tax)
    pf_shares = p["acq_sh"] + deal["new_shares"]
    eps = pf_ni / pf_shares                          # acq_sh > 0 garantizado por los topes del input
    require(bool(np.all(np.isfinite(eps))), "la simulación produjo valores no finitos; revisa los inputs extremos.")

    sa_eps = safe_div(p["acq_ni"], p["acq_sh"])
    has_sa = not pd.isna(sa_eps) and sa_eps != 0
    acc = (eps - sa_eps) / abs(sa_eps) if has_sa else np.full(n_sim, np.nan)
    accretive = eps >= sa_eps

    # Histograma con bordes comunes para las zonas accretive / dilutive
    counts, edges = safe_histogram(eps, bins=40)
    return dict(
        mean_syn=cur_syn, std_syn=std, integration=cur_integ, tgt_ni=cur_tni, sa_eps=sa_eps,
        syn_draws=syn_draws, eps=eps, acc=acc, prob_acc=float(np.mean(accretive)) * 100,
        eps_mean=float(np.mean(eps)), eps_p5=float(np.percentile(eps, 5)),
        eps_stats=_describe(eps), acc_stats=_describe(acc),
        counts=counts, edges=edges, mids=(edges[:-1] + edges[1:]) / 2, widths=np.diff(edges),
        cnt_acc=np.histogram(eps[accretive], bins=edges)[0],
        cnt_dil=np.histogram(eps[~accretive], bins=edges)[0],
    )