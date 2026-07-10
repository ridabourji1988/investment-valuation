"""FRED client (PRD §7).

Uses the public fredgraph CSV endpoint (no API key required) so the macro
module works out of the box. Every value is returned with its asof date.
"""
from __future__ import annotations

import csv
import io

import httpx

FREDGRAPH = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def fetch_series(series_id: str, *, timeout: float = 15.0) -> list[tuple[str, float]]:
    """Return [(date, value), ...] for a FRED series, skipping missing points."""
    r = httpx.get(FREDGRAPH, params={"id": series_id}, timeout=timeout,
                  headers={"User-Agent": "ValueScope/1.0"})
    r.raise_for_status()
    rows = list(csv.reader(io.StringIO(r.text)))
    out: list[tuple[str, float]] = []
    for row in rows[1:]:
        if len(row) < 2 or row[1] in (".", ""):
            continue
        try:
            out.append((row[0], float(row[1])))
        except ValueError:
            continue
    return out


def latest(series_id: str) -> tuple[str, float]:
    data = fetch_series(series_id)
    if not data:
        raise ValueError(f"no data for FRED series {series_id}")
    return data[-1]


def last_n(series_id: str, n: int) -> list[float]:
    return [v for _, v in fetch_series(series_id)[-n:]]
