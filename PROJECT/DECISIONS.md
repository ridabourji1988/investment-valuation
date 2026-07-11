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

### 2026-07-11 Decision: Priced Assets shipped as pricing-only module
**Context**: User approved ("go on with the last 2 decisions").
**Choice**: Markets tab, Coinbase + FRED→Yahoo chains, percentile context, no fair values ever.
**Outcome**: GOOD — live-verified same day.

### 2026-07-11 Decision: ESEF via filings.xbrl.org xBRL-JSON (design validated)
**Context**: Live probe proved GLEIF→filings.xbrl.org→OIM-JSON end-to-end (Air France FY2024 extracted).
**Choice**: Implement per the recipe in PLAN.md Milestone 2. Germany is NOT in filings.xbrl.org — BMW excluded until a German OAM source exists; SAP unaffected (20-F).
**Outcome**: PENDING (implementation next session)

### 2026-07-11 Decision: Acquisition goodwill excluded from invested capital
**Context**: AMD showed fair value −$1.75 (price $560); user lost trust. Xilinx's ~$45B goodwill made sales-to-capital 0.62 → ten years of phantom negative FCFF.
**Choice**: invested capital = equity + debt − cash − goodwill (Damodaran); floor revenue/2.
**Alternatives considered**: marginal Δsales/Δcapital (noisy), leaving as-was with a warning (dishonest output).
**Outcome**: GOOD — AMD fair −$1.75 → +$28.97, implied growth −20% → +60% (coherent); AAPL/AVGO sane.
**Lesson**: every mechanically-derived input needs an "is this economically possible" review; jointly-plausible inputs can still compound into absurd outputs.

### 2026-07-11 Decision: Lease liabilities are debt; growth base-effect guard
**Context**: AF-KLM valued at €310/share (price €13): zero debt tags matched (aircraft leases untagged as borrowings) and 2020-COVID-base CAGR hit the 30% growth cap.
**Choice**: add IFRS-16 lease liabilities (and us-gaap FINANCE leases only — operating-lease cost already sits in US-GAAP EBIT) to debt; growth base = min(point-to-point CAGR, median YoY).
**Outcome**: GOOD — AF-KLM net debt €8.1B, growth 13.7%, fair €106 (still rich → kept out of default scan; cyclical normalization stays on backlog).
**Lesson**: deep cyclicals need cycle-normalized margins before they can be shown by default.

### 2026-07-11 Decision: Boursorama as keyless EU price source
**Context**: EU prices were planned Yahoo-only; Yahoo is IP-boxed both locally and on Railway — ESEF names would have been dead on arrival. Cboe/AV don't carry Euronext; Euronext's own AJAX is encrypted.
**Choice**: Boursorama GetTicksEOD (browser-shaped headers required): Paris "1rP"+mnemonic, Amsterdam "1rA"+mnemonic, ~10y depth, EOD label. Helsinki not covered → .HE names excluded from default scan.
**Outcome**: GOOD — LVMH/Adyen valued with Yahoo fully down.

### 2026-07-11 Decision: ESEF ingestion shipped (Milestone 2)
**Context**: approved earlier today; recipe pre-validated live.
**Choice**: OIM→EDGAR-shape adapter so the entire existing assembly (tag fallbacks, share identities, forensics) works on EU filings unchanged; EUR end-to-end with ECB AAA 10y as risk-free.
**Outcome**: GOOD — LVMH FY2024 revenue €84.68B extracted exactly; 106/108 universe live locally.
**Lesson**: adapting a new source to an existing internal shape beats a parallel pipeline — every hard-won fallback came free.
