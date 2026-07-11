"""Live macro snapshot — autonomous, keyless, per-series fallback chains.

Every series tries FRED first, then a keyless alternate. Each value carries its
source label so the UI can show exactly where a number came from. Nothing is
ever synthesised: a series with no reachable source is reported as None and
downstream signals treat it as "unavailable", never as a made-up value.

  dgs10        FRED DGS10            -> US Treasury yield curve -> Yahoo ^TNX
  t10y3m       FRED T10Y3M           -> Treasury/Yahoo 10Y − 3M
  unemployment FRED UNRATE           -> BLS LNS14000000 (public API v1)
  hy_oas       FRED BAMLH0A0HYM2     -> None (credit proxy: HYG vs IEF 3m
                                         return, Yahoo -> Cboe delayed)
  ip_yoy       FRED IPMAN YoY        -> None (signal skipped)
  cpi_yoy      FRED CPIAUCSL YoY     -> BLS CUUR0000SA0 YoY
  fed target   FRED DFEDTARU/DFEDTARL-> 3M T-bill proxy (Treasury/Yahoo)
"""
from __future__ import annotations

import datetime as dt

from . import bls, fred, market, treasury, yahoo

# Public FOMC calendar (reference data, not market data).
FOMC_DATES = [
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
    "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-16",
]


def _next_fomc(today: dt.date) -> str:
    for d in FOMC_DATES:
        if dt.date.fromisoformat(d) >= today:
            return d
    return FOMC_DATES[-1]


def _try(fn, *args):
    try:
        return fn(*args)
    except Exception:  # noqa: BLE001 — any source failure means "try next"
        return None


def snapshot() -> dict:
    """Assemble the full macro dict. Raises only if BOTH sources fail for the
    essential series (10Y yield and unemployment)."""
    sources: dict[str, str] = {}

    # 10Y — anchor for every valuation; essential.
    dgs10 = _try(lambda: fred.latest("DGS10")[1] / 100.0)
    if dgs10 is not None:
        sources["dgs10"] = "FRED DGS10"
    elif (dgs10 := _try(treasury.yield_10y)) is not None:
        sources["dgs10"] = "U.S. Treasury daily par yield curve"
    else:
        dgs10 = yahoo.yield_10y()  # raises if also unreachable — genuinely stuck
        sources["dgs10"] = "Yahoo ^TNX (10Y yield)"

    # Yield curve 10Y - 3M
    t10y3m = _try(lambda: fred.latest("T10Y3M")[1] / 100.0)
    if t10y3m is not None:
        sources["t10y3m"] = "FRED T10Y3M"
    else:
        t3m = _try(treasury.yield_3m) or _try(yahoo.yield_3m)
        t10y3m = (dgs10 - t3m) if t3m is not None else None
        sources["t10y3m"] = ("10Y − 3M (Treasury/market data)"
                             if t10y3m is not None else "unavailable")

    # Unemployment (Sahm rule needs >= 15 monthly points); essential.
    unemployment = _try(lambda: fred.last_n("UNRATE", 15))
    if unemployment and len(unemployment) >= 15:
        sources["unemployment"] = "FRED UNRATE"
    else:
        unemployment = bls.unemployment_monthly(15)  # raises if unreachable
        sources["unemployment"] = "BLS LNS14000000"

    # High-yield credit
    hy_oas = _try(lambda: fred.latest("BAMLH0A0HYM2")[1] / 100.0)
    credit_proxy = None
    if hy_oas is not None:
        sources["credit"] = "FRED BAMLH0A0HYM2 (HY OAS)"
    else:
        credit_proxy = _try(market.credit_stress_proxy)
        sources["credit"] = (credit_proxy["source"] if credit_proxy is not None
                             else "unavailable")

    # Industrial production YoY (manufacturing-cycle signal)
    ip_yoy = _try(lambda: fred.yoy("IPMAN"))
    sources["ip_yoy"] = "FRED IPMAN (YoY)" if ip_yoy is not None else "unavailable"

    # CPI YoY
    cpi_yoy = _try(lambda: fred.yoy("CPIAUCSL"))
    if cpi_yoy is not None:
        sources["cpi"] = "FRED CPIAUCSL (YoY)"
    else:
        cpi_yoy = _try(bls.cpi_yoy)
        sources["cpi"] = "BLS CUUR0000SA0 (YoY)" if cpi_yoy is not None else "unavailable"

    # Fed target range
    lo = _try(lambda: fred.latest("DFEDTARL")[1] / 100.0)
    hi = _try(lambda: fred.latest("DFEDTARU")[1] / 100.0)
    if lo is not None and hi is not None:
        sources["fed"] = "FRED DFEDTARL/DFEDTARU"
    else:
        t3m = _try(treasury.yield_3m) or _try(yahoo.yield_3m)
        if t3m is not None:
            lo, hi = round(t3m - 0.00125, 4), round(t3m + 0.00125, 4)
            sources["fed"] = "3M T-bill proxy for the policy rate"
        else:
            lo = hi = None
            sources["fed"] = "unavailable"

    today = dt.date.today()
    return {
        "asof": today.isoformat(),
        "dgs10": dgs10,
        "t10y3m": t10y3m,
        "unemployment_monthly": unemployment,
        "hy_oas": hy_oas,
        "credit_proxy": credit_proxy,   # {"stress": bool, "hyg_minus_ief_3m": float} | None
        "ip_yoy": ip_yoy,
        "cpi_yoy": cpi_yoy,
        "fed_target_low": lo,
        "fed_target_high": hi,
        "next_fomc": _next_fomc(today),
        "sources": sources,
    }
