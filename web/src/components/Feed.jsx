import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { usd, pct, signedPct } from '../lib/format'
import { T, verdictColor } from '../theme'
import { Sparkline } from './Charts'

export default function Feed({ onOpen, onMacro }) {
  const [feed, setFeed] = useState(null)
  const [brief, setBrief] = useState(null)
  const [q, setQ] = useState('')
  const [results, setResults] = useState(null)
  const [err, setErr] = useState(null)
  const debounce = useRef(null)

  const onQuery = (value) => {
    setQ(value)
    clearTimeout(debounce.current)
    if (value.trim().length < 2) { setResults(null); return }
    debounce.current = setTimeout(() => {
      api.search(value.trim()).then((r) => setResults(r.results)).catch(() => setResults(null))
    }, 300)
  }

  useEffect(() => {
    let timer
    const load = () => api.feed().then((f) => {
      setFeed(f)
      // First scan of the universe runs in the background at startup —
      // poll until every ticker has been attempted.
      if (f.warming) timer = setTimeout(load, 4000)
      else api.brief().then(setBrief).catch(() => {})
    }).catch((e) => setErr(e.message))
    load()
    return () => clearTimeout(timer)
  }, [])

  if (err) return <div className="loading">Could not load feed: {err}</div>
  if (!feed) return <div className="loading">Scanning markets…</div>

  const today = new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })
  const rows = feed.rows.filter((r) =>
    !q || r.ticker.toLowerCase().includes(q.toLowerCase()) ||
    r.name.toLowerCase().includes(q.toLowerCase()))

  return (
    <div>
      <div className="title-lg">ValueScope</div>
      <div className="subtitle">{today}</div>

      <div className="toolbar">
        <input className="search" placeholder="Search any ticker or company (US, EU & EM via US listings)"
          value={q} onChange={(e) => onQuery(e.target.value)} />
        <button className="pill-btn" title="Filters">···</button>
      </div>

      {/* Global search results */}
      {results && (
        <div className="search-results">
          {results.length === 0 && <div className="search-hint">No matches.</div>}
          {results.map((r) => (
            <div className="row hairline" key={r.ticker}
              onClick={() => r.analyzable && onOpen(r.ticker)}
              style={{ opacity: r.analyzable ? 1 : 0.55, cursor: r.analyzable ? 'pointer' : 'default' }}>
              <div className="row-main">
                <div className="row-ticker" style={{ fontSize: 15 }}>{r.ticker}
                  {r.exchange ? <span className="tag" style={{ marginLeft: 8 }}>{r.exchange}</span> : null}
                </div>
                <div className="row-name">{r.name}</div>
              </div>
              {r.analyzable
                ? <span className="tag blue">Analyze ›</span>
                : <span className="tag">no SEC filings</span>}
            </div>
          ))}
          <div className="search-hint">
            Any company with SEC filings is analyzable on demand — including European and
            emerging-market names via their US listings (ADRs).
          </div>
        </div>
      )}

      {/* Macro & Cycle entry row */}
      <div className="row hairline" onClick={onMacro}>
        <span className="dot" style={{ background: regimeDot(feed.regime) }} />
        <div className="row-main">
          <div className="row-ticker" style={{ fontSize: 15 }}>Macro &amp; Cycle</div>
          <div className="row-name">{feed.regime} · {feed.regime_implication}</div>
        </div>
        <span className="muted">›</span>
      </div>

      {/* Warming banner while the first live scan completes */}
      {feed.warming && (
        <div className="row hairline" style={{ cursor: 'default' }}>
          <div className="row-main">
            <div className="row-name">
              Scanning SEC filings… {feed.count}/{feed.universe} companies ready
            </div>
          </div>
        </div>
      )}
      {Object.keys(feed.failed || {}).length > 0 && !feed.warming && (
        <div className="row hairline" style={{ cursor: 'default' }}>
          <div className="row-main">
            <div className="row-name">
              Skipped (source unavailable): {Object.keys(feed.failed).join(', ')}
            </div>
          </div>
        </div>
      )}

      {/* Ranked rows */}
      {rows.map((r) => {
        const chg = (r.price - r.prev_close) / r.prev_close
        return (
          <div className="row hairline" key={r.ticker} onClick={() => onOpen(r.ticker)}>
            <div className="row-main">
              <div className="row-ticker">{r.ticker}
                <span className="tag" style={{ marginLeft: 8 }}>{r.sector.length > 26 ? r.sector.slice(0, 24) + '…' : r.sector}</span>
              </div>
              <div className="row-name">{r.name}</div>
              <div className="row-verdict" style={{ color: verdictColor(r.verdict) }}>
                <span className={'tag ' + (r.verdict === 'BUY' ? 'green' : r.verdict === 'SELL' ? 'red' : 'amber')}>{r.verdict}</span>
                {r.margin_of_safety >= 0 ? pct(r.margin_of_safety) + ' under fair value'
                  : pct(-r.margin_of_safety) + ' over fair value'}
                {r.data_quality === 'low' && <span className="badge warn">data quality: low</span>}
              </div>
            </div>
            <div className="mos-bar">
              <div className="lab"><span>Quality</span><span>{Math.round(r.quality)}</span></div>
              <div className="bar"><div className="fill" style={{ width: Math.max(2, Math.min(100, r.quality)) + '%', background: r.quality >= 66 ? T.green : r.quality >= 33 ? T.amber : T.red }} /></div>
            </div>
            <Sparkline data={r.spark} prevClose={r.prev_close} />
            <div className="row-right">
              <span className="price tnum">{usd(r.price)}</span>
              <span className={'chip ' + (chg >= 0 ? 'pos' : 'neg')}>{signedPct(chg)}</span>
            </div>
          </div>
        )
      })}

      {/* AI Market Brief (Apple "Business News" style) */}
      {brief && (
        <div className="card memo" style={{ marginTop: 18 }}>
          <div className="src">
            Market Brief · {brief.block.ai ? brief.block.source : 'ValueScope engine'}
            {brief.block.ai ? <span className="badge ai">AI</span> : null}
          </div>
          <div className="headline">Today’s scan</div>
          <div className="body">{brief.block.text}</div>
        </div>
      )}

      <Disclaimer />
    </div>
  )
}

function regimeDot(regime) {
  if (regime === 'Expansion') return T.green
  if (regime === 'Late cycle') return T.amber
  return T.red
}

export function Disclaimer() {
  return (
    <div className="disclaimer">
      Educational research tool. Not investment advice. All valuations are estimates that depend on
      assumptions. No orders are ever executed.
    </div>
  )
}
