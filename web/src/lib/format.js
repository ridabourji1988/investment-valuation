// Shared number formatting (PRD §2). European locale: comma decimal separator,
// thin-space thousands separator, "US$" suffix, true minus sign for negatives.
// No screen may format numbers independently — everything goes through here.

const THIN = ' ' // thin space
const MINUS = '−' // true minus sign

function group(intStr) {
  return intStr.replace(/\B(?=(\d{3})+(?!\d))/g, THIN)
}

function core(value, decimals) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const neg = value < 0
  const fixed = Math.abs(value).toFixed(decimals)
  const [int, frac] = fixed.split('.')
  let out = group(int)
  if (decimals > 0) out += ',' + frac
  return (neg ? MINUS : '') + out
}

export function num(value, decimals = 2) {
  return core(value, decimals)
}

export function usd(value, decimals = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return core(value, decimals) + THIN + 'US$'
}

// Compact large currency (e.g. market cap): 42,1 Md US$ / 6,20 Mrd style.
export function usdCompact(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const abs = Math.abs(value)
  const sign = value < 0 ? MINUS : ''
  if (abs >= 1e12) return sign + core(abs / 1e12, 2) + THIN + 'T' + THIN + 'US$'
  if (abs >= 1e9) return sign + core(abs / 1e9, 2) + THIN + 'Md' + THIN + 'US$'
  if (abs >= 1e6) return sign + core(abs / 1e6, 2) + THIN + 'M' + THIN + 'US$'
  return usd(value, 0)
}

export function pct(value, decimals = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return core(value * 100, decimals) + THIN + '%'
}

// Signed change chip value, e.g. +1,90 % or −0,48 %.
export function signedPct(value, decimals = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const s = core(value * 100, decimals)
  const sign = value > 0 ? '+' : '' // core already adds the minus sign
  return sign + s + THIN + '%'
}

export function signed(value, decimals = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const s = core(value, decimals)
  return (value > 0 ? '+' : '') + s
}

// Format an engine input value for the calculation sheet (unit-aware).
export function formatInput(value, unit) {
  if (value === null || value === undefined) return '—'
  if (Array.isArray(value)) return value.map((v) => formatInput(v, unit)).join(', ')
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  if (typeof value === 'string') return value
  if (typeof value !== 'number') return String(value)
  switch (unit) {
    case 'decimal':
      return pct(value)
    case '%':
      return num(value, 1) + THIN + '%'
    case 'US$':
      return usdCompact(value)
    case 'US$/share':
      return usd(value)
    case 'count':
      return num(value, 0)
    case 'pp':
      return num(value, 2) + THIN + 'pp'
    case 'index':
    case 'idx':
      return num(value, 1)
    default:
      return num(value, Math.abs(value) >= 1000 ? 0 : Math.abs(value) >= 10 ? 2 : 4)
  }
}

// Generic value formatter for result/step values in calculation sheets.
export function formatValue(v) {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'boolean') return v ? 'yes' : 'no'
  if (typeof v === 'number') {
    if (Math.abs(v) >= 1e6) return usdCompact(v)
    if (Math.abs(v) >= 1000) return num(v, 0)
    if (Math.abs(v) > 0 && Math.abs(v) < 1) return num(v, 4)
    return num(v, 2)
  }
  return String(v)
}
