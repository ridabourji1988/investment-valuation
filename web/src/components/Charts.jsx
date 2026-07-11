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

export function PriceChart({ history, fairValue, rangeLabel = '1Y', height = 220 }) {
  // Reindex from 0 — history may be a tail slice, and recharts ticks refer to
  // dataKey values, not positions.
  const rows = history.map((p, idx) => ({ i: idx, close: p.close }))
  const closes = rows.map((r) => r.close)
  const lo = Math.min(...closes, fairValue || Infinity)
  const hi = Math.max(...closes, fairValue || -Infinity)
  const last = closes[closes.length - 1]
  const up = last >= closes[0]
  const color = up ? T.green : T.red
  const n = rows.length
  const ticks = [0, Math.floor(n / 4), Math.floor(n / 2), Math.floor((3 * n) / 4), n - 1]
  return (
    <div style={{ height, margin: '4px 8px 0' }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 8, right: 44, bottom: 4, left: 0 }}>
          <CartesianGrid stroke={T.separator} strokeWidth={0.5} vertical={false} />
          <XAxis dataKey="i" ticks={ticks} tick={{ fill: T.gray, fontSize: 10 }}
            axisLine={false} tickLine={false} tickFormatter={(i) => labelFor(i, n, rangeLabel)} />
          <YAxis orientation="right" domain={[lo * 0.98, hi * 1.02]}
            tick={{ fill: T.gray, fontSize: 10 }} axisLine={false} tickLine={false} width={44}
            tickFormatter={(v) => v.toFixed(0)} />
          <Tooltip contentStyle={{ background: T.sheet, border: 'none', borderRadius: 8, fontSize: 12 }}
            labelStyle={{ color: T.gray }} formatter={(v) => [usd(v), 'Close']}
            labelFormatter={() => ''} />
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

function labelFor(i, n, rangeLabel) {
  const frac = i / (n - 1)
  const start = rangeLabel === 'All' ? 'Start' : `${rangeLabel} ago`
  const labels = [start, '', '', '', 'Now']
  const idx = Math.round(frac * 4)
  return labels[idx] || ''
}
