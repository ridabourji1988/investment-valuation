"""FastAPI application: JSON API + served React frontend."""
from __future__ import annotations

import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import ENGINE_VERSION
from ..config import config
from ..registry import REGISTRY
from ..ai import narrator
from . import service


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=service.warm_cache, daemon=True).start()
    yield


app = FastAPI(title="ValueScope API", version=ENGINE_VERSION, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

_WEB_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "..", "web", "dist")
_WEB_DIST = os.path.abspath(_WEB_DIST)


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health() -> dict:
    s = service.status()
    return {
        "status": "ok",
        "engine_version": ENGINE_VERSION,
        "ai_ready": config.ai_ready(),
        "model": config.OPENROUTER_MODEL,
        "provider": config.OPENROUTER_PROVIDER,
        "data": {"universe": s["universe"], "ready": s["ready"],
                 "warming": s["warming"], "failed": s["failed"]},
    }


@app.get("/api/feed")
def get_feed() -> dict:
    return service.feed()


@app.get("/api/brief")
def get_brief() -> dict:
    f = service.feed()
    if f["count"] == 0:
        # Empty scan: nothing to narrate — skip the AI call entirely.
        reason = ("the first scan is still running" if f["warming"]
                  else "market data sources are unavailable right now")
        return {"payload": {"ideas": 0}, "block": {
            "text": f"No companies are ready yet — {reason}. Scanning resumes "
                    "automatically and results appear here as soon as live data flows.",
            "source": "engine", "ai": False}}
    scan = {
        "count": f["count"],
        "buys": f["buys"],
        "regime": f["regime"],
        "top": [{"ticker": r["ticker"], "margin_of_safety": r["margin_of_safety"]}
                for r in f["rows"][:2]],
    }
    return narrator.narrate_brief(scan)


def _analysis_or_http_error(ticker: str) -> dict:
    """404 for unknown tickers, 502 when a live source is down — never a fake."""
    try:
        return service.analyze_ticker(ticker)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:  # noqa: BLE001 — live-source failure
        raise HTTPException(status_code=502,
                            detail=f"live data unavailable for {ticker.upper()}: {e}")


@app.get("/api/asset/{ticker}")
def get_asset(ticker: str) -> dict:
    return _analysis_or_http_error(ticker)


@app.get("/api/asset/{ticker}/narrative")
def get_asset_narrative(ticker: str) -> dict:
    return narrator.narrate_asset(_analysis_or_http_error(ticker))


@app.get("/api/asset/{ticker}/calc/{metric}")
def get_calc(ticker: str, metric: str) -> dict:
    analysis = _analysis_or_http_error(ticker)
    trace = analysis["traces"].get(metric)
    if trace is None:
        raise HTTPException(status_code=404,
                            detail=f"no trace '{metric}'. Available: {list(analysis['traces'])}")
    return trace


@app.get("/api/search")
def search(q: str) -> dict:
    """Global symbol search: SEC filers (incl. foreign ADRs) analyzable now."""
    from ..data import provider
    if not q or len(q.strip()) < 1:
        return {"results": []}
    return {"results": provider.search(q.strip())}


@app.post("/api/retry")
def retry() -> dict:
    return service.retry_failed()


@app.get("/api/macro")
def get_macro() -> dict:
    try:
        return service.macro_dashboard()
    except Exception as e:  # noqa: BLE001 — live sources down; report, never fake
        raise HTTPException(status_code=503, detail=f"macro sources unavailable: {e}")


@app.get("/api/macro/rate-sensitivity")
def get_rate_sensitivity(bp: int = 50) -> dict:
    return {"bp": bp, "rows": service.rate_sensitivity_table(bp)}


@app.get("/api/formulas")
def get_formulas() -> dict:
    return {
        "engine_version": ENGINE_VERSION,
        "formulas": [
            {
                "formula_id": s.formula_id, "name": s.name, "expression": s.expression,
                "variables": s.variables, "citation": s.source_citation,
                "implementation": s.implementation_ref, "tests": s.tests, "version": s.version,
            }
            for s in REGISTRY.values()
        ],
    }


# --------------------------------------------------------------------------- #
# Frontend (built React app). API routes above take precedence.
# --------------------------------------------------------------------------- #
if os.path.isdir(_WEB_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(_WEB_DIST, "assets")), name="assets")

    @app.get("/")
    def _root() -> FileResponse:
        return FileResponse(os.path.join(_WEB_DIST, "index.html"))

    @app.exception_handler(404)
    async def _spa_fallback(request, exc):  # noqa: ANN001
        # Serve the SPA for non-API GET routes; keep API 404s as JSON.
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": exc.detail}, status_code=404)
        index = os.path.join(_WEB_DIST, "index.html")
        if os.path.exists(index):
            return FileResponse(index)
        return JSONResponse({"detail": "not found"}, status_code=404)
else:
    @app.get("/")
    def _root_no_web() -> dict:
        return {"detail": "Frontend not built. Run the web build. API is at /api/*.",
                "health": "/api/health"}
