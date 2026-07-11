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


# Annual-report forms: 10-K (domestic), 20-F (foreign private issuers, IFRS),
# 40-F (Canadian MJDS).
_ANNUAL_FORMS = ("10-K", "20-F", "40-F")
_NAMESPACES = ("us-gaap", "ifrs-full")


def _extract_rows(items: list, flow: bool) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for it in items:
        if not str(it.get("form", "")).startswith(_ANNUAL_FORMS):
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
    return rows


def _better(rows: dict, best: dict) -> bool:
    return bool(rows) and (not best or max(rows) > max(best)
                           or (max(rows) == max(best) and len(rows) > len(best)))


def annual_series(facts: dict, concepts: list[str], *, unit: str = "USD",
                  flow: bool = False, n: int = 5) -> list[tuple[str, float]]:
    """Last n fiscal-year values [(end_date, value), ...] oldest-first, in a
    FIXED unit, scanning both us-gaap and ifrs-full namespaces.

    Taxonomy tags vary by filer AND migrate over time (e.g. NVDA moved to
    `Revenues` while META's `Revenues` went stale years ago), so every
    candidate concept is extracted and the one with the most RECENT fiscal
    year wins — not merely the first with any rows.

    flow=True keeps only ~annual durations so quarterly rows inside annual
    filings are excluded.
    """
    best: dict[str, dict] = {}
    for ns in _NAMESPACES:
        for concept in concepts:
            try:
                items = facts["facts"][ns][concept]["units"][unit]
            except KeyError:
                continue
            rows = _extract_rows(items, flow)
            if _better(rows, best):
                best = rows
    if not best:
        return []
    ordered = sorted(best)[-n:]
    return [(end, float(best[end]["val"])) for end in ordered]


def monetary_series(facts: dict, concepts: list[str], *, currency: str | None = None,
                    flow: bool = False, n: int = 5) -> tuple[list[tuple[str, float]], str | None]:
    """Like annual_series but currency-aware: IFRS filers report in their home
    currency (SAP in EUR, TSM in TWD). Returns (series, currency).

    With `currency` set, only that unit is considered — pass the revenue
    currency to every later fetch so all statement items stay consistent.
    Without it, the best (most recent, then longest) series across all
    currency units wins.
    """
    best: dict[str, dict] = {}
    best_ccy: str | None = None
    for ns in _NAMESPACES:
        for concept in concepts:
            try:
                units = facts["facts"][ns][concept]["units"]
            except KeyError:
                continue
            for unit_name, items in units.items():
                if "/" in unit_name or len(unit_name) != 3:  # skip USD/shares, pure counts
                    continue
                if currency and unit_name.upper() != currency.upper():
                    continue
                rows = _extract_rows(items, flow)
                if _better(rows, best):
                    best, best_ccy = rows, unit_name.upper()
    if not best:
        return [], None
    ordered = sorted(best)[-n:]
    return [(end, float(best[end]["val"])) for end in ordered], best_ccy


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


def search_tickers(query: str, *, limit: int = 8) -> list[dict]:
    """Search SEC filers by ticker or company name (every hit is analyzable)."""
    q = query.strip().upper()
    if not q:
        return []
    table = _ticker_table()
    ql = q.lower()
    exact, prefix, name_match = [], [], []
    for tk, (cik, title) in table.items():
        if tk == q:
            exact.append((tk, title))
        elif tk.startswith(q):
            prefix.append((tk, title))
        # Word-prefix match on the company name ("sap" -> "SAP SE", not
        # "Che-sap-eake").
        elif any(w.startswith(ql) for w in title.lower().split()):
            name_match.append((tk, title))
    hits = exact + sorted(prefix)[:limit] + sorted(name_match, key=lambda x: len(x[1]))[:limit]
    return [{"ticker": tk, "name": title, "source": "edgar"} for tk, title in hits[:limit]]


def has_ticker(ticker: str) -> bool:
    return ticker.upper() in _ticker_table()
