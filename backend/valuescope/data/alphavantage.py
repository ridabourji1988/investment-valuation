"""Alpha Vantage — optional, keyed, LAST-RESORT source.

Free keys allow ~25 requests/day (1/sec), so this sits at the very end of the
price and FX chains behind Yahoo and Cboe, with day-long caches. Enabled only
when ALPHAVANTAGE_API_KEY is set; without it the chain simply skips this hop.
"""
from __future__ import annotations

from ..config import config
from .cache import get_cached, http_get

_URL = "https://www.alphavantage.co/query"
_TTL_QUOTE = 6 * 3600
_TTL_HISTORY = 24 * 3600
_TTL_FX = 24 * 3600


class AlphaVantageUnavailable(RuntimeError):
    pass


def available() -> bool:
    return bool(config.ALPHAVANTAGE_API_KEY)


def _query(params: dict) -> dict:
    if not available():
        raise AlphaVantageUnavailable("no ALPHAVANTAGE_API_KEY configured")
    r = http_get(_URL, params={**params, "apikey": config.ALPHAVANTAGE_API_KEY},
                 timeout=20, retries=0)
    body = r.json()
    # Quota/rate responses come back 200 with an explanatory key.
    for k in ("Information", "Note", "Error Message"):
        if k in body:
            raise AlphaVantageUnavailable(f"Alpha Vantage: {body[k][:120]}")
    return body


def quote(symbol: str) -> dict:
    """{"price", "prev_close"} from GLOBAL_QUOTE."""
    def build():
        q = _query({"function": "GLOBAL_QUOTE", "symbol": symbol})["Global Quote"]
        px = float(q["05. price"])
        if px <= 0:
            raise ValueError(f"Alpha Vantage has no price for {symbol}")
        return {"price": px, "prev_close": float(q.get("08. previous close") or px)}
    return get_cached(f"av:quote:{symbol.upper()}", _TTL_QUOTE, build)


def history(symbol: str, *, days: int = 260) -> list[dict]:
    """Last `days` daily closes as [{"t", "close", "date"}], oldest-first."""
    def build():
        body = _query({"function": "TIME_SERIES_DAILY", "symbol": symbol,
                       "outputsize": "full"})
        series = body.get("Time Series (Daily)") or {}
        rows = sorted((d, float(v["4. close"])) for d, v in series.items())
        if not rows:
            raise ValueError(f"Alpha Vantage has no history for {symbol}")
        return [{"close": round(c, 4), "date": d} for d, c in rows]
    full = get_cached(f"av:history:{symbol.upper()}", _TTL_HISTORY, build)
    tail = full[-days:]
    return [{"t": i, "close": r["close"], "date": r["date"]} for i, r in enumerate(tail)]


def fx_to_usd(currency: str) -> float:
    """1 unit of `currency` in US$ from CURRENCY_EXCHANGE_RATE."""
    ccy = currency.upper()
    if ccy == "USD":
        return 1.0
    def build():
        q = _query({"function": "CURRENCY_EXCHANGE_RATE",
                    "from_currency": ccy, "to_currency": "USD"})
        rate = float(q["Realtime Currency Exchange Rate"]["5. Exchange Rate"])
        if rate <= 0:
            raise ValueError(f"Alpha Vantage has no USD rate for {ccy}")
        return rate
    return get_cached(f"av:fx:{ccy}", _TTL_FX, build)
