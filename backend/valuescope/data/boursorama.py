"""Boursorama EOD prices — keyless fallback for Euronext listings.

Yahoo is the primary for EU listings but rate-limits aggressively per IP;
Cboe's free CDN and Alpha Vantage don't carry Euronext. Boursorama (Société
Générale's broker portal) serves daily OHLCV JSON for Euronext Paris ("1rP" +
mnemonic) and Amsterdam ("1rA" + mnemonic) with ~10 years of depth — enough
for price, Max chart and beta. Quotes are end-of-day (labelled as such).
Nasdaq Helsinki is NOT covered — .HE names stay Yahoo-only.
"""
from __future__ import annotations

import datetime as dt
import threading
import time

from .cache import get_cached, http_get

_URL = ("https://www.boursorama.com/bourse/action/graph/ws/GetTicksEOD"
        "?symbol={symbol}&length={length}&period=0&guid=")
_TTL = 30 * 60

_SUFFIX_PREFIX = {".PA": "1rP", ".AS": "1rA"}

_PACE = {"lock": threading.Lock(), "last": 0.0, "strikes": 0, "down_until": 0.0}
_MIN_INTERVAL = 0.6
_BREAKER_WINDOW = 180.0


def supports(ticker: str) -> bool:
    t = ticker.upper()
    return any(t.endswith(s) for s in _SUFFIX_PREFIX)


def _symbol(ticker: str) -> str:
    t = ticker.upper()
    for suffix, prefix in _SUFFIX_PREFIX.items():
        if t.endswith(suffix):
            return prefix + t[: -len(suffix)]
    raise ValueError(f"{ticker}: not a Boursorama-covered venue")


def _headers(symbol: str) -> dict:
    # The endpoint returns [] without browser-shaped headers.
    return {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"https://www.boursorama.com/cours/{symbol}/",
    }


def _guarded_get(url: str, symbol: str):
    now = time.time()
    if now < _PACE["down_until"]:
        raise RuntimeError(
            f"Boursorama cooling down {int(_PACE['down_until'] - now)}s")
    with _PACE["lock"]:
        wait = _PACE["last"] + _MIN_INTERVAL - time.time()
        if wait > 0:
            time.sleep(wait)
        _PACE["last"] = time.time()
    try:
        r = http_get(url, headers=_headers(symbol), timeout=25)
        _PACE["strikes"] = 0
        return r
    except Exception:
        _PACE["strikes"] += 1
        if _PACE["strikes"] >= 3:
            _PACE["down_until"] = time.time() + _BREAKER_WINDOW
        raise


def quote_page_url(ticker: str) -> str:
    """Human-readable quote page for verify-at-source links."""
    return f"https://www.boursorama.com/cours/{_symbol(ticker)}/"


def price_and_history(ticker: str, *, days: int = 2520) -> dict:
    """{"price", "currency", "history", "source"} — same shape as the other
    price sources. `d` in QuoteTab is days since 1970-01-01; length is in
    calendar days (3650 -> ~2520 trading rows)."""
    symbol = _symbol(ticker)

    def build():
        length = max(365, int(days * 365 / 252))
        r = _guarded_get(_URL.format(symbol=symbol, length=length), symbol)
        d = (r.json() or {}).get("d") or {}
        rows = d.get("QuoteTab") or []
        history = []
        epoch = dt.date(1970, 1, 1)
        for q in rows:
            try:
                history.append({
                    "date": (epoch + dt.timedelta(days=int(q["d"]))).isoformat(),
                    "close": float(q["c"]),
                })
            except (KeyError, TypeError, ValueError):
                continue
        if not history:
            raise ValueError(f"{ticker}: Boursorama returned no usable rows "
                             f"for {symbol}")
        return {"price": history[-1]["close"], "currency": "EUR",
                "history": history, "source": "Boursorama EOD (Euronext)"}
    return get_cached(f"boursorama:eod:{symbol}:{days}", _TTL, build)
