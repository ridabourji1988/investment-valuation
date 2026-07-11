"""Alpha Vantage — optional, keyed, LAST-RESORT source.

Free keys allow ~25 requests/day (1/sec), so this sits at the very end of the
price and FX chains behind Yahoo and Cboe, with day-long caches. Enabled only
when ALPHAVANTAGE_API_KEY is set; without it the chain simply skips this hop.
"""
from __future__ import annotations

import threading
import time as _time

from ..config import config
from .cache import get_cached, http_get

_URL = "https://www.alphavantage.co/query"
_TTL_QUOTE = 6 * 3600
_TTL_HISTORY = 24 * 3600
_TTL_FX = 24 * 3600

# Free keys: 1 request/second, ~25 requests/day. Requests are serialized with
# a floor interval, and a quota message opens the breaker for 30 minutes —
# hammering an exhausted key during a scan is pure waste.
_PACE = {"lock": threading.Lock(), "last": 0.0}
_MIN_INTERVAL = 1.3
_BREAKER = {"down_until": 0.0}
_BREAKER_WINDOW = 1800.0


class AlphaVantageUnavailable(RuntimeError):
    pass


def available() -> bool:
    return bool(config.ALPHAVANTAGE_API_KEY) and _time.time() >= _BREAKER["down_until"]


def _query(params: dict) -> dict:
    if not config.ALPHAVANTAGE_API_KEY:
        raise AlphaVantageUnavailable("no ALPHAVANTAGE_API_KEY configured")
    if _time.time() < _BREAKER["down_until"]:
        raise AlphaVantageUnavailable("Alpha Vantage quota breaker open")
    with _PACE["lock"]:
        wait = _PACE["last"] + _MIN_INTERVAL - _time.time()
        if wait > 0:
            _time.sleep(wait)
        _PACE["last"] = _time.time()
    r = http_get(_URL, params={**params, "apikey": config.ALPHAVANTAGE_API_KEY},
                 timeout=20, retries=0)
    body = r.json()
    # Quota/rate responses come back 200 with an explanatory key.
    for k in ("Information", "Note", "Error Message"):
        if k in body:
            _BREAKER["down_until"] = _time.time() + _BREAKER_WINDOW
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
        # "compact" = last ~100 sessions ("full" is premium-only). Shorter
        # charts beat no charts for a last-resort source.
        body = _query({"function": "TIME_SERIES_DAILY", "symbol": symbol,
                       "outputsize": "compact"})
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
