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
| **Data** (`backend/valuescope/data`) | Live SEC EDGAR / Yahoo / FRED clients + a bundled demo universe so the app runs fully offline. |
| **AI** (`backend/valuescope/ai`) | OpenRouter client (GLM via **Streamlake** with a cached system prompt for the discount) + number-validator guardrail + deterministic fallback. |
| **API** (`backend/valuescope/api`) | FastAPI: `/api/feed`, `/api/asset/{t}`, `/api/asset/{t}/calc/{metric}`, `/api/macro`, `/api/macro/rate-sensitivity`, `/api/formulas`, `/api/brief`, `/api/health`. |
| **Web** (`web/`) | React + Vite + Recharts. Opportunity Feed, Asset 360 (with live-slider DCF, Reverse DCF, Monte Carlo tabs), Show Calculation sheets with recursive drill-down, Macro & Cycle dashboard, Learn/Methodology generated from the registry. |

## Tested math

The acceptance bar is correctness of the financial calculations. **54 tests pass**,
each reproducing a textbook/Damodaran worked example within tolerance:

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest            # 54 passed
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
2. In **Project → Variables**, set (see `.env.example`):
   - `OPENROUTER_API_KEY` — your OpenRouter key (comma-separate multiple keys).
   - `OPENROUTER_MODEL` — the GLM slug to use (e.g. `z-ai/glm-4.6`).
   - `OPENROUTER_PROVIDER=Streamlake` — requested first for the caching discount.
   - `VALUESCOPE_LIVE_DATA=true` and `VALUESCOPE_SEC_UA="…your email…"` to enable live
     prices/macro (otherwise the demo dataset is served).
3. Deploy. Railway injects `PORT`; the server binds `0.0.0.0:$PORT` automatically.
   The single service serves both the API and the React app.

The app is fully functional with **no keys and no network** (demo dataset + deterministic
narratives); adding the OpenRouter key switches on GLM-written narratives, and
`VALUESCOPE_LIVE_DATA=true` switches on live prices and macro.

## Prompt caching

The AI client sends the large, static methodology/system prompt as a single cached
breakpoint (`cache_control: ephemeral`) and puts all per-request data in the user
message, so repeated calls reuse the cached prefix at the discounted rate on providers
that support it (Streamlake for GLM). See `backend/valuescope/ai/openrouter.py`.

## License

MIT / AGPL (see PRD). Contributions welcome.
