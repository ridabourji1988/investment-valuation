"""Yahoo Finance client (PRD §7) — prices, history, market rate/credit series.

Keyless. Also serves as the macro fallback: ^TNX/^IRX give the 10Y/3M yields
when FRED is unreachable, and the HYG-vs-IEF 3-month relative return acts as a
transparent credit-stress proxy for the HY OAS signal.
"""
from __future__ import annotations

import datetime as _dt
import time as _time

import httpx

from .cache import get_cached, http_get

CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
SEARCH = "https://query1.finance.yahoo.com/v1/finance/search"
QUOTE = "https://query1.finance.yahoo.com/v7/finance/quote"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}

_TTL_PRICE = 15 * 60
_TTL_HISTORY = 30 * 60
_TTL_FX = 6 * 3600
_TTL_SEARCH = 3600
_TTL_QUOTE = 6 * 3600

# Circuit breaker: Yahoo rate-limits per IP and the penalty RE-ARMS on every
# request made while boxed. Three consecutive 429s open the breaker for 10
# minutes so the penalty can expire; it re-probes automatically afterwards.
# Stale cache entries keep serving during the window (cache.get_cached), and
# the service watchdog retries failed tickers — no admin action needed.
_BREAKER = {"down_until": 0.0, "strikes": 0}
_BREAKER_WINDOW = 600.0


class YahooUnavailable(RuntimeError):
    pass


def _guarded_get(url: str, **kw):
    if _time.time() < _BREAKER["down_until"]:
        raise YahooUnavailable("Yahoo circuit breaker open (rate-limited)")
    try:
        r = http_get(url, **kw)
    except Exception as e:
        if "429" in str(e):
            _BREAKER["strikes"] += 1
            if _BREAKER["strikes"] >= 3:
                _BREAKER["down_until"] = _time.time() + _BREAKER_WINDOW
                _BREAKER["strikes"] = 0
        raise
    _BREAKER["strikes"] = 0
    return r


def fetch_chart(symbol: str, *, rng: str = "1y", interval: str = "1d") -> dict:
    """Chart data with timestamps and ISO dates. Cached; raises on failure."""
    def build():
        r = _guarded_get(CHART.format(symbol=symbol),
                         params={"range": rng, "interval": interval},
                         headers=_HEADERS, timeout=20, retries=1,
                         alt_hosts={"query1": "query2"})
        result = r.json()["chart"]["result"][0]
        meta = result["meta"]
        ts = result.get("timestamp") or []
        closes = (result["indicators"]["quote"][0].get("close") or [])
        series, stamps = [], []
        for i, c in enumerate(closes):
            if c is None:
                continue
            stamp = ts[i] if i < len(ts) else None
            date = (_dt.date.fromtimestamp(stamp).isoformat() if stamp else None)
            series.append({"t": len(series), "close": round(float(c), 4), "date": date})
            stamps.append(stamp)
        return {
            "symbol": symbol,
            "price": meta.get("regularMarketPrice"),
            "currency": meta.get("currency", "USD"),
            "exchange": meta.get("fullExchangeName", ""),
            "history": series,
            "timestamps": stamps,
        }
    return get_cached(f"yahoo:{symbol}:{rng}:{interval}",
                      _TTL_PRICE if rng in ("1d", "5d") else _TTL_HISTORY, build)


def latest_price(symbol: str) -> float:
    px = fetch_chart(symbol, rng="5d")["price"]
    if not px or px <= 0:
        raise ValueError(f"no price for {symbol}")
    return float(px)


def daily_closes(symbol: str, rng: str = "2y") -> dict:
    """{timestamp -> close} for return alignment across symbols."""
    c = fetch_chart(symbol, rng=rng)
    return {ts: row["close"] for ts, row in zip(c["timestamps"], c["history"])
            if ts is not None}


def regression_beta(symbol: str, benchmark: str = "^GSPC", rng: str = "2y") -> float:
    """Levered beta from daily returns vs the S&P 500, clamped to [0.4, 2.5]."""
    a = daily_closes(symbol, rng)
    b = daily_closes(benchmark, rng)
    common = sorted(set(a) & set(b))
    if len(common) < 120:
        raise ValueError(f"not enough overlapping history for beta({symbol})")
    ra, rb = [], []
    for prev, cur in zip(common, common[1:]):
        if a[prev] > 0 and b[prev] > 0:
            ra.append(a[cur] / a[prev] - 1.0)
            rb.append(b[cur] / b[prev] - 1.0)
    n = len(ra)
    mean_a, mean_b = sum(ra) / n, sum(rb) / n
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(ra, rb)) / n
    var = sum((y - mean_b) ** 2 for y in rb) / n
    if var <= 0:
        raise ValueError("degenerate benchmark variance")
    return max(0.4, min(2.5, cov / var))


