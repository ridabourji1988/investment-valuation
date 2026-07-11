# ValueScope

**Open-source, AI-explained investment valuation for retail investors.** ValueScope
values companies with Aswath Damodaran's methodologies, adds macro/cycle context,
and translates all of it into plain English — with **no unexplained number**: every
metric is tappable to reveal its full calculation (formula → inputs with sources →
step-by-step arithmetic → the book the formula comes from).

- **Deterministic math, narrated by AI.** All numbers come from a versioned Python
  calculation engine. The AI layer only explains; it never computes or invents figures
  (a guardrail rejects any generated number not present in the engine's output).
- **Canonical sources only.** Every formula cites its source (Damodaran, Graham,
  Greenblatt, Piotroski, Altman, Beneish, Sahm…). CI fails if a formula lacks a
  citation or a unit test reproducing a worked example.
- **Apple-Stocks-style UI**, European number formatting, "Show Calculation" everywhere.

> Educational research tool. **Not investment advice.** All valuations are estimates
> that depend on assumptions. No orders are ever executed.

---

## What's implemented

| Layer | Contents |
|-------|----------|
| **Engine** (`backend/valuescope/engine`) | 10-year FCFF DCF (Damodaran *ginzu*), terminal value, reverse DCF (bisection), Monte Carlo (≥10k runs), CAPM, bottom-up beta (Hamada), WACC, margin of safety, NCAV net-nets, Magic Formula, Piotroski F-Score, Altman Z-Score, Beneish M-Score, quality composite, Sahm rule, regime classifier, rate-sensitivity, verdict rules + value-trap check. Every metric emits a **CalculationTrace**. |
| **Registry** (`backend/valuescope/registry/formulas.yaml`) | Single source of truth: `formula_id → expression, variables, citation, implementation, tests`. |
| **Data** (`backend/valuescope/data`) | **100% live, keyless, autonomous, global.** SEC EDGAR XBRL fundamentals for US filers (10-K, us-gaap) **and European/emerging-market companies via their US listings** (20-F/40-F, ifrs-full, home-currency statements converted to US$ at live FX). Multi-tag candidates, tag-migration detection, derived-EBIT fallbacks, ADR-ratio-aware share counts. Yahoo prices + 2Y regression beta vs the S&P 500; macro from FRED with automatic keyless fallbacks (Yahoo Treasury tickers, BLS public API, HYG−IEF credit proxy) behind a circuit breaker. Disk-persisted cache + a 5-minute self-healing watchdog. Zero synthetic data: a company whose filings lack required tags is skipped and reported. |
| **AI** (`backend/valuescope/ai`) | OpenRouter client (**GLM 5.2 via StreamLake**, implicit prompt caching for the discount) + number-validator guardrail + deterministic fallback. |
| **API** (`backend/valuescope/api`) | FastAPI: `/api/feed`, `/api/asset/{t}`, `/api/asset/{t}/calc/{metric}`, `/api/macro`, `/api/macro/rate-sensitivity`, `/api/formulas`, `/api/brief`, `/api/health`. |
| **Web** (`web/`) | React + Vite + Recharts. Opportunity Feed, Asset 360 (with live-slider DCF, Reverse DCF, Monte Carlo tabs), Show Calculation sheets with recursive drill-down, Macro & Cycle dashboard, Learn/Methodology generated from the registry. |

## Tested math

The acceptance bar is correctness of the financial calculations. **66 tests pass**,
each reproducing a textbook/Damodaran worked example within tolerance (API tests run
offline against fixtures; the live pipeline is verified separately):

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest            # 66 passed
```

Highlights: the DCF collapses to a closed-form perpetuity `NOPAT/WACC` under zero
growth; reverse DCF round-trips growth→price→growth; CAPM/WACC/beta/Altman/Beneish
reproduce hand-computed values; the registry test fails CI if any formula lacks a
citation or a test.

## Run locally

**Backend + built frontend (one service):**
```bash
cd web && npm ci && npm run build          # outputs web/dist
cd ../backend && . .venv/bin/activate
uvicorn valuescope.api.app:app --port 8000 # http://localhost:8000
```

**Frontend dev server (hot reload, proxies /api → :8000):**
```bash
cd web && npm run dev                       # http://localhost:5173
```

**Docker (mirrors production):**
```bash
docker build -t valuescope .
docker run -p 8000:8000 --env-file .env valuescope
```

## Deploy on Railway

1. Push this repo to GitHub and create a Railway project from it. Railway detects the
   **`Dockerfile`** (config in `railway.json`, health check at `/api/health`).
2. In **Project → Variables**, set **one variable**:
   - `OPENROUTER_API_KEY` — your OpenRouter key (comma-separate multiple keys).
   Everything else has autonomous defaults (`z-ai/glm-5.2` via `streamlake`,
   temperature 0, 20-ticker global universe, keyless data pipeline) — see
   `.env.example` for optional overrides.
3. Deploy. Railway injects `PORT`; the server binds `0.0.0.0:$PORT` automatically.
   The single service serves both the API and the React app.

At startup the server scans the whole universe in the background (SEC filings, prices,
macro). The default universe covers the US, Europe and emerging markets (20 names);
**any other SEC filer — including foreign ADRs — is analyzable on demand through the
search bar**. The feed serves each company as it becomes ready and shows a progress
banner until the first pass completes (~1min). After that: fundamentals refresh every
12h, prices every 15min, macro hourly; failed tickers retry automatically every 5
minutes — no admin action, ever. Without an OpenRouter key the app still runs fully,
with deterministic narrative text.

### Coverage

- **US**: every SEC filer with XBRL facts (~thousands of tickers) on demand.
- **Europe & emerging markets**: any company with a US listing (ADR/ADS) that files
  20-F/40-F — SAP, ASML, Shell, Novo Nordisk, TSMC, Alibaba, Vale, Infosys, … IFRS
  statements in EUR/DKK/TWD/etc. are converted at live spot FX; per-share values use
  listing-consistent share counts (Yahoo count or EDGAR ÷ ADR ratio).
- **Not covered**: companies with no SEC registration (e.g. Nestlé's OTC ticker) —
  search shows them greyed out as "no SEC filings" rather than faking numbers.

## Prompt caching

GLM providers on OpenRouter cache the prompt prefix **implicitly** — the client keeps
the large, static methodology/system prompt first and puts all per-request data in the
user message, so repeated calls reuse the cached prefix. Verified live on StreamLake:
77–91% of prompt tokens billed at the cache-read rate (~19% of the normal prompt
price), ≈$0.0001 per narration call. Do not add Anthropic-style `cache_control`
breakpoints — they divert OpenRouter's routing away from StreamLake (observed live).
See `backend/valuescope/ai/openrouter.py`.

## License

MIT / AGPL (see PRD). Contributions welcome.
