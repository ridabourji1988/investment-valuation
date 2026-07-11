import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { usd, pct, signedPct, num } from '../lib/format'
import { T } from '../theme'
import { Sparkline } from './Charts'
import { Disclaimer } from './Feed'

// Commodities & crypto: priced, never valued. No verdicts, no fair values —
// the engine's valuation machinery does not apply to non-cash-flow assets.
export default function Priced() {
  const [m, setM] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => {
    let timer
    const load = () => api.priced().then((d) => { setErr(null); setM(d) })
      .catch((e) => { setErr(e.message); timer = setTimeout(load, 30000) })
    load()
    return () => clearTimeout(timer)
  }, [])

  if (err && !m) return <div className="loading">Priced-asset sources unavailable — retrying automatically. {err}</div>
  if (!m) return <div className="loading"><span className="spinner" />Loading market prices…</div>

  const groups = [['crypto', 'Crypto'], ['commodity', 'Commodities']]
  return (
    <div>
      <div className="title-lg">Markets</div>
      <div className="subtitle">Commodities &amp; crypto — priced, not valued</div>

      <div className="card">
        <div className="eyebrow" style={{ color: T.amber }}>Why no fair value here</div>
        <div className="muted" style={{ fontSize: 13, lineHeight: 1.5 }}>{m.epistemics}</div>
      </div>

      {groups.map(([kind, title]) => {
        const rows = m.assets.filter((a) => a.kind === kind)
        if (!rows.length) return null
        return (
          <div className="card" style={{ padding: 0 }} key={kind}>
            <div className="eyebrow" style={{ padding: '16px 16px 8px' }}>{title}</div>
            {rows.map((a) => (
              <div className="row hairline" key={a.id} style={{ cursor: 'default' }}>
                <div className="row-main">
                  <div className="row-ticker">{a.label}</div>
                  <div className="row-name">
                    {num(a.percentile * 100, 0)}th percentile of its {a.history_years}y history ·{' '}
                    <a href={a.url} target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>{a.source} ↗</a>
                  </div>
                  <div className="mos-bar" style={{ maxWidth: 220 }}>
                    <div className="bar"><div className="fill" style={{
                      width: Math.max(2, a.percentile * 100) + '%',
                      background: a.percentile >= 0.8 ? T.red : a.percentile >= 0.5 ? T.amber : T.green }} />
                    </div>
                  </div>
                </div>
                <Sparkline data={a.spark.map((p) => p.close)} prevClose={a.spark[0]?.close} />
                <div className="row-right">
                  <span className="price tnum">{usd(a.price)}</span>
                  {a.change_1y !== null && (
                    <span className={'chip ' + (a.change_1y >= 0 ? 'pos' : 'neg')}>{signedPct(a.change_1y)} 1y</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )
      })}

      {m.skipped?.length > 0 && (
        <div className="card">
          <div className="muted" style={{ fontSize: 12 }}>
            Unavailable right now (source down, auto-retrying): {m.skipped.map((s) => s.id).join(', ')}
          </div>
        </div>
      )}
      <Disclaimer />
    </div>
  )
}
