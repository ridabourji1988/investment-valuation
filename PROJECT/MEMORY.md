# Working memory (active gotchas & context)

- Boursorama EOD endpoint returns [] without browser-shaped headers
  (User-Agent + Accept + X-Requested-With + Referer). Symbols: Paris
  "1rP"+mnemonic, Amsterdam "1rA"+mnemonic; Helsinki NOT covered. `d` field
  = days since 1970-01-01; length param is calendar days.
- GLEIF fulltext top hit is often a subsidiary LEI with no ESEF filings —
  always verify against filings.xbrl.org/api/entities/{LEI}/filings before
  adding to the esef.py registry (Air Liquide/Safran/Vinci/Danone/Thales
  still unresolved this way).
- ESEF facts: OIM period ends are EXCLUSIVE (midnight after last day) —
  subtract one day; keep only ifrs-full concepts with no dimensions beyond
  {concept,entity,period,unit,language}.
- Valuation model updates 2026-07-11 (all filers): goodwill OUT of invested
  capital; IFRS-16 leases (us-gaap: finance leases only) IN debt; growth
  base = min(CAGR, median YoY). Don't "fix" these back.

- **Never** add Anthropic-style `cache_control` to OpenRouter GLM calls — it
  diverts routing away from StreamLake to ~3x pricier providers. GLM caches
  implicitly (static system prompt first).
- Yahoo per-IP penalty RE-ARMS on every contact while boxed; VPN exits are
  usually pre-boxed. Cboe CDN throttles bursts (~45 tickers) — pacing is
  adaptive in `data/cboe.py`, don't hammer it in tests.
- FRED is unreachable from the user's home network (timeouts) — Treasury/BLS
  fallbacks carry macro locally; FRED works on Railway.
- Alpha Vantage free tier = 25 req/day: last-resort only, quota breaker 30 min.
- EDGAR XBRL long tail: tags migrate (pick by most-recent FY); some filers tag
  no revenue (Novartis → GP+CoS), no pretax (TTE → NI+tax), no share count
  (BP → dividends÷DPS); dei count is sometimes ADS-equivalent (BABA) — the
  implied-P/E selector resolves units.
- Unsponsored ADRs (BMWKY) have a CIK but no XBRL → honest 404 + greyed search.
- Local test server: port 8015; OPENROUTER_API_KEY + ALPHAVANTAGE_API_KEY set
  via env only (never committed). Railway needs them in Variables.
- Production URL: https://investment.up.railway.app — queryable directly
  (/api/health, /api/feed) to diagnose prod without user screenshots.
- 2026-07-11 prod outage cause: user set VALUESCOPE_UNIVERSE=10000 in Railway
  (meant for MC_RUNS) → universe = one fake ticker → zero data, looked like
  rate-limiting. config.py now drops non-ticker tokens and falls back to the
  default universe; the variable should still be deleted in Railway.
- PRD source: the original requirements doc from session 1 (PRD.md/SPECS.md
  still to be distilled from it).
