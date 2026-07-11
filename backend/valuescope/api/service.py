"""Application service — scans the universe, builds the feed, macro dashboard
and Asset 360 payloads, with in-memory caching so the feed loads fast (PRD §11).
"""
from __future__ import annotations

import threading
import time

from ..config import config
from ..data import provider
from ..engine.analyze import analyze
from ..engine import macro as macro_mod

_CACHE: dict = {}
_LOCK = threading.Lock()
_TTL = 15 * 60  # 15 minutes


def _stamp(obj: dict) -> dict:
    obj["computed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return obj


def _regime_reduce() -> float:
    """Macro may only *reduce* suggested position size (PRD P4)."""
    label = macro_dashboard()["regime"]["result"]["label"]
    return {
        "Expansion": 1.0, "Late cycle": 0.8, "Slowdown": 0.6,
        "Contraction / Late-cycle stress": 0.4,
    }.get(label, 1.0)


def analyze_ticker(ticker: str, *, force: bool = False) -> dict:
    ticker = ticker.upper()
    key = f"analysis:{ticker}"
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and not force and (time.time() - hit["_ts"] < _TTL):
            return hit["data"]
    company = provider.get_company(ticker)
    data = analyze(company, mc_runs=config.MC_RUNS, regime_reduce=_regime_reduce())
    data["price_history"] = provider.get_price_history(ticker)
    with _LOCK:
        _CACHE[key] = {"_ts": time.time(), "data": data}
    return data


def scan_universe(*, force: bool = False) -> list[dict]:
    results = [analyze_ticker(t, force=force) for t in provider.list_tickers()]
    # Rank by margin of safety (PRD §3.1).
    results.sort(key=lambda r: r["margin_of_safety"], reverse=True)
    return results


def feed() -> dict:
    results = scan_universe()
    rows = []
    for r in results:
        under_over = r["margin_of_safety"]
        rows.append({
            "ticker": r["ticker"], "name": r["name"], "sector": r["sector"],
            "exchange": r["exchange"], "price": r["price"], "fair_value": r["fair_value"],
            "margin_of_safety": under_over, "verdict": r["verdict"]["action"],
            "quality": r["quality"], "data_quality": r["data_quality"],
            "spark": [p["close"] for p in r["price_history"][-40:]],
            "prev_close": r["price_history"][-2]["close"] if len(r["price_history"]) > 1 else r["price"],
        })
    buys = sum(1 for r in results if r["verdict"]["action"] == "BUY")
    dash = macro_dashboard()
    return _stamp({
        "rows": rows,
        "count": len(rows),
        "buys": buys,
        "regime": dash["regime"]["result"]["label"],
        "regime_implication": dash["regime"]["result"]["implication"],
        # From the cached dashboard — a direct provider.get_macro() here would
        # fire live FRED fetches on every feed request.
        "sources": dash.get("sources", {}),
    })


def macro_dashboard() -> dict:
    key = "macro"
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and (time.time() - hit["_ts"] < _TTL):
            return hit["data"]
    m = provider.get_macro()
    sahm = macro_mod.sahm_rule(m["unemployment_monthly"])
    regime = macro_mod.classify_regime(macro_mod.RegimeInputs(
        t10y3m=m["t10y3m"], pmi=m["pmi"], hy_oas=m["hy_oas"],
        sahm_triggered=sahm.result["triggered"],
    ))
    indicators = [
        {"id": "DGS10", "label": "10Y Treasury", "value": m["dgs10"], "unit": "%",
         "read": "Discount-rate anchor for every valuation."},
        {"id": "T10Y3M", "label": "Yield curve (10Y−3M)", "value": m["t10y3m"], "unit": "%",
         "read": "Negative warns of recession risk."},
        {"id": "PMI", "label": "ISM Manufacturing PMI", "value": m["pmi"], "unit": "idx",
         "read": "Below 50 signals factory contraction."},
        {"id": "HYOAS", "label": "High-yield spread", "value": m["hy_oas"], "unit": "%",
         "read": "Wider spreads mean credit stress."},
        {"id": "UNRATE", "label": "Unemployment", "value": m["unemployment_monthly"][-1] / 100.0,
         "unit": "%", "read": "Feeds the Sahm recession rule."},
        {"id": "CPI", "label": "CPI (YoY)", "value": m["cpi_yoy"], "unit": "%",
         "read": "Drives the Fed's rate path."},
    ]
    data = _stamp({
        "asof": m["asof"],
        "sahm": sahm.to_dict(),
        "regime": regime.to_dict(),
        "indicators": indicators,
        "fed": {
            "target_low": m["fed_target_low"], "target_high": m["fed_target_high"],
            "next_fomc": m["next_fomc"], "cpi_yoy": m["cpi_yoy"],
        },
        "sources": m.get("sources", {}),
    })
    with _LOCK:
        _CACHE[key] = {"_ts": time.time(), "data": data}
    return data


def rate_sensitivity_table(bp: int = 50) -> list[dict]:
    """Re-run every DCF at 10Y ±bp (PRD §3.7)."""
    from ..engine.dcf import DCFAssumptions
    out = []
    for t in provider.list_tickers():
        a = analyze_ticker(t)
        assum = DCFAssumptions(**a["dcf_assumptions"])
        r = macro_mod.rate_sensitivity(assum, bp=bp).result
        out.append({"ticker": t, "name": a["name"], "price": a["price"], **r})
    return out


def warm_cache() -> None:
    """Precompute the universe so the first feed request is instant."""
    try:
        scan_universe(force=True)
    except Exception:
        pass
