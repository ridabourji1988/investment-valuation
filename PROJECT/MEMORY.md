# Working memory (active gotchas & context)

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
- PRD source: the original requirements doc from session 1 (PRD.md/SPECS.md
  still to be distilled from it).
