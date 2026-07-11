import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { pct, num, usd } from '../lib/format'
import { T } from '../theme'
import { CalcProvider, Calc } from './Calc'
import { Disclaimer } from './Feed'

export default function Macro({ formulas }) {
  const [m, setM] = useState(null)
  const [rs, setRs] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => {
    let timer
    const load = () => {
      api.macro().then((d) => { setErr(null); setM(d) })
        .catch((e) => { setErr(e.message); timer = setTimeout(load, 30000) })
      api.rateSensitivity(50).then(setRs).catch(() => {})
    }
    load()
    return () => clearTimeout(timer)
  }, [])
  if (err && !m) return (
    <div>
      <div className="title-lg">Macro &amp; Cycle</div>
      <div className="card">
        <div className="eyebrow" style={{ color: T.amber }}>Macro sources warming</div>
        <div className="lead">
          Live macro series (Treasury yields, unemployment, CPI) are still being fetched —
          the first pass can take a moment, and a temporary rate limit looks the same.
          This page retries automatically every 30 seconds; nothing is ever simulated.
        </div>
        <div className="muted" style={{ fontSize: 12, marginTop: 10 }}>{err}</div>
      </div>
      <Disclaimer />
    </div>
  )
  if (!m) return <div className="loading">Loading macro…</div>

  const traces = { sahm: m.sahm, regime: m.regime }
  const regime = m.regime.result
  const dotColor = regime.label === 'Expansion' ? T.green : regime.label === 'Late cycle' ? T.amber : T.red

  return (
    <CalcProvider traces={traces} formulas={formulas}>
      <div className="title-lg">Macro &amp; Cycle</div>
      <div className="subtitle">As of {m.asof}</div>

      {/* Regime card */}
      <div className="card">
        <div className="eyebrow">Regime</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span className="dot" style={{ background: dotColor, width: 12, height: 12 }} />
          <span style={{ fontSize: 22, fontWeight: 800 }}><Calc metricId="regime">{regime.label}</Calc></span>
        </div>
        <div className="lead" style={{ marginTop: 6 }}>{regime.implication}</div>
        <div className="muted" style={{ fontSize: 12, marginTop: 10, fontStyle: 'italic' }}>
          Rule P4: macro adjusts position size and risk labels; it never flips a verdict or gates the feed.
        </div>
      </div>

      {/* Sahm rule */}
      <div className="card">
        <div className="eyebrow">Sahm recession rule</div>
        <div style={{ fontSize: 22, fontWeight: 800 }}>
          <Calc metricId="sahm">{num(m.sahm.result.value, 2)} pp</Calc>
          <span className="muted" style={{ fontSize: 15, marginLeft: 8 }}>
            {m.sahm.result.triggered ? 'triggered' : 'not triggered'} (≥ 0,50)
          </span>
        </div>
      </div>

      {/* Indicators */}
      <div className="card" style={{ padding: 0 }}>
        {m.indicators.map((ind) => (
          <div key={ind.id} className="row hairline" style={{ cursor: 'default' }}>
            <div className="row-main">
              <div className="row-ticker" style={{ fontSize: 15 }}>{ind.label}</div>
              <div className="row-name">{ind.read}</div>
            </div>
            <div className="tnum" style={{ fontWeight: 700 }}>
              {ind.unit === '%' ? pct(ind.value) : ind.unit === 'idx' ? num(ind.value, 1) : num(ind.value, 2)}
            </div>
          </div>
        ))}
      </div>

      {/* Fed Watch */}
      <div className="card">
        <div className="eyebrow">Fed Watch</div>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <div>
            <div className="muted" style={{ fontSize: 13 }}>Target range</div>
            <div style={{ fontSize: 20, fontWeight: 700 }} className="tnum">
              {pct(m.fed.target_low)}–{pct(m.fed.target_high)}
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div className="muted" style={{ fontSize: 13 }}>Next FOMC</div>
            <div style={{ fontSize: 20, fontWeight: 700 }}>{m.fed.next_fomc}</div>
          </div>
        </div>
        <div className="muted" style={{ fontSize: 13, marginTop: 8 }}>CPI (YoY) {pct(m.fed.cpi_yoy)}. Path revalued weekly.</div>
      </div>

      {/* Rate-sensitivity table */}
      {rs && (
        <div className="card" style={{ padding: 0 }}>
          <div className="eyebrow" style={{ padding: '16px 16px 8px' }}>Rate-sensitivity — every DCF at 10Y ±50bp</div>
          <table className="inputs" style={{ padding: '0 16px' }}>
            <tbody>
              <tr><td className="src">Ticker</td><td className="src">−50bp</td><td className="src">Base</td><td className="src">+50bp</td></tr>
              {rs.rows.map((r) => (
                <tr key={r.ticker}>
                  <td><b>{r.ticker}</b></td>
                  <td className="tnum" style={{ color: T.green }}>{usd(r.minus_50bp)}</td>
                  <td className="tnum">{usd(r.base)}</td>
                  <td className="tnum" style={{ color: T.red }}>{usd(r.plus_50bp)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ height: 12 }} />
        </div>
      )}

      <div className="card">
        <div className="muted" style={{ fontSize: 12 }}>Sources: {Object.values(m.sources).join(', ')}</div>
      </div>
      <Disclaimer />
    </CalcProvider>
  )
}
