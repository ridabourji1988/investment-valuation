"""FRED client (PRD §7) — keyless fredgraph CSV, cached.

Primary macro source. Some networks block/throttle the fredgraph host, so
every consumer must be prepared for this module to raise and fall back to the
keyless alternates (Yahoo rates, BLS labour data, ETF credit proxy) — see
macro_live.py. Short timeout keeps fallback latency bounded.
"""
from __future__ import annotations

import csv
import io
import time

from .cache import get_cached, http_get

FREDGRAPH = "https://fred.stlouisfed.org/graph/fredgraph.csv"
_TTL = 6 * 3600

# Circuit breaker: some networks black-hole the fredgraph host (connects hang
# until timeout). One tripped call marks FRED down for 10 minutes so the other
# series skip straight to their keyless fallbacks instead of serially timing
# out. It re-probes automatically after the window — no admin action.
_BREAKER = {"down_until": 0.0}
_BREAKER_WINDOW = 600.0


class FredUnavailable(RuntimeError):
    pass


def fetch_series(series_id: str) -> list[tuple[str, float]]:
    """[(date, value), ...] for a FRED series, skipping missing points."""
    def build():
        if time.time() < _BREAKER["down_until"]:
            raise FredUnavailable("FRED circuit breaker open")
        try:
            r = http_get(FREDGRAPH, params={"id": series_id},
                         headers={"User-Agent": "Mozilla/5.0 (ValueScope/1.0)"},
                         timeout=8, retries=0)
        except Exception as e:
            _BREAKER["down_until"] = time.time() + _BREAKER_WINDOW
            raise FredUnavailable(f"FRED unreachable: {e}") from e
        rows = list(csv.reader(io.StringIO(r.text)))
        out: list[tuple[str, float]] = []
        for row in rows[1:]:
            if len(row) < 2 or row[1] in (".", ""):
                continue
            try:
                out.append((row[0], float(row[1])))
            except ValueError:
                continue
        if not out:
            raise ValueError(f"no data for FRED series {series_id}")
        return out
    return get_cached(f"fred:{series_id}", _TTL, build)


def latest(series_id: str) -> tuple[str, float]:
    return fetch_series(series_id)[-1]


def last_n(series_id: str, n: int) -> list[float]:
    return [v for _, v in fetch_series(series_id)[-n:]]


def yoy(series_id: str) -> float:
    """Year-over-year change of a monthly index series."""
    data = fetch_series(series_id)
    if len(data) < 13:
        raise ValueError(f"not enough history for YoY on {series_id}")
    return data[-1][1] / data[-13][1] - 1.0
