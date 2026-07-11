"""Yahoo Finance client (PRD §7) — prices, history, market rate/credit series.

Keyless. Also serves as the macro fallback: ^TNX/^IRX give the 10Y/3M yields
when FRED is unreachable, and the HYG-vs-IEF 3-month relative return acts as a
transparent credit-stress proxy for the HY OAS signal.
"""
from __future__ import annotations

from .cache import get_cached, http_get

CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_HEADERS = {"User-Agent": "Mozilla/5.0 (ValueScope/1.0)"}

_TTL_PRICE = 15 * 60
_TTL_HISTORY = 30 * 60


def fetch_chart(symbol: str, *, rng: str = "1y", interval: str = "1d") -> dict:
    """Chart data with timestamps. Cached; raises on failure."""
    def build():
        r = http_get(CHART.format(symbol=symbol),
                     params={"range": rng, "interval": interval},
                     headers=_HEADERS, timeout=20)
        result = r.json()["chart"]["result"][0]
        meta = result["meta"]
        ts = result.get("timestamp") or []
        closes = (result["indicators"]["quote"][0].get("close") or [])
        series, stamps = [], []
        for i, c in enumerate(closes):
            if c is None:
                continue
            series.append({"t": len(series), "close": round(float(c), 4)})
            stamps.append(ts[i] if i < len(ts) else None)
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
