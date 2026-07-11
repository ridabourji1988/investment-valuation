"""Keyless FX fallback chain for statement-currency conversion.

open.er-api.com serves daily USD-base rates for ~160 currencies with no key
(covers TWD/DKK/CNY/INR/BRL — everything the ADR universe files in);
frankfurter.dev (ECB reference rates) backs it up for major currencies.
Daily rates are adequate here: they convert annual IFRS statements, not
intraday positions.
"""
from __future__ import annotations

from .cache import get_cached, http_get

_ERAPI = "https://open.er-api.com/v6/latest/USD"
_FRANKFURTER = "https://api.frankfurter.dev/v1/latest"
_TTL = 6 * 3600


def _erapi_rates() -> dict:
    def build():
        r = http_get(_ERAPI, timeout=15, retries=1)
        body = r.json()
        if body.get("result") != "success" or not body.get("rates"):
            raise ValueError("er-api returned no rates")
        return body["rates"]  # 1 USD -> {ccy: amount}
    return get_cached("fx:erapi:usd", _TTL, build)


def _frankfurter_to_usd(ccy: str) -> float:
    def build():
        r = http_get(_FRANKFURTER, params={"base": ccy, "symbols": "USD"},
                     timeout=15, retries=1)
        rate = r.json()["rates"]["USD"]
        if not rate or rate <= 0:
            raise ValueError(f"frankfurter has no USD rate for {ccy}")
        return float(rate)
    return get_cached(f"fx:frankfurter:{ccy}", _TTL, build)


def to_usd(currency: str) -> float:
    """Spot(ish) rate: 1 unit of `currency` in US$."""
    ccy = currency.upper()
    if ccy == "USD":
        return 1.0
    try:
        rate = _erapi_rates().get(ccy)
        if rate and rate > 0:
            return 1.0 / float(rate)
    except Exception:  # noqa: BLE001 — try the next source
        pass
    return _frankfurter_to_usd(ccy)
