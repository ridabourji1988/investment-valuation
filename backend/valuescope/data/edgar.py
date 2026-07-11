"""SEC EDGAR client (PRD §7) — XBRL companyfacts, fully autonomous.

Ground-truth financial statement items. EDGAR requires a descriptive
User-Agent (default works; set VALUESCOPE_SEC_UA to your contact for courtesy)
and <= 10 req/s. The ticker map is cached 24h and companyfacts 12h, so steady
state traffic is a handful of requests per day.
"""
from __future__ import annotations

import datetime as dt

from ..config import config
from .cache import get_cached, http_get

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"

_TTL_TICKERS = 24 * 3600
_TTL_FACTS = 12 * 3600


def _headers() -> dict:
    return {"User-Agent": config.SEC_UA, "Accept-Encoding": "gzip, deflate"}


def _ticker_table() -> dict:
    def build():
        r = http_get(TICKERS_URL, headers=_headers(), timeout=30)
        table: dict = {}
        for row in r.json().values():
            # Duplicate tickers exist (e.g. financing subsidiaries); the
            # canonical operating company is listed first — keep it.
            table.setdefault(row["ticker"].upper(), (int(row["cik_str"]), row["title"]))
        return table
    return get_cached("edgar:tickers", _TTL_TICKERS, build)


def cik_for_ticker(ticker: str) -> int:
    table = _ticker_table()
    if ticker.upper() not in table:
        raise KeyError(f"ticker '{ticker}' not found on SEC EDGAR")
    return table[ticker.upper()][0]


def company_name(ticker: str) -> str:
    return _ticker_table().get(ticker.upper(), (0, ticker))[1]


def company_facts(ticker: str) -> dict:
    cik = cik_for_ticker(ticker)
    return get_cached(f"edgar:facts:{cik}", _TTL_FACTS,
                      lambda: http_get(FACTS_URL.format(cik=cik), headers=_headers(),
                                       timeout=40).json())


def company_profile(ticker: str) -> dict:
    """Sector (SIC description) and exchange from the EDGAR submissions API."""
    cik = cik_for_ticker(ticker)

    def build():
        d = http_get(SUBMISSIONS_URL.format(cik=cik), headers=_headers(), timeout=30).json()
        exchanges = [e for e in (d.get("exchanges") or []) if e]
        return {
            "sector": d.get("sicDescription") or "—",
            "exchange": exchanges[0] if exchanges else "US",
            "name": d.get("name") or company_name(ticker),
        }
    return get_cached(f"edgar:profile:{cik}", _TTL_TICKERS, build)


# --------------------------------------------------------------------------- #
# Annual (FY) series extraction
# --------------------------------------------------------------------------- #
def _duration_days(item: dict) -> int | None:
    try:
        start = dt.date.fromisoformat(item["start"])
        end = dt.date.fromisoformat(item["end"])
        return (end - start).days
    except (KeyError, ValueError):
        return None


def annual_series(facts: dict, concepts: list[str], *, unit: str = "USD",
                  flow: bool = False, n: int = 5) -> list[tuple[str, float]]:
    """Last n fiscal-year values [(end_date, value), ...] oldest-first.

    Taxonomy tags vary by filer AND migrate over time (e.g. NVDA moved to
    `Revenues` while META's `Revenues` went stale years ago), so every
    candidate concept is extracted and the one with the most RECENT fiscal
    year wins — not merely the first with any rows.

    flow=True keeps only ~annual durations so quarterly rows inside 10-K
    filings are excluded.
    """
    best: dict[str, dict] = {}
    for concept in concepts:
        try:
            items = facts["facts"]["us-gaap"][concept]["units"][unit]
        except KeyError:
            continue
        rows: dict[str, dict] = {}
        for it in items:
            if not str(it.get("form", "")).startswith("10-K"):
                continue
            if flow:
                d = _duration_days(it)
                if d is None or d < 300 or d > 400:
                    continue
            end = it.get("end")
            if not end:
                continue
            prev = rows.get(end)
            if prev is None or str(it.get("filed", "")) > str(prev.get("filed", "")):
                rows[end] = it
        if rows and (not best or max(rows) > max(best)
                     or (max(rows) == max(best) and len(rows) > len(best))):
            best = rows
    if not best:
        return []
    ordered = sorted(best)[-n:]
    return [(end, float(best[end]["val"])) for end in ordered]


def latest_annual(facts: dict, concepts: list[str], *, unit: str = "USD",
                  flow: bool = False) -> float | None:
    s = annual_series(facts, concepts, unit=unit, flow=flow, n=1)
    return s[-1][1] if s else None


def shares_outstanding(facts: dict) -> float | None:
    """Share count for per-share values: dei cover-page shares outstanding,
    falling back to diluted weighted-average shares (multi-class filers like
    Alphabet omit the dei tag) and then instant common shares outstanding."""
    try:
        items = [x for x in
                 facts["facts"]["dei"]["EntityCommonStockSharesOutstanding"]["units"]["shares"]
                 if x.get("val")]
        if items:
            return float(max(items, key=lambda x: str(x.get("end", "")))["val"])
    except KeyError:
        pass
    for concept, flow in (("WeightedAverageNumberOfDilutedSharesOutstanding", True),
                          ("CommonStockSharesOutstanding", False)):
        s = annual_series(facts, [concept], unit="shares", flow=flow, n=1)
        if s and s[-1][1] > 0:
            return s[-1][1]
    return None
