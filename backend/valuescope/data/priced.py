"""Priced assets — commodities and crypto (PRD extension, approved 2026-07-11).

These assets produce no cash flows, so they have NO intrinsic value and the
valuation engine never touches them. This module only *prices* them and gives
context (long-run nominal percentile, 1-year move) — every payload carries
that epistemic label. Sources are keyless with chains:

  crypto        Coinbase spot + daily candles (public API)
  commodities   FRED daily series -> Yahoo continuous futures
"""
from __future__ import annotations

import datetime as _dt
import time as _time

from . import fred, yahoo
from .cache import get_cached, http_get

_TTL = 30 * 60

EPISTEMICS = ("Commodities and crypto generate no cash flows, so they cannot be "
              "valued — only priced. Nothing here is a fair value or a verdict; "
              "the percentile is where today's nominal price sits in the asset's "
              "own trading history.")

CRYPTO = [
    {"id": "BTC", "label": "Bitcoin", "product": "BTC-USD"},
    {"id": "ETH", "label": "Ethereum", "product": "ETH-USD"},
    {"id": "SOL", "label": "Solana", "product": "SOL-USD"},
]
COMMODITIES = [
    {"id": "WTI", "label": "Crude oil (WTI)", "fred": "DCOILWTICO", "future": "CL=F", "unit": "US$/bbl"},
    {"id": "NATGAS", "label": "Natural gas (Henry Hub)", "fred": "DHHNGSP", "future": "NG=F", "unit": "US$/MMBtu"},
    {"id": "GOLD", "label": "Gold", "fred": None, "future": "GC=F", "unit": "US$/oz"},
    {"id": "SILVER", "label": "Silver", "fred": None, "future": "SI=F", "unit": "US$/oz"},
    {"id": "COPPER", "label": "Copper", "fred": None, "future": "HG=F", "unit": "US$/lb"},
]


def _coinbase_candles(product: str, *, chunks: int = 5) -> list[dict]:
    """~4 years of daily closes, oldest-first (public API caps 300/request)."""
    def build():
        rows: dict[str, float] = {}
        end = _dt.datetime.now(_dt.timezone.utc)
        for _ in range(chunks):
            start = end - _dt.timedelta(days=299)
            r = http_get(f"https://api.exchange.coinbase.com/products/{product}/candles",
                         params={"granularity": 86400,
                                 "start": start.isoformat(), "end": end.isoformat()},
                         timeout=15, retries=1)
            batch = r.json()
            if not batch:
                break
            for t, _lo, _hi, _op, close, *_ in batch:
                rows[_dt.date.fromtimestamp(t).isoformat()] = float(close)
            end = start
            _time.sleep(0.2)  # public rate limit courtesy
        if not rows:
            raise ValueError(f"no candles for {product}")
        return [{"date": d, "close": c} for d, c in sorted(rows.items())]
    return get_cached(f"coinbase:candles:{product}", _TTL, build)


def _coinbase_spot(product: str) -> float:
    def build():
        r = http_get(f"https://api.coinbase.com/v2/prices/{product}/spot",
                     timeout=10, retries=1)
        return float(r.json()["data"]["amount"])
    return get_cached(f"coinbase:spot:{product}", 5 * 60, build)


def _commodity_series(spec: dict) -> tuple[list[dict], str, str]:
    """(closes oldest-first, source label, source url) via FRED -> Yahoo."""
    if spec["fred"]:
        try:
            series = fred.fetch_series(spec["fred"])
            return ([{"date": d, "close": v} for d, v in series],
                    f"FRED {spec['fred']}",
                    f"https://fred.stlouisfed.org/series/{spec['fred']}")
        except Exception:  # noqa: BLE001 — futures carry it
            pass
    hist = yahoo.fetch_chart(spec["future"], rng="10y")["history"]
    return ([{"date": row["date"], "close": row["close"]} for row in hist],
            f"Yahoo {spec['future']} (continuous future)",
            f"https://finance.yahoo.com/quote/{spec['future'].replace('=', '%3D')}")


def _shape(label, unit, closes, price, source, url):
    values = [c["close"] for c in closes]
    below = sum(1 for v in values if v <= price)
    tail = closes[-260:]
    year_ago = tail[0]["close"] if tail else price
    return {
        "label": label, "unit": unit, "price": price,
        "asof": closes[-1]["date"],
        "percentile": below / len(values),
        "history_years": round(len(values) / 260, 1),
        "change_1y": price / year_ago - 1.0 if year_ago else None,
        "spark": [{"t": i, "close": c["close"], "date": c["date"]}
                  for i, c in enumerate(tail)],
        "source": source, "url": url,
    }


def snapshot() -> dict:
    """All priced assets; a failing source skips its asset honestly."""
    assets, skipped = [], []
    for c in CRYPTO:
        try:
            closes = _coinbase_candles(c["product"])
            price = _coinbase_spot(c["product"])
            assets.append({"id": c["id"], "kind": "crypto",
                           **_shape(c["label"], "US$", closes, price,
                                    "Coinbase spot/candles",
                                    f"https://www.coinbase.com/price/{c['label'].lower()}")})
        except Exception as e:  # noqa: BLE001
            skipped.append({"id": c["id"], "reason": str(e)[:120]})
    for m in COMMODITIES:
        try:
            closes, source, url = _commodity_series(m)
            price = closes[-1]["close"]
            assets.append({"id": m["id"], "kind": "commodity",
                           **_shape(m["label"], m["unit"], closes, price, source, url)})
        except Exception as e:  # noqa: BLE001
            skipped.append({"id": m["id"], "reason": str(e)[:120]})
    return {"epistemics": EPISTEMICS, "assets": assets, "skipped": skipped}
