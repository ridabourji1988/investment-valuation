"""Cboe delayed-quotes client — the keyless price fallback when Yahoo is
rate-limited.

Cboe publishes official exchange data (15-minute delayed) from a CDN with no
key and no crumb handshake: a current quote and the full daily history for
every US-listed equity/ETF plus the S&P 500 index. Coverage matches exactly
what ValueScope supports (US listings, incl. ADRs), and a 15-minute delay is
already the app's price-refresh cadence.
"""
from __future__ import annotations

import time as _time

from .cache import get_cached, http_get

QUOTE = "https://cdn.cboe.com/api/global/delayed_quotes/quotes/{symbol}.json"
HISTORY = "https://cdn.cboe.com/api/global/delayed_quotes/charts/historical/{symbol}.json"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}

_TTL_QUOTE = 15 * 60
_TTL_HISTORY = 30 * 60

# Yahoo-style symbols -> Cboe path names (indices use an underscore prefix).
_SYMBOL_MAP = {"^GSPC": "_SPX", "^SPX": "_SPX"}

_BREAKER = {"down_until": 0.0, "strikes": 0}
_BREAKER_WINDOW = 300.0


class CboeUnavailable(RuntimeError):
    pass


def _guarded_get(url: str, **kw):
    if _time.time() < _BREAKER["down_until"]:
        raise CboeUnavailable("Cboe circuit breaker open")
    try:
        r = http_get(url, **kw)
    except Exception:
        _BREAKER["strikes"] += 1
        if _BREAKER["strikes"] >= 3:
            _BREAKER["down_until"] = _time.time() + _BREAKER_WINDOW
            _BREAKER["strikes"] = 0
        raise
    _BREAKER["strikes"] = 0
    return r


def _path_symbol(symbol: str) -> str:
    return _SYMBOL_MAP.get(symbol.upper(), symbol.upper())


def quote(symbol: str) -> dict:
    """{"price", "prev_close"} — 15-minute-delayed official quote."""
    def build():
        r = _guarded_get(QUOTE.format(symbol=_path_symbol(symbol)),
                         headers=_HEADERS, timeout=15, retries=1)
        d = r.json()["data"]
        px = float(d.get("current_price") or 0)
        if px <= 0:
            raise ValueError(f"Cboe has no price for {symbol}")
        return {"price": px, "prev_close": float(d.get("prev_day_close") or px)}
    return get_cached(f"cboe:quote:{symbol.upper()}", _TTL_QUOTE, build)


def history(symbol: str, *, days: int = 260) -> list[dict]:
    """Last `days` daily closes as [{"t", "close", "date"}, ...] oldest-first.
    Cboe returns the full listed history; numeric fields may arrive as strings
    (the index feed does), so everything is coerced."""
    def build():
        r = _guarded_get(HISTORY.format(symbol=_path_symbol(symbol)),
                         headers=_HEADERS, timeout=20, retries=1)
        rows = r.json()["data"]
        out = []
        for row in rows:
            c = row.get("close")
            if c in (None, ""):
                continue
            out.append({"close": round(float(c), 4), "date": row.get("date")})
        if not out:
            raise ValueError(f"Cboe has no history for {symbol}")
        return out
    full = get_cached(f"cboe:history:{symbol.upper()}", _TTL_HISTORY, build)
    tail = full[-days:]
    return [{"t": i, "close": r["close"], "date": r["date"]} for i, r in enumerate(tail)]
