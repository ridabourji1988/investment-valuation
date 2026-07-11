# ValueScope — Plan

## Milestone 1 — Core app (DONE, deployed-ready `7119765`+)
Deterministic valuation engine (67 tests) · live keyless multi-source data
(EDGAR + Yahoo→Cboe→AlphaVantage, FRED→Treasury→Yahoo, BLS, er-api/ECB FX) ·
GLM 5.2 via StreamLake with guardrails + content-addressed narrative cache ·
93-name US/EU/EM universe · desktop UI with filters/sorting, 10y charts,
verify-at-source links, economic-events calendar · Railway deploy config.
**DoD met**: math tested, live-verified 93/93 with zero failures, UI verified.

## Milestone 2 — ESEF ingestion (APPROVED 2026-07-11; design VALIDATED live, implementation next)
Cover EU-only filers via official ESEF XBRL. **Proven recipe** (all keyless):
1. Name→LEI: `api.gleif.org/api/v1/lei-records?filter[fulltext]=<name>` (60 req/min;
   autocompletions needs `field=fulltext`). LVMH=IOG4E947OATN0KJYSD45,
   AF-KLM=969500AQW31GYO8JZD66.
2. Filings: `filings.xbrl.org/api/entities/{LEI}/filings` (relationship filters on
   /api/filings silently return 0 — use the entity path). Fields: period_end,
   json_url (root-relative, can be null), fxo_id; dedupe amended (/0,/1 → highest)
   and language-variant filings by period_end.
3. Facts: xBRL-JSON (OIM) `facts{}`: keep only facts whose dimensions have NO keys
   beyond {concept, entity, period, unit, language} (= consolidated, undimensioned),
   then filter period to latest FY (duration for P&L, FY-end+1d instant for BS).
   Values are strings; EPS unit `iso4217:EUR/xbrli:shares`. Verified on AF-KLM
   FY2024: Revenue 31,459M€, EBIT 1,466M€, NI 489M€.
**Hard caveat**: Germany does NOT feed filings.xbrl.org (BMW/Siemens/SAP-local not
available; SAP is fine via its 20-F). Coverage: FR 1173, DK 2121, GB 2885, FI 1168,
NL 655 filings. BMW needs a German OAM/Bundesanzeiger source — separate item.
- [ ] data/esef.py (LEI resolve, filing pick, fact extraction with the dimension rule)
- [ ] Non-USD listing support in live.py + currency-aware UI (EUR prices end-to-end)
- [ ] EU listing prices via Yahoo exchange suffixes (AF.PA, MC.PA…) — Yahoo-only, breaker-aware
- [ ] Search: merge ESEF entities, label "EU filer (ESEF)"; extension-taxonomy fallbacks
**DoD**: LVMH + Air France-KLM analyzable with cited ESEF filings, tests green, zero synthetic.

## Milestone 3 — Priced Assets (DONE 2026-07-11)
Markets tab: crypto (Coinbase, ~6y candles) + commodities (FRED → Yahoo futures),
long-run percentile + 1y move + source links, explicit priced-not-valued epistemics,
honest per-asset skip. Verified live: BTC/ETH/SOL; commodities populate where
FRED/Yahoo reachable (Railway).

## Milestone 3 — Priced Assets (PROPOSED, awaiting user confirmation)
Commodities (oil/gas/metals) and crypto have no cash flows → cannot be
*valued*, only *priced*. Proposal: separate clearly-labeled section —
real-price percentile vs long history, futures curve read (contango/backwd.),
staking-yield note for PoS crypto. Never a "fair value".

## Backlog / options
- Universe: user can set VALUESCOPE_UNIVERSE (any size); optional "S&P 500
  mode" default — warm ~15 min first pass, then incremental.
- Bank/insurer + captive-finance valuation model (FCFE/DDM) — re-admit
  JPM/HSBC/Toyota etc. honestly.
- Cycle-normalized margins for cyclicals (Damodaran) — better CVX/VALE/RIO.
- Analysis persistence across restarts (survive redeploys without rewarm).
