"""Unified data provider.

Serves the bundled demo dataset by default so the app is fully functional
offline. When VALUESCOPE_LIVE_DATA=1 it overlays live prices (Yahoo) and live
macro (FRED) on top, degrading gracefully to demo on any failure and flagging
data quality. Full live fundamentals assembly from EDGAR XBRL is experimental
and only used when a ticker is not in the demo universe.
"""
from __future__ import annotations

import copy

from ..config import config
from ..engine.analyze import CompanyInputs
from . import demo


def list_tickers() -> list[str]:
    return list(demo.UNIVERSE.keys())


def _refresh_price_live(company: CompanyInputs) -> CompanyInputs:
    try:
        from . import yahoo
        px = yahoo.latest_price(company.ticker)
        if px and px > 0:
            company = copy.copy(company)
            company.price = float(px)
            company.sources = {**company.sources, "prices": "Yahoo Finance (live)"}
    except Exception:
        company.sources = {**company.sources, "prices": "ValueScope demo (live fetch failed)"}
    return company


def get_company(ticker: str) -> CompanyInputs:
    ticker = ticker.upper()
    company = demo.UNIVERSE.get(ticker)
    if company is None:
        raise KeyError(f"Unknown ticker '{ticker}'. Known: {list_tickers()}")
    company = copy.copy(company)
    if config.LIVE_DATA:
        company = _refresh_price_live(company)
    return company


def get_price_history(ticker: str) -> list[dict]:
    ticker = ticker.upper()
    if config.LIVE_DATA:
        try:
            from . import yahoo
            hist = yahoo.fetch_chart(ticker, rng="1y")["history"]
            if hist:
                return hist
        except Exception:
            pass
    return demo.price_history(ticker)


def get_macro() -> dict:
    macro = dict(demo.DEMO_MACRO)
    if config.LIVE_DATA:
        try:
            from . import fred
            macro["unemployment_monthly"] = fred.last_n("UNRATE", 15) or macro["unemployment_monthly"]
            macro["t10y3m"] = fred.latest("T10Y3M")[1] / 100.0
            macro["hy_oas"] = fred.latest("BAMLH0A0HYM2")[1] / 100.0
            macro["dgs10"] = fred.latest("DGS10")[1] / 100.0
            macro["sources"] = {"macro": "FRED (live)"}
        except Exception:
            macro["sources"] = {"macro": "ValueScope demo (live fetch failed)"}
    return macro
