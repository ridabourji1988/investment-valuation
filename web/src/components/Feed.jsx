import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { usd, pct, signedPct } from '../lib/format'
import { T, verdictColor } from '../theme'
import { Sparkline } from './Charts'

const SORTS = {
  mos: { label: 'Margin of safety', fn: (a, b) => b.margin_of_safety - a.margin_of_safety },
  quality: { label: 'Quality', fn: (a, b) => b.quality - a.quality },
  change: { label: 'Daily change', fn: (a, b) => chgOf(b) - chgOf(a) },
  price: { label: 'Price', fn: (a, b) => b.price - a.price },
  ticker: { label: 'A–Z', fn: (a, b) => a.ticker.localeCompare(b.ticker) },
}
const chgOf = (r) => (r.price - r.prev_close) / (r.prev_close || 1)

export default function Feed({ onOpen, onMacro }) {
  const [feed, setFeed] = useState(null)
  const [brief, setBrief] = useState(null)
  const [q, setQ] = useState('')
  const [results, setResults] = useState(null)
  const [err, setErr] = useState(null)
  const [showFilters, setShowFilters] = useState(false)
  const [sortBy, setSortBy] = useState('mos')
  const [verdictF, setVerdictF] = useState('ALL')
  const [hideLowDq, setHideLowDq] = useState(false)
  const debounce = useRef(null)

  const onQuery = (value) => {
    setQ(value)
    clearTimeout(debounce.current)
    if (value.trim().length < 2) { setResults(null); return }
    debounce.current = setTimeout(() => {
      api.search(value.trim()).then((r) => setResults(r.results)).catch(() => setResults(null))
    }, 300)
  }

  const briefFor = useRef(-1)
  const fastUntil = useRef(0)
  const loadRef = useRef(null)
  useEffect(() => {
    let timer
    const load = () => api.feed().then((f) => {
      setFeed(f)
      // Poll fast during the first scan and after a manual retry, slower
      // while tickers are missing — the page recovers on its own.
      if (f.warming) timer = setTimeout(load, 4000)
      else if (f.count < f.universe)
        timer = setTimeout(load, Date.now() < fastUntil.current ? 5000 : 30000)
      if (!f.warming && briefFor.current !== f.count) {
        briefFor.current = f.count
        api.brief().then(setBrief).catch(() => {})
      }
    }).catch((e) => setErr(e.message))
    loadRef.current = () => { clearTimeout(timer); load() }
    load()
    return () => clearTimeout(timer)
  }, [])

  const [retrying, setRetrying] = useState(false)
  const retryNow = () => {
    setRetrying(true)
    fastUntil.current = Date.now() + 180000
    api.retry().catch(() => {}).finally(() => {
      loadRef.current && loadRef.current()
      setTimeout(() => setRetrying(false), 8000)
    })
  }

  if (err) return <div className="loading">Could not load feed: {err}</div>
  if (!feed) return (
    <div className="loading">
      <span className="spinner" />
      Starting the live scan — SEC filings, prices, macro. First results within a minute.
    </div>
  )

  const today = new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })
  const rows = feed.rows
    .filter((r) =>
      !q || r.ticker.toLowerCase().includes(q.toLowerCase()) ||
      r.name.toLowerCase().includes(q.toLowerCase()))
    .filter((r) => verdictF === 'ALL' || r.verdict === verdictF)
    .filter((r) => !hideLowDq || r.data_quality !== 'low')
    .sort(SORTS[sortBy].fn)

  return (
    <div>
      <div className="title-lg">ValueScope</div>
      <div className="subtitle">{today}</div>

      <div className="toolbar">
        <input className="search" placeholder="Search any ticker or company (US, EU & EM via US listings)"
          value={q} onChange={(e) => onQuery(e.target.value)} />
        <button className={'pill-btn' + (showFilters ? ' on' : '')} title="Filters & sorting"
          onClick={() => setShowFilters((v) => !v)}>≡</button>
      </div>

      {showFilters && (
        <div className="filterbar">
          <div className="frow">
            <span className="flabel">Sort</span>
            {Object.entries(SORTS).map(([id, s]) => (
              <span key={id} className={'tag' + (sortBy === id ? ' blue' : '')}
                onClick={() => setSortBy(id)} role="button">{s.label}</span>
            ))}
          </div>
          <div className="frow">
            <span className="flabel">Verdict</span>
            {['ALL', 'BUY', 'HOLD', 'SELL'].map((v) => (
              <span key={v}
                className={'tag' + (verdictF === v ? (v === 'BUY' ? ' green' : v === 'SELL' ? ' red' : ' blue') : '')}
                onClick={() => setVerdictF(v)} role="button">{v === 'ALL' ? 'All' : v}</span>
            ))}
            <span className="flabel" style={{ marginLeft: 12 }}>Data</span>
            <span className={'tag' + (hideLowDq ? ' amber' : '')}
              onClick={() => setHideLowDq((v) => !v)} role="button">hide low quality</span>
            <span className="muted" style={{ fontSize: 12, marginLeft: 'auto' }}>
              {rows.length}/{feed.rows.length} shown
            </span>
          </div>
        </div>
      )}

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

      {/* Warming banner with real progress while the first live scan runs */}
      {feed.warming && (
        <div className="row hairline" style={{ cursor: 'default' }}>
          <span className="spinner" />
          <div className="row-main">
            <div className="row-name">
              Scanning SEC filings… {feed.count}/{feed.universe} companies ready
            </div>
            <div className="warmbar">
              <div className="fill" style={{ width: Math.max(3, (100 * feed.count) / feed.universe) + '%' }} />
            </div>
          </div>
        </div>
      )}
      {/* Everything failed: a real explanation beats a wall of tickers */}
      {!feed.warming && feed.count === 0 && Object.keys(feed.failed || {}).length > 0 && (
        <div className="card">
          <div className="eyebrow" style={{ color: T.amber }}>Market data sources rate-limited</div>
          <div className="lead">
            The market-data sources are rate-limiting this network, so no company can be
            valued right now. Nothing is broken — the scanner retries automatically every
            few minutes and this page refreshes itself when data flows again.
          </div>
          <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
            SEC filings are unaffected. ValueScope never shows simulated numbers.
          </div>
          <button className="pill-btn" disabled={retrying}
            style={{ marginTop: 10, width: 'auto', padding: '0 16px', opacity: retrying ? 0.6 : 1 }}
            onClick={retryNow}>
            {retrying ? <><span className="spinner" style={{ width: 10, height: 10 }} />Rescanning…</> : 'Retry now'}
          </button>
          <ScannerStatus scanner={feed.scanner} />
        </div>
      )}
      {!feed.warming && feed.count > 0 && Object.keys(feed.failed || {}).length > 0 && (
        <div className="row hairline" style={{ cursor: 'default' }}>
          <div className="row-main">
            <div className="row-name">
              Skipped (source unavailable, auto-retrying):{' '}
              {Object.keys(feed.failed).slice(0, 8).join(', ')}
              {Object.keys(feed.failed).length > 8 ? ` +${Object.keys(feed.failed).length - 8} more` : ''}
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

function ScannerStatus({ scanner }) {
  if (!scanner) return null
  const busy = scanner.queue > 0
  return (
    <div className="muted" style={{ fontSize: 12, marginTop: 10, display: 'flex', alignItems: 'center' }}>
      {busy && <span className="spinner" style={{ width: 10, height: 10 }} />}
      {busy
        ? `Background scanner running — ${scanner.queue} companies in the queue.`
        : scanner.cooldown_s > 0
          ? `Background scanner waiting out a source cool-down (~${scanner.cooldown_s}s), then retries automatically.`
          : 'Background scanner idle — next automatic retry within 5 minutes.'}
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
