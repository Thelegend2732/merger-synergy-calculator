"""
Company fundamentals from Yahoo Finance (via yfinance) and their mapping onto model inputs.

`fetch_company` is the only function that touches the network. `acquirer_inputs`, `target_inputs`
and `estimate_wacc` are pure, so the mapping is unit-tested offline with fixture data.
All amounts are returned in millions of the company's reporting currency.
"""
from __future__ import annotations

import math

from engine import MAX_M, MAX_PX, MAX_SH

# CAPM assumptions for the WACC estimate (shown to the user next to the result)
RISK_FREE = 0.0425
EQUITY_RISK_PREMIUM = 0.050
DEFAULT_DEBT_RATE = 0.05


class MarketDataError(Exception):
    """Ticker not found, network failure or statements missing a required line."""


def _latest(df, *rows):
    """Most recent non-null value of the first row label present in a yfinance statement."""
    if df is None or df.empty:
        return None
    for r in rows:
        if r in df.index:
            s = df.loc[r].dropna()
            if not s.empty:
                return float(s.iloc[0])
    return None


def _series(df, row):
    if df is None or df.empty or row not in df.index:
        return []
    return [float(v) for v in df.loc[row].dropna().tolist()]


def fetch_company(ticker: str) -> dict:
    """Download the latest annual fundamentals of `ticker`. Raises MarketDataError on failure."""
    try:
        import yfinance as yf
    except ImportError as exc:
        raise MarketDataError("yfinance is not installed: `pip install yfinance`.") from exc

    ticker = ticker.strip().upper()
    if not ticker:
        raise MarketDataError("Empty ticker.")
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        inc, cf, bs = t.income_stmt, t.cashflow, t.balance_sheet
    except Exception as exc:  # noqa: BLE001 - yfinance raises many unrelated exception types
        raise MarketDataError(f"Could not download {ticker}: {exc}") from exc

    price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
    if not price or inc is None or inc.empty:
        raise MarketDataError(f"No market data or financial statements found for {ticker}.")

    m = 1e6
    revenue = _latest(inc, "Total Revenue")
    revenues = _series(inc, "Total Revenue")
    d = dict(
        ticker=ticker,
        name=info.get("shortName") or ticker,
        currency=info.get("currency"),
        financial_currency=info.get("financialCurrency") or info.get("currency"),
        fiscal_year_end=str(inc.columns[0].date()),
        price=float(price),
        shares=(_latest(bs, "Ordinary Shares Number", "Share Issued") or info.get("sharesOutstanding") or 0) / m,
        revenue=(revenue or 0) / m,
        revenue_hist=[v / m for v in revenues],
        ebitda=(_latest(inc, "EBITDA", "Normalized EBITDA") or info.get("ebitda") or 0) / m,
        net_income=(_latest(inc, "Net Income Common Stockholders", "Net Income") or 0) / m,
        da=(_latest(cf, "Depreciation And Amortization", "Depreciation Amortization Depletion")
            or _latest(inc, "Reconciled Depreciation") or 0) / m,
        capex=abs(_latest(cf, "Capital Expenditure") or 0) / m,
        interest=abs(_latest(inc, "Interest Expense") or 0) / m,
        tax_rate=_latest(inc, "Tax Rate For Calcs"),
        debt=(_latest(bs, "Total Debt") or 0) / m,
        cash=(_latest(bs, "Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents") or 0) / m,
        book_equity=(_latest(bs, "Stockholders Equity", "Common Stock Equity") or 0) / m,
        beta=info.get("beta"),
        low_52w=info.get("fiftyTwoWeekLow"), high_52w=info.get("fiftyTwoWeekHigh"),
    )
    missing = [k for k in ("shares", "revenue", "ebitda") if not d[k]]
    if missing:
        raise MarketDataError(f"{ticker}: statements are missing {', '.join(missing)}.")
    return d


