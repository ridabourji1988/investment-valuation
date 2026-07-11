"""BLS public API v1 (keyless) — fallback source for unemployment and CPI.

Used when FRED's CSV host is unreachable (some networks block it). v1 needs no
registration; results are cached for hours so the 25 req/day courtesy limit is
never approached.
"""
from __future__ import annotations

import datetime as dt

import httpx

API = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
UNRATE_SERIES = "LNS14000000"   # unemployment rate, seasonally adjusted
CPI_SERIES = "CUUR0000SA0"      # CPI-U, all items, NSA index


def _fetch(series_ids: list[str], years_back: int = 2) -> dict:
    end = dt.date.today().year
    r = httpx.post(API, json={"seriesid": series_ids, "startyear": str(end - years_back),
                              "endyear": str(end)},
                   headers={"Content-Type": "application/json"}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "REQUEST_SUCCEEDED":
        raise ValueError(f"BLS error: {data.get('message')}")
    out = {}
    for s in data["Results"]["series"]:
        pts = []
        for p in s["data"]:
            if not p["period"].startswith("M"):
                continue
            try:
                pts.append((p["year"], p["period"], float(p["value"])))
            except ValueError:  # BLS marks missing months with '-'
                continue
        pts.sort()  # chronological (year, M01..M12)
        out[s["seriesID"]] = pts
    return out


def unemployment_monthly(n: int = 15) -> list[float]:
    pts = _fetch([UNRATE_SERIES])[UNRATE_SERIES]
    if len(pts) < n:
        raise ValueError(f"BLS returned only {len(pts)} unemployment points")
    return [v for _, _, v in pts[-n:]]


def cpi_yoy() -> float:
    pts = _fetch([CPI_SERIES])[CPI_SERIES]
    if len(pts) < 13:
        raise ValueError("not enough CPI history for YoY")
    return pts[-1][2] / pts[-13][2] - 1.0
