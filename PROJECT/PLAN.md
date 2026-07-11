# ValueScope — Plan

## Milestone 1 — Core app (DONE, deployed-ready `7119765`+)
Deterministic valuation engine (67 tests) · live keyless multi-source data
(EDGAR + Yahoo→Cboe→AlphaVantage, FRED→Treasury→Yahoo, BLS, er-api/ECB FX) ·
GLM 5.2 via StreamLake with guardrails + content-addressed narrative cache ·
93-name US/EU/EM universe · desktop UI with filters/sorting, 10y charts,
verify-at-source links, economic-events calendar · Railway deploy config.
**DoD met**: math tested, live-verified 93/93 with zero failures, UI verified.

## Milestone 2 — ESEF ingestion (APPROVED by user 2026-07-11, NEXT)
Cover EU-only filers (BMW, LVMH, Air France…) via their official ESEF XBRL
filings — keyless, from filings.xbrl.org.
- [ ] ESEF client: index query by LEI/name, fetch iXBRL, extract ifrs-full facts
- [ ] Entity resolution: ticker/name → LEI (GLEIF API, keyless)
- [ ] Non-USD listing support (EUR prices end-to-end; currency-aware UI)
- [ ] EU price source (Yahoo covers EU exchanges; needs non-USD listing path)
- [ ] Search: merge ESEF entities, label "EU filer (ESEF)"
**DoD**: BMW, LVMH, Air France-KLM analyzable with cited ESEF filings, math
tests green, zero synthetic data.

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
