"""Market-data facade — every price-shaped fetch goes through a source chain
so no single provider (Yahoo) can take the app down.

Chains (first success wins, source label carried through):
  prices/history   Yahoo Finance (real-time)  -> Cboe delayed quotes (15 min)
                   -> Alpha Vantage (optional key, last resort)
  regression beta  close series via the same chain, vs the S&P 500
  credit proxy     HYG vs IEF closes via the same chain
  FX               Yahoo spot -> er-api daily -> ECB (frankfurter)
                   -> Alpha Vantage (optional key, last resort)

Nothing is ever synthesised: when every source in a chain fails, the call
raises and the ticker is skipped and reported.
"""
from __future__ import annotations

from . import alphavantage, cboe, fx, yahoo


def price_and_history(ticker: str, *, rng: str = "10y") -> dict:
    """{"price", "currency", "history", "source"}. Yahoo first (it also tells
    us the listing currency, used to reject non-US$ listings); Cboe fallback
    covers US listings only, so its currency is USD by construction.

    Ten years by default: one cached fetch serves the current price, the full
    Max-range chart and the beta regression."""
    days = {"1y": 260, "2y": 505, "5y": 1260}.get(rng, 2520)
    try:
        c = yahoo.fetch_chart(ticker, rng=rng)
        px = c.get("price")
        if px and px > 0 and c.get("history"):
            return {"price": float(px), "currency": c.get("currency", "USD"),
                    "history": c["history"], "source": "Yahoo Finance"}
    except Exception:  # noqa: BLE001 — fall through to Cboe
        pass
    try:
        q = cboe.quote(ticker)
        hist = cboe.history(ticker, days=days)
        return {"price": q["price"], "currency": "USD", "history": hist,
                "source": "Cboe delayed quotes (15 min)"}
    except Exception as e_cboe:  # noqa: BLE001 — last resort, only with a key
        if not alphavantage.available():
            raise
        try:
            q = alphavantage.quote(ticker)
            hist = alphavantage.history(ticker, days=days)
            return {"price": q["price"], "currency": "USD", "history": hist,
                    "source": "Alpha Vantage (daily)"}
        except Exception as e_av:
            raise RuntimeError(
                f"no price source available for {ticker} "
                f"(Cboe: {e_cboe}; Alpha Vantage: {e_av})") from e_av


def price_history(ticker: str) -> list[dict]:
    return price_and_history(ticker)["history"]


def _close_map(symbol: str, *, days: int) -> dict:
    """{iso_date: close} through the source chain, for return alignment.
    Reuses the cached 10y fetch and slices the tail — no extra request."""
    try:
        hist = yahoo.fetch_chart(symbol, rng="10y")["history"][-days:]
    except Exception:  # noqa: BLE001
        hist = cboe.history(symbol, days=days)
    return {row["date"]: row["close"] for row in hist if row.get("date")}


def regression_beta(ticker: str, benchmark: str = "^GSPC") -> float:
    """Levered beta from ~2y of daily returns vs the S&P 500, clamped to
    [0.4, 2.5]. Stock and benchmark may come from different sources — series
    are aligned by ISO date, so mixing is safe."""
    a = _close_map(ticker, days=505)
    b = _close_map(benchmark, days=505)
    common = sorted(set(a) & set(b))
    if len(common) < 120:
        raise ValueError(f"not enough overlapping history for beta({ticker})")
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


def credit_stress_proxy() -> dict:
    """HYG (junk) underperforming IEF (Treasuries) by >4% over ~3 months
    signals credit stress. Source-chained like everything else."""
    def hist(sym):
        try:
            return yahoo.fetch_chart(sym, rng="6mo")["history"], "Yahoo"
        except Exception:  # noqa: BLE001
            return cboe.history(sym, days=130), "Cboe delayed"
    hyg, src = hist("HYG")
    ief, _ = hist("IEF")
    n = min(len(hyg), len(ief), 66)  # ~3 trading months
    if n < 20:
        raise ValueError("not enough HYG/IEF history")
    hyg_r = hyg[-1]["close"] / hyg[-n]["close"] - 1.0
    ief_r = ief[-1]["close"] / ief[-n]["close"] - 1.0
    spread_move = hyg_r - ief_r
    return {"stress": spread_move < -0.04, "hyg_minus_ief_3m": spread_move,
            "source": f"{src} HYG−IEF 3-month proxy"}


def fx_to_usd(currency: str) -> float:
    """1 unit of `currency` in US$: Yahoo spot -> keyless daily rates."""
    ccy = currency.upper()
    if ccy == "USD":
        return 1.0
    try:
        return yahoo.fx_to_usd(ccy)
    except Exception:  # noqa: BLE001 — er-api / ECB carry it
        pass
    try:
        return fx.to_usd(ccy)
    except Exception:  # noqa: BLE001 — last resort, only with a key
        if not alphavantage.available():
            raise
    return alphavantage.fx_to_usd(ccy)
