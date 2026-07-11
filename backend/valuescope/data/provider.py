"""Unified data provider — 100% live, zero synthetic data, zero configuration.

Universe comes from config (sensible default, env-overridable). Fundamentals
come from SEC EDGAR, prices/beta from Yahoo, macro from FRED with keyless
fallbacks (Yahoo rates, BLS, ETF credit proxy). Everything is TTL-cached at
the source layer; a source failure raises so callers surface/skip honestly —
nothing ever falls back to made-up numbers.
"""
from __future__ import annotations

from ..config import config
from ..engine.analyze import CompanyInputs
from . import live, macro_live, market, yahoo
from .cache import get_cached

_TTL_COMPANY = 15 * 60   # price freshness; EDGAR layer caches facts 12h anyway
_TTL_MACRO = 60 * 60


def list_tickers() -> list[str]:
    return list(config.UNIVERSE)


def get_macro() -> dict:
    return get_cached("macro:snapshot", _TTL_MACRO, macro_live.snapshot)


def get_company(ticker: str) -> CompanyInputs:
    ticker = ticker.upper()
    rf = get_macro()["dgs10"]
    return get_cached(f"company:{ticker}", _TTL_COMPANY,
                      lambda: live.build_company(ticker, risk_free=rf))


def get_price_history(ticker: str) -> list[dict]:
    return market.price_history(ticker.upper())


def search(query: str, *, limit: int = 8) -> list[dict]:
    """Global symbol search. SEC filers (incl. foreign ADRs on 20-F) are
    analyzable now; other listings are shown but marked unsupported."""
    from . import edgar as _edgar
    out, seen = [], set()
    for hit in _edgar.search_tickers(query, limit=limit):
        seen.add(hit["ticker"])
        out.append({**hit, "exchange": "", "analyzable": True})
    try:
        for hit in yahoo.search(query, count=limit):
            tk = (hit["ticker"] or "").upper()
            if not tk or tk in seen:
                continue
            seen.add(tk)
            analyzable = _edgar.has_ticker(tk)
            out.append({"ticker": tk, "name": hit["name"], "exchange": hit["exchange"],
                        "source": "yahoo", "analyzable": analyzable})
    except Exception:  # noqa: BLE001 — EDGAR-only results still useful
        pass
    return out[:limit]
