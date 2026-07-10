// Design tokens — exact values from the design file (PRD §2).
export const T = {
  bg: '#000000',
  sheet: '#1c1c1e',
  sheetBase: '#141416',
  elev: '#2c2c2e',
  separator: 'rgba(84,84,88,0.65)',
  green: '#32d74b',
  red: '#ff453a',
  amber: '#ffd60a',
  blue: '#0a84ff',
  gray: '#8e8e93',
  gray2: '#98989f',
  font: '-apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", "Helvetica Neue", Arial, sans-serif',
}

export const verdictColor = (v) => (v === 'BUY' ? T.green : v === 'SELL' ? T.red : T.amber)
