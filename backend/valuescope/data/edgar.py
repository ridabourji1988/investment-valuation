"""SEC EDGAR client (PRD §7) — XBRL companyfacts.

Ground-truth financial statement items. EDGAR requires a descriptive
User-Agent and rate-limit courtesy (<= 10 req/s). Set VALUESCOPE_SEC_UA to a
real contact string when running live.
"""
from __future__ import annotations

import os

import httpx

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"


def _ua() -> str:
    return os.getenv("VALUESCOPE_SEC_UA", "ValueScope research contact@example.com")


def _headers() -> dict:
    return {"User-Agent": _ua(), "Accept-Encoding": "gzip, deflate"}


def cik_for_ticker(ticker: str, *, timeout: float = 15.0) -> int | None:
    r = httpx.get(TICKERS_URL, headers=_headers(), timeout=timeout)
    r.raise_for_status()
    for row in r.json().values():
        if row["ticker"].upper() == ticker.upper():
            return int(row["cik_str"])
    return None


def company_facts(cik: int, *, timeout: float = 20.0) -> dict:
    r = httpx.get(FACTS_URL.format(cik=cik), headers=_headers(), timeout=timeout)
    r.raise_for_status()
    return r.json()


def latest_fact(facts: dict, concept: str, unit: str = "USD") -> dict | None:
    """Return the most recent annual (FY) value for a us-gaap concept, with its
    filing date and period, or None if unavailable."""
    try:
        items = facts["facts"]["us-gaap"][concept]["units"][unit]
    except KeyError:
        return None
    annual = [x for x in items if x.get("form") in ("10-K", "10-K/A") and x.get("fp") == "FY"]
    pool = annual or items
    if not pool:
        return None
    best = max(pool, key=lambda x: x.get("end", ""))
    return {"value": best["value"], "end": best.get("end"), "filed": best.get("filed"),
            "form": best.get("form"), "concept": concept}