def fetch_multiples(ticker: str, as_of: str | None = None) -> dict:
    """
    EV/EBITDA and EV/Revenue of a peer. EV = price × shares + total debt − cash & short-term investments.
    With `as_of` (YYYY-MM-DD) the price is the last close on or before that date and the statements are
    the fiscal year closest to it, so a historical deal can be benchmarked without look-ahead bias;
    otherwise the current price and the latest fiscal year are used.
    """
    try:
        import pandas as pd
        import yfinance as yf

        t = yf.Ticker(ticker.strip().upper())
        inc, bs = t.income_stmt, t.balance_sheet
        if inc is None or inc.empty:
            raise MarketDataError(f"No financial statements found for {ticker}.")
        if as_of:
            when = pd.Timestamp(as_of)
            hist = t.history(start=when - pd.Timedelta(days=10), end=when + pd.Timedelta(days=1), auto_adjust=False)
            if hist.empty:
                raise MarketDataError(f"No price history for {ticker} around {as_of}.")
            price = float(hist["Close"].iloc[-1])
            col = min(inc.columns, key=lambda d: abs((pd.Timestamp(d).tz_localize(None) - when).days))
        else:
            info = t.info or {}
            price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
            col = inc.columns[0]
        name = (t.info or {}).get("shortName", ticker) if not as_of else ticker.upper()
    except MarketDataError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise MarketDataError(f"Could not download {ticker}: {exc}") from exc

    def at(df, *rows):
        for r in rows:
            if df is not None and r in df.index and col in df.columns and df.loc[r, col] == df.loc[r, col]:
                return float(df.loc[r, col])
        return None

    shares = at(bs, "Ordinary Shares Number", "Share Issued")
    ebitda, revenue = at(inc, "EBITDA", "Normalized EBITDA"), at(inc, "Total Revenue")
    if not (price and shares and revenue):
        raise MarketDataError(f"{ticker}: missing price, shares or revenue.")
    ev = price * shares + (at(bs, "Total Debt") or 0.0) - (
        at(bs, "Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents") or 0.0)
    return {"Company": name, "Ticker": ticker.strip().upper(), "Fiscal year": str(pd.Timestamp(col).date()),
            "EV (M)": round(ev / 1e6, 1),
            "EV/EBITDA": round(ev / ebitda, 1) if ebitda and ebitda > 0 else None,
            "EV/Revenue": round(ev / revenue, 2)}


# ---------------------------------------------------------------------------
# Pure mapping onto model inputs (UI units: millions, percentages as 0–100)
# ---------------------------------------------------------------------------
def _clip(v: float, lo: float, hi: float) -> float:
    return float(min(max(v, lo), hi))


def _money(v: float) -> float:
    return round(_clip(v, -MAX_M, MAX_M), 1)


def _shares(v: float) -> float:
    return round(_clip(v, 0.01, MAX_SH), 2)


def _price(v: float) -> float:
    return round(_clip(v, 0.01, MAX_PX), 2)


def revenue_cagr(revenue_hist: list) -> float | None:
    """CAGR over the annual revenue history (most recent first), or None if it cannot be computed."""
    vals = [v for v in revenue_hist if v and v > 0]
    if len(vals) < 2:
        return None
    return (vals[0] / vals[-1]) ** (1 / (len(vals) - 1)) - 1


def estimate_wacc(c: dict, tax: float) -> dict:
    """CAPM cost of equity, after-tax cost of debt (interest / debt), market-value weights."""
    beta = c.get("beta") if c.get("beta") and math.isfinite(c["beta"]) else 1.0
    ke = RISK_FREE + beta * EQUITY_RISK_PREMIUM
    kd = c["interest"] / c["debt"] if c["debt"] > 0 and c["interest"] > 0 else DEFAULT_DEBT_RATE
    e, dbt = c["price"] * c["shares"], max(c["debt"], 0.0)
    w_d = dbt / (e + dbt) if e + dbt > 0 else 0.0
    wacc = (1 - w_d) * ke + w_d * kd * (1 - tax)
    return dict(beta=beta, ke=ke, kd=kd, w_d=w_d, wacc=wacc)


def acquirer_inputs(c: dict) -> dict:
    """Sidebar Acquirer fields from fetched fundamentals."""
    return dict(
        acq_ni=_money(c["net_income"]), acq_sh=_shares(c["shares"]), acq_px=_price(c["price"]),
        acq_ebitda=_money(c["ebitda"]), acq_netdebt=_money(c["debt"] - c["cash"]),
        acq_cash=_money(max(c["cash"], 0.0)),
    )


def target_inputs(c: dict, tax: float) -> tuple:
    """Target market data and DCF assumptions from fetched fundamentals. Returns (inputs, wacc details)."""
    rev = c["revenue"]
    cagr = revenue_cagr(c["revenue_hist"])
    w = estimate_wacc(c, tax)
    td_rate = c["interest"] / c["debt"] if c["debt"] > 0 and c["interest"] > 0 else DEFAULT_DEBT_RATE
    inputs = dict(
        tgt_sh=_shares(c["shares"]), tgt_px=_price(c["price"]), tgt_book=_money(c["book_equity"]),
        dcf_rev=_money(max(rev, 0.0)),
        dcf_gr=round(_clip((cagr if cagr is not None else 0.03) * 100, -50, 100), 1),
        dcf_mg=round(_clip(c["ebitda"] / rev * 100, 0, 100), 1),
        dcf_da=round(_clip(c["da"] / rev * 100, 0, 100), 1),
        dcf_cx=round(_clip(c["capex"] / rev * 100, 0, 100), 1),
        dcf_nd=_money(c["debt"] - c["cash"]),
        dcf_td=round(_clip(td_rate * 100, 0, 30), 2),
        dcf_wacc=round(_clip(w["wacc"] * 100, 0.5, 30) * 4) / 4,
    )
    return inputs, w