# ---- macro fallbacks (keyless) --------------------------------------------- #
def _yield_to_decimal(quote: float) -> float:
    """Yahoo has quoted ^TNX/^IRX both as percent (4.57) and as percent×10
    (45.7) over the years. A Treasury yield above 15% is implausible in the
    modern era, so treat larger quotes as the ×10 convention."""
    return quote / 1000.0 if quote > 15 else quote / 100.0


def yield_10y() -> float:
    """10-year Treasury yield as a decimal (^TNX)."""
    return _yield_to_decimal(latest_price("^TNX"))


def yield_3m() -> float:
    """13-week T-bill yield as a decimal (^IRX)."""
    return _yield_to_decimal(latest_price("^IRX"))


def credit_stress_proxy() -> dict:
    """High-yield stress proxy: HYG (junk bonds) underperforming IEF
    (Treasuries) by >4% over ~3 months signals credit stress."""
    hyg = fetch_chart("HYG", rng="6mo")["history"]
    ief = fetch_chart("IEF", rng="6mo")["history"]
    n = min(len(hyg), len(ief), 66)  # ~3 trading months
    if n < 20:
        raise ValueError("not enough HYG/IEF history")
    hyg_r = hyg[-1]["close"] / hyg[-n]["close"] - 1.0
    ief_r = ief[-1]["close"] / ief[-n]["close"] - 1.0
    spread_move = hyg_r - ief_r
    return {"stress": spread_move < -0.04, "hyg_minus_ief_3m": spread_move}


# ---- FX, search, share counts (all keyless) --------------------------------- #
def fx_to_usd(currency: str) -> float:
    """Spot rate: 1 unit of `currency` in US$ (e.g. EUR -> 1.14)."""
    ccy = currency.upper()
    if ccy == "USD":
        return 1.0
    def build():
        return latest_price(f"{ccy}USD=X")
    return get_cached(f"yahoo:fx:{ccy}", _TTL_FX, build)


def search(query: str, *, count: int = 8) -> list[dict]:
    """Global symbol search (equities only)."""
    def build():
        r = _guarded_get(SEARCH, params={"q": query, "quotesCount": count, "newsCount": 0},
                         headers=_HEADERS, timeout=15, retries=1,
                         alt_hosts={"query1": "query2"})
        out = []
        for q in r.json().get("quotes", []):
            if q.get("quoteType") != "EQUITY":
                continue
            out.append({
                "ticker": q.get("symbol"),
                "name": q.get("shortname") or q.get("longname") or q.get("symbol"),
                "exchange": q.get("exchDisp", ""),
            })
        return out
    return get_cached(f"yahoo:search:{query.lower()}:{count}", _TTL_SEARCH, build)


def _crumb_session() -> tuple[dict, str]:
    """Cookie+crumb pair for the quote API. Cached; raises when Yahoo
    rate-limits the handshake (callers must degrade gracefully)."""
    def build():
        with httpx.Client(headers=_HEADERS, timeout=20, follow_redirects=True) as c:
            c.get("https://fc.yahoo.com")
            r = c.get("https://query1.finance.yahoo.com/v1/test/getcrumb")
            crumb = r.text.strip()
            if r.status_code != 200 or not crumb or "<" in crumb:
                raise ValueError(f"crumb handshake failed ({r.status_code})")
            return dict(c.cookies), crumb
    return get_cached("yahoo:crumb", _TTL_QUOTE, build)


def listing_shares(symbol: str) -> float | None:
    """Shares outstanding consistent with the listing's price (Yahoo computes
    ADR-equivalent counts for depositary receipts). None when the crumb
    handshake is unavailable — callers fall back to EDGAR + ADR ratio table."""
    def build():
        cookies, crumb = _crumb_session()
        r = httpx.get(QUOTE, params={"symbols": symbol, "crumb": crumb},
                      headers=_HEADERS, cookies=cookies, timeout=20)
        r.raise_for_status()
        result = r.json()["quoteResponse"]["result"]
        if not result:
            raise ValueError(f"no quote for {symbol}")
        sh = result[0].get("sharesOutstanding")
        if not sh or sh <= 0:
            raise ValueError(f"no share count for {symbol}")
        return float(sh)
    try:
        return get_cached(f"yahoo:shares:{symbol}", _TTL_QUOTE, build)
    except Exception:  # noqa: BLE001 — degrade to EDGAR/ratio table
        return None
