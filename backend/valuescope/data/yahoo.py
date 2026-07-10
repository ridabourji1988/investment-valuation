"""Yahoo Finance client (PRD §7) — prices & quick fundamentals.

Uses the public chart endpoint. Cross-check vs. EDGAR is the caller's job; a
>5% discrepancy should raise a data-quality flag.
"""
from __future__ import annotations

import httpx

CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_HEADERS = {"User-Agent": "Mozilla/5.0 (ValueScope/1.0)"}


def fetch_chart(symbol: str, *, rng: str = "1y", interval: str = "1d",
                timeout: float = 15.0) -> dict:
    r = httpx.get(CHART.format(symbol=symbol), params={"range": rng, "interval": interval},
                  headers=_HEADERS, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    result = data["chart"]["result"][0]
    meta = result["meta"]
    ts = result.get("timestamp", []) or []
    closes = result["indicators"]["quote"][0].get("close", []) or []
    series = [{"t": i, "close": round(c, 4)} for i, c in enumerate(closes) if c is not None]
    return {
        "symbol": symbol,
        "price": meta.get("regularMarketPrice"),
        "currency": meta.get("currency", "USD"),
        "exchange": meta.get("fullExchangeName", ""),
        "history": series,
    }


def latest_price(symbol: str) -> float:
    return float(fetch_chart(symbol, rng="5d")["price"])
