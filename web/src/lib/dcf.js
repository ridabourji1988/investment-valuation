// Client-side port of the engine's FCFF DCF (valuescope/engine/dcf.py:value_firm)
// used only for the live "Assumptions" sliders (<50ms). The server engine
// remains the source of truth for stored results; this mirrors it exactly so
// the slider's base case reproduces the server's fair value.

function linspace(start, end, n) {
  if (n <= 1) return [end]
  const out = []
  for (let i = 0; i < n; i++) out.push(start + ((end - start) * i) / (n - 1))
  return out
}

export function valuePerShare(a) {
  const yh = a.years_high ?? 5
  const yt = a.years_total ?? 10
  const fade = yt - yh

  const growth = Array(yh).fill(a.growth_initial)
  for (let k = 1; k <= fade; k++) {
    growth.push(a.growth_initial + ((a.growth_terminal - a.growth_initial) * k) / fade)
  }
  const margins = linspace(a.ebit_margin_base, a.target_margin, yh).concat(Array(fade).fill(a.target_margin))
  const waccs = Array(yh).fill(a.wacc_initial)
  for (let k = 1; k <= fade; k++) {
    waccs.push(a.wacc_initial + ((a.wacc_terminal - a.wacc_initial) * k) / fade)
  }

  let rev = a.revenue_base
  let df = 1.0
  let pv = 0.0
  let lastRev = rev
  let lastDf = 1.0
  for (let t = 0; t < yt; t++) {
    const prev = rev
    rev = rev * (1 + growth[t])
    const ebit = rev * margins[t]
    const nopat = ebit * (1 - a.tax_rate)
    const reinvest = (rev - prev) / a.sales_to_capital
    const f = nopat - reinvest
    df *= 1 / (1 + waccs[t])
    pv += f * df
    lastRev = rev
    lastDf = df
  }
  const roic = a.roic_stable != null ? a.roic_stable : a.wacc_terminal
  const g = a.growth_terminal
  const reinvestRate = roic <= 0 ? 0 : g / roic
  const rev11 = lastRev * (1 + g)
  const nopat11 = rev11 * a.target_margin * (1 - a.tax_rate)
  const fcff11 = nopat11 * (1 - reinvestRate)
  const tv = fcff11 / (a.wacc_terminal - g)
  const ev = pv + tv * lastDf
  return (ev - a.net_debt) / a.shares
}
