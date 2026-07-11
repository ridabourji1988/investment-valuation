import {
  AreaChart, Area, LineChart, Line, ReferenceLine, ResponsiveContainer,
  YAxis, XAxis, CartesianGrid, Tooltip,
} from 'recharts'
import { T } from '../theme'
import { usd } from '../lib/format'

export function Sparkline({ data, prevClose, width = 90, height = 34 }) {
  const last = data[data.length - 1]
  const up = last >= (prevClose ?? data[0])
  const color = up ? T.green : T.red
  const rows = data.map((v, i) => ({ i, v }))
  const id = `sg-${Math.round((prevClose || 0) * 1000)}-${data.length}`
  return (
    <div style={{ width, height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={rows} margin={{ top: 2, bottom: 2, left: 0, right: 0 }}>
          <defs>
            <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.35} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          {prevClose != null && (
            <ReferenceLine y={prevClose} stroke={T.gray} strokeDasharray="2 2" strokeWidth={0.5} />
          )}
          <YAxis hide domain={['dataMin', 'dataMax']} />
          <Area type="monotone" dataKey="v" stroke={color} strokeWidth={1.5}
            fill={`url(#${id})`} isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// "2026-03-14" -> "14 Mar" (short ranges) or "Mar 26" (long ranges)
function fmtDate(iso, longRange) {
  if (!iso) return ''
  const [y, m, d] = iso.split('-')
  const mon = MONTHS[parseInt(m, 10) - 1] || ''
  return longRange ? `${mon} ${y.slice(2)}` : `${parseInt(d, 10)} ${mon}`
}

export function PriceChart({ history, fairValue, height = 240 }) {
  // Reindex from 0 — history may be a tail slice, and recharts ticks refer to
  // dataKey values, not positions.
  const rows = history.map((p, idx) => ({ i: idx, close: p.close, date: p.date }))
  const closes = rows.map((r) => r.close)
  const lo = Math.min(...closes, fairValue || Infinity)
  const hi = Math.max(...closes, fairValue || -Infinity)
  const last = closes[closes.length - 1]
  const up = last >= closes[0]
  const color = up ? T.green : T.red
  const n = rows.length
  // Span in days decides the date format (months for >120 trading days).
  const longRange = n > 120
  const tickCount = 5
  const ticks = Array.from({ length: tickCount },
    (_, k) => Math.round((k * (n - 1)) / (tickCount - 1)))
  const dateAt = (i) => fmtDate(rows[Math.max(0, Math.min(n - 1, i))]?.date, longRange)
  return (
    <div style={{ height, margin: '4px 8px 0' }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 8, right: 48, bottom: 4, left: 0 }}>
          <CartesianGrid stroke={T.separator} strokeWidth={0.5} vertical={false} />
          <XAxis dataKey="i" ticks={ticks} tick={{ fill: T.gray, fontSize: 10.5 }}
            axisLine={false} tickLine={false} tickFormatter={dateAt} />
          <YAxis orientation="right" domain={[lo * 0.98, hi * 1.02]}
            tick={{ fill: T.gray, fontSize: 10.5 }} axisLine={false} tickLine={false} width={48}
            tickFormatter={(v) => v.toFixed(0)} />
          <Tooltip contentStyle={{ background: T.sheet, border: 'none', borderRadius: 8, fontSize: 12 }}
            labelStyle={{ color: T.gray }} formatter={(v) => [usd(v), 'Close']}
            labelFormatter={(i) => fmtDate(rows[i]?.date, false)} />
          {fairValue != null && (
            <ReferenceLine y={fairValue} stroke={T.blue} strokeDasharray="5 4" strokeWidth={1}
              label={{ value: 'Fair value', fill: T.blue, fontSize: 10, position: 'insideTopRight' }} />
          )}
          <Line type="monotone" dataKey="close" stroke={color} strokeWidth={1.6} dot={false}
            isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

// Tiny inline series for calculation-sheet inputs (e.g. monthly unemployment).
export function InlineSeries({ values, width = 130, height = 30 }) {
  const rows = values.map((v, i) => ({ i, v }))
  return (
    <div style={{ width, height, display: 'inline-block', verticalAlign: 'middle' }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 3, bottom: 3, left: 0, right: 0 }}>
          <YAxis hide domain={['dataMin', 'dataMax']} />
          <Line type="monotone" dataKey="v" stroke={T.blue} strokeWidth={1.4} dot={false}
            isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
