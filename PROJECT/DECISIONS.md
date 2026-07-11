# Decision log (append-only)

### 2026-07-11 Decision: Multi-source keyless data chains (no Yahoo dependence)
**Context**: Yahoo rate-limits per IP (penalty re-arms on contact); user's networks kept getting boxed.
**Choice**: Chain every price-shaped fetch: Yahoo → Cboe delayed CDN → Alpha Vantage (optional key); rates FRED → official US Treasury XML → Yahoo; FX Yahoo → er-api → ECB; BLS for unemployment/CPI. Adaptive pacing + circuit breakers per source.
**Alternatives considered**: Stooq (PoW-walled on datacenter IPs), keyed APIs as primary (violates zero-admin mandate).
**Outcome**: GOOD — 93/93 warmed live with Yahoo fully down.
**Lesson**: Burst scans trip CDN throttles; pace adaptively and let a watchdog heal.

### 2026-07-11 Decision: Exclude banks/insurers and Toyota from the default universe
**Context**: FCFF DCF treats debt as a claim to net out; for financials debt is raw material. Toyota's captive finance arm produced fair value $14.84 vs $177 price with correct inputs.
**Choice**: Exclude until a dedicated FCFE/DDM model exists; still searchable.
**Outcome**: GOOD (honesty over coverage).

### 2026-07-11 Decision: Share-count unit ambiguity resolved by implied P/E (log-space)
**Context**: EDGAR share tags are sometimes ordinary shares, sometimes ADS-equivalent (BABA), off by exactly the ADR ratio.
**Choice**: Among candidates (Yahoo, EDGAR÷ratio, EDGAR as-is), pick the implied P/E closest in log space to ~15x; filed-identity fallbacks (NI/EPS, dividends/DPS) for filers with no share tag (BP).
**Outcome**: GOOD — BABA 686→86, BP 15.5B shares matches reality.

### 2026-07-11 Decision: MoS pinned at −100% when value ≤ 0
**Context**: (V−P)/V flips sign for negative V; AMD showed +32,022% and topped the feed.
**Choice**: Pin at −1.0 with trace caveat; SELL rule then fires naturally.
**Outcome**: GOOD.

### 2026-07-11 Decision: ESEF ingestion approved as next milestone
**Context**: User wants BMW/LVMH/Air France-class EU companies; they file no SEC XBRL.
**Choice**: Ingest official ESEF filings (filings.xbrl.org, keyless) + non-USD listing support.
**Outcome**: PENDING

### 2026-07-11 Decision: Commodities/crypto = pricing, not valuation (proposal)
**Context**: User asked repeatedly about oil/gas/metals/crypto.
**Choice**: Proposed a separate "Priced Assets" section (relative pricing, futures curve, staking yield) — never a fair value; awaiting explicit go-ahead.
**Outcome**: PENDING
