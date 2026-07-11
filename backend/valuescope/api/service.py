"""Application service — scans the universe, builds the feed, macro dashboard
and Asset 360 payloads.

Autonomy model (PRD §11): a background warm thread analyses the whole universe
at startup; the feed serves whatever is ready immediately (with a `warming`
flag while the first pass runs) and refreshes stale entries in the background.
A ticker whose sources fail is skipped and reported — never faked.
"""
from __future__ import annotations

import threading
import time

from ..config import config
from ..data import provider
from ..engine.analyze import analyze
from ..engine import macro as macro_mod

_TTL = 15 * 60  # analysis freshness

_CACHE: dict = {}                 # key -> {"_ts": float, "data": dict}
_CACHE_LOCK = threading.Lock()
_TICKER_LOCKS: dict = {}          # per-ticker compute locks
_TICKER_LOCKS_GUARD = threading.Lock()
_WARM = {"started": False, "attempted": set(), "failed": {}}
_MACRO_KICK = {"running": False}


def _stamp(obj: dict) -> dict:
    obj["computed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return obj


def _lock_for(ticker: str) -> threading.Lock:
    with _TICKER_LOCKS_GUARD:
        return _TICKER_LOCKS.setdefault(ticker, threading.Lock())


def _regime_reduce() -> float:
    """Macro may only *reduce* suggested position size (PRD P4)."""
    try:
        label = macro_dashboard()["regime"]["result"]["label"]
    except Exception:  # macro sources down -> no reduction, verdicts unaffected
        return 1.0
    return {
        "Expansion": 1.0, "Late cycle": 0.8, "Slowdown": 0.6,
        "Contraction / Late-cycle stress": 0.4,
    }.get(label, 1.0)


def analyze_ticker(ticker: str, *, force: bool = False) -> dict:
    """Blocking compute with per-ticker lock and TTL cache."""
    ticker = ticker.upper()
    key = f"analysis:{ticker}"
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
    if hit and not force and (time.time() - hit["_ts"] < _TTL):
        return hit["data"]
    with _lock_for(ticker):
        with _CACHE_LOCK:  # another thread may have filled it while we waited
            hit = _CACHE.get(key)
        if hit and not force and (time.time() - hit["_ts"] < _TTL):
            return hit["data"]
        company = provider.get_company(ticker)
        data = analyze(company, mc_runs=config.MC_RUNS, regime_reduce=_regime_reduce())
        data["price_history"] = provider.get_price_history(ticker)
        data = _stamp(data)
        with _CACHE_LOCK:
            _CACHE[key] = {"_ts": time.time(), "data": data}
        _WARM["failed"].pop(ticker, None)
        return data


def peek_analysis(ticker: str) -> dict | None:
    """Cached analysis at any age (stale beats blocking the feed)."""
    with _CACHE_LOCK:
        hit = _CACHE.get(f"analysis:{ticker.upper()}")
    return hit["data"] if hit else None


def _warm_one(ticker: str, force: bool = False) -> None:
    try:
        analyze_ticker(ticker, force=force)
    except Exception as e:  # noqa: BLE001 — recorded, retried next cycle
        _WARM["failed"][ticker] = str(e)
    finally:
        _WARM["attempted"].add(ticker)


def _warm_all() -> None:
    for t in provider.list_tickers():
        _warm_one(t)
        time.sleep(1.0)  # courtesy pacing — burst scans trip source throttles


def _watchdog_loop() -> None:
    """Self-healing: retry tickers that failed (source outage, rate limit)
    every 5 minutes, forever — first check after 1 minute so short outages
    recover fast. Autonomy means failures recover without anyone touching
    anything."""
    delay = 60
    while True:
        time.sleep(delay)
        delay = 300
        try:
            missing = [t for t in provider.list_tickers() if peek_analysis(t) is None]
            for t in missing:
                _warm_one(t)
                time.sleep(0.5)
        except Exception:  # noqa: BLE001 — watchdog must never die
            pass


def ensure_warming() -> None:
    if not _WARM["started"]:
        _WARM["started"] = True
        threading.Thread(target=_warm_all, daemon=True).start()
        threading.Thread(target=_watchdog_loop, daemon=True).start()


def warm_cache() -> None:
    ensure_warming()


_REFRESH = {"queue": set(), "running": False, "lock": threading.Lock()}


def _refresh_async(ticker: str) -> None:
    """Queue a background refresh. Single-flight: one worker drains the queue
    serially — 20 tickers going stale together must not spawn 20 concurrent
    Monte Carlo recomputes and starve every API request (GIL)."""
    with _REFRESH["lock"]:
        _REFRESH["queue"].add(ticker)
        if _REFRESH["running"]:
            return
        _REFRESH["running"] = True
    threading.Thread(target=_drain_refresh, daemon=True).start()


def _drain_refresh() -> None:
    while True:
        with _REFRESH["lock"]:
            if not _REFRESH["queue"]:
                _REFRESH["running"] = False
                return
            t = _REFRESH["queue"].pop()
        _warm_one(t, force=True)
        time.sleep(0.25)


def _stale_after(ticker: str) -> float:
    """Per-ticker TTL with deterministic jitter (up to +4 min) so entries
    warmed together don't all expire together."""
    return _TTL + (hash(ticker) % 240)


def feed() -> dict:
    """Non-blocking: serves every ready ticker now, warms/refreshes the rest
    in the background."""
    ensure_warming()
    universe = provider.list_tickers()
    rows, ready = [], 0
    now = time.time()
    for t in universe:
        a = peek_analysis(t)
        if a is None:
            continue
        ready += 1
        with _CACHE_LOCK:
            age = now - _CACHE[f"analysis:{t}"]["_ts"]
        if age > _stale_after(t):
            _refresh_async(t)  # serve stale, refresh in background
        hist = a["price_history"]
        rows.append({
            "ticker": a["ticker"], "name": a["name"], "sector": a["sector"],
            "exchange": a["exchange"], "price": a["price"], "fair_value": a["fair_value"],
            "margin_of_safety": a["margin_of_safety"], "verdict": a["verdict"]["action"],
            "quality": a["quality"], "data_quality": a["data_quality"],
            "spark": [p["close"] for p in hist[-40:]],
            "prev_close": hist[-2]["close"] if len(hist) > 1 else a["price"],
        })
    rows.sort(key=lambda r: r["margin_of_safety"], reverse=True)

    # Macro must never block the feed: the first computation can spend many
    # seconds in source timeouts, so serve whatever is cached (any age) and
    # refresh in the background.
    regime_label, regime_impl, sources = "—", "Macro sources warming…", {}
    dash = _macro_cached_or_kick()
    if dash:
        regime_label = dash["regime"]["result"]["label"]
        regime_impl = dash["regime"]["result"]["implication"]
        sources = dash.get("sources", {})

    attempted_all = _WARM["attempted"] >= set(universe)
    return _stamp({
        "rows": rows,
        "count": len(rows),
        "buys": sum(1 for r in rows if r["verdict"] == "BUY"),
        "universe": len(universe),
        "warming": not attempted_all,
        "failed": dict(_WARM["failed"]),
        "regime": regime_label,
        "regime_implication": regime_impl,
        "sources": sources,
    })


def _macro_cached_or_kick() -> dict | None:
    """Cached macro dashboard at any age; when missing/stale, computes it in a
    background thread (single-flight) instead of blocking the caller."""
    with _CACHE_LOCK:
        hit = _CACHE.get("macro-dash")
    if hit and (time.time() - hit["_ts"] < _TTL):
        return hit["data"]
    if not _MACRO_KICK["running"]:
        _MACRO_KICK["running"] = True

        def run():
            try:
                macro_dashboard()
            except Exception:  # noqa: BLE001 — sources down; retried next feed
                pass
            finally:
                _MACRO_KICK["running"] = False
        threading.Thread(target=run, daemon=True).start()
    return hit["data"] if hit else None  # stale beats nothing


def macro_dashboard() -> dict:
    key = "macro-dash"
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
    if hit and (time.time() - hit["_ts"] < _TTL):
        return hit["data"]
    m = provider.get_macro()
    sahm = macro_mod.sahm_rule(m["unemployment_monthly"])
    credit_proxy = m.get("credit_proxy") or {}
    regime = macro_mod.classify_regime(macro_mod.RegimeInputs(
        t10y3m=m["t10y3m"], ip_yoy=m.get("ip_yoy"), hy_oas=m.get("hy_oas"),
        sahm_triggered=sahm.result["triggered"],
        credit_proxy_stress=credit_proxy.get("stress"),
    ))
    links = m.get("links", {})
    indicators = [
        {"id": "DGS10", "label": "10Y Treasury", "value": m["dgs10"], "unit": "%",
         "read": "Discount-rate anchor for every valuation.",
         "source": m["sources"].get("dgs10"), "url": links.get("dgs10")},
        {"id": "T10Y3M", "label": "Yield curve (10Y−3M)", "value": m["t10y3m"], "unit": "%",
         "read": "Negative warns of recession risk.",
         "source": m["sources"].get("t10y3m"), "url": links.get("t10y3m")},
        {"id": "IPMAN", "label": "Industrial production (YoY)", "value": m.get("ip_yoy"),
         "unit": "%", "read": "Below zero signals factory contraction.",
         "source": m["sources"].get("ip_yoy"), "url": links.get("ip_yoy")},
        {"id": "HYOAS", "label": "High-yield spread",
         "value": m.get("hy_oas") if m.get("hy_oas") is not None
         else credit_proxy.get("hyg_minus_ief_3m"),
         "unit": "%", "read": "Wider spreads mean credit stress."
         if m.get("hy_oas") is not None else "HYG−IEF 3-month proxy; strongly negative means stress.",
         "source": m["sources"].get("credit"), "url": links.get("credit")},
        {"id": "UNRATE", "label": "Unemployment",
         "value": m["unemployment_monthly"][-1] / 100.0,
         "unit": "%", "read": "Feeds the Sahm recession rule.",
         "source": m["sources"].get("unemployment"), "url": links.get("unemployment")},
        {"id": "CPI", "label": "CPI (YoY)", "value": m.get("cpi_yoy"), "unit": "%",
         "read": "Drives the Fed's rate path.",
         "source": m["sources"].get("cpi"), "url": links.get("cpi")},
    ]
    data = _stamp({
        "asof": m["asof"],
        "sahm": sahm.to_dict(),
        "regime": regime.to_dict(),
        "indicators": indicators,
        "fed": {
            "target_low": m.get("fed_target_low"), "target_high": m.get("fed_target_high"),
            "next_fomc": m.get("next_fomc"), "cpi_yoy": m.get("cpi_yoy"),
        },
        "upcoming_events": m.get("upcoming_events", []),
        "sources": m.get("sources", {}),
    })
    with _CACHE_LOCK:
        _CACHE[key] = {"_ts": time.time(), "data": data}
    return data


def rate_sensitivity_table(bp: int = 50) -> list[dict]:
    """Re-run every *ready* DCF at 10Y ±bp (PRD §3.7)."""
    from ..engine.dcf import DCFAssumptions
    out = []
    for t in provider.list_tickers():
        a = peek_analysis(t)
        if a is None:
            continue
        assum = DCFAssumptions(**a["dcf_assumptions"])
        r = macro_mod.rate_sensitivity(assum, bp=bp).result
        out.append({"ticker": t, "name": a["name"], "price": a["price"], **r})
    return out


def retry_failed() -> dict:
    """User-triggered: clear failures and re-scan everything missing NOW
    (the watchdog does this every 5 minutes anyway)."""
    _WARM["failed"] = {}
    missing = [t for t in provider.list_tickers() if peek_analysis(t) is None]
    for t in missing:
        _refresh_async(t)
    return {"retrying": missing}


def status() -> dict:
    universe = provider.list_tickers()
    return {
        "universe": universe,
        "ready": sorted(t for t in universe if peek_analysis(t) is not None),
        "failed": dict(_WARM["failed"]),
        "warming": not (_WARM["attempted"] >= set(universe)),
    }


def reset_for_tests() -> None:
    """Test hook: clear caches and warm state."""
    with _CACHE_LOCK:
        _CACHE.clear()
    _WARM["started"] = False
    _WARM["attempted"] = set()
    _WARM["failed"] = {}
    _MACRO_KICK["running"] = False
    with _REFRESH["lock"]:
        _REFRESH["queue"] = set()
        _REFRESH["running"] = False
