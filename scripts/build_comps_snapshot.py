"""
Rebuild the trading-comps snapshot embedded in a preset case (marketdata/cases.py).

    python scripts/build_comps_snapshot.py 2023-12-21 CDNS ADSK PTC BSY DSY.PA

Prints a Python literal with each peer's EV/EBITDA and EV/Revenue as of the given date (last close
on or before it, fiscal year closest to it), ready to paste into the case definition.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from marketdata.yahoo import MarketDataError, fetch_multiples  # noqa: E402

if __name__ == "__main__":
    as_of, *tickers = sys.argv[1:]
    rows = []
    for tk in tickers:
        try:
            rows.append(fetch_multiples(tk, as_of=as_of))
        except MarketDataError as exc:
            print(f"# skipped {tk}: {exc}", file=sys.stderr)
    print("[")
    for r in rows:
        print(f"    {r!r},")
    print("]")
