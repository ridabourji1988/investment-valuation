import { useEffect, useState, useMemo } from 'react'
import { api } from '../lib/api'
import { usd, pct, num, signed } from '../lib/format'
import { T, verdictColor } from '../theme'
import { PriceChart } from './Charts'
import { CalcProvider, Calc } from './Calc'
import { valuePerShare } from '../lib/dcf'
import { Disclaimer } from './Feed'

// Trading-day counts to slice from the tail of the daily history series.
const RANGES = { '1W': 5, '1M': 22, '3M': 66, '6M': 130, '1Y': Infinity }

export default function Asset({ ticker, formulas, onClose }) {
  const [a, setA] = useState(null)
  const [narr, setNarr] = useState(null)
  const [range, setRange] = useState('1Y')
  const [err, setErr] = useState(null)

  useEffect(() => {
    setA(null); setNarr(null)
    api.asset(ticker).then(setA).catch((e) => setErr(e.message))
    api.narrative(ticker).then(setNarr).catch(() => {})
  }, [ticker])

  if (err) return <Modal onClose={onClose}><div className="loading">Error: {err}</div></Modal>
  if (!a) return <Modal onClose={onClose}><div className="loading">Valuing {ticker}…</div></Modal>

  const chg = a.margin_of_safety
  return (
    <Modal onClose={onClose}>
      <CalcProvider traces={a.traces} formulas={formulas}>
        {/* Header */}
        <div style={{ padding: '4px 16px 0' }}>
          <div style={{ fontSize: 26, fontWeight: 800 }}>{a.ticker}</div>
          <div className="muted" style={{ fontSize: 14 }}>{a.name} · {a.exchange}</div>
          <div style={{ marginTop: 8 }}>
            <span className="tag blue">{a.sector}</span>
            <span className="tag">{(a.idea_category || '').replace('_', ' ')}</span>
            <span className={'tag ' + (a.data_quality === 'high' ? 'green' : a.data_quality === 'medium' ? 'amber' : 'red')}>
              data: {a.data_quality}
            </span>
            {a.sources?.fundamentals && <span className="tag">{a.sources.fundamentals.includes('20-F') || a.sources.fundamentals.includes('converted') ? 'IFRS filer' : 'SEC filer'}</span>}
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginTop: 8 }}>
            <span style={{ fontSize: 30, fontWeight: 700 }} className="tnum">{usd(a.price)}</span>
            <span style={{ color: chg >= 0 ? T.green : T.red, fontWeight: 700 }}>
              {chg >= 0 ? pct(chg) + ' under fair value' : pct(-chg) + ' over fair value'}
            </span>
          </div>
        </div>

        {/* Range selector */}
        <div className="ranges">
          {Object.keys(RANGES).map((r) => (
            <div key={r} className={'range ' + (r === range ? 'sel' : '')} onClick={() => setRange(r)}>{r}</div>
          ))}
        </div>

        {/* Price chart with blue dashed fair-value line */}
        <PriceChart history={a.price_history.slice(-RANGES[range])} fairValue={a.fair_value} />

        {/* Stats grid */}
        <div className="card" style={{ padding: 0 }}>
          <div className="stats">
            <Stat k="Fair value" metric="intrinsic_value"><span>{usd(a.fair_value)}</span></Stat>
            <Stat k="Margin of safety" metric="margin_of_safety"><span style={{ color: chg >= 0 ? T.green : T.red }}>{pct(a.margin_of_safety)}</span></Stat>
            <Stat k="Quality" metric="quality"><span>{num(a.quality, 0)}/100</span></Stat>
            <Stat k="P(value > price)" metric="monte_carlo"><span>{pct(a.prob_value_gt_price)}</span></Stat>
            <Stat k="Implied growth" metric="implied_growth"><span>{pct(a.implied_growth)}</span></Stat>
            <Stat k="Verdict" metric="verdict"><span style={{ color: verdictColor(a.verdict.action) }}>{a.verdict.action}</span></Stat>
          </div>
        </div>

        {/* Verdict card */}
        <VerdictCard a={a} />

        {/* What is this company */}
        <NarrativeCard title="What is this company?" block={narr?.blocks?.business}
          fallback={`${a.name} operates in the ${a.sector} sector on ${a.exchange}.`} />

        {/* Quality */}
        <QualityCard a={a} />

        {/* What is it worth */}
        <WorthCard a={a} narr={narr} />

        {/* Value-trap check */}
        <ValueTrapCard a={a} />

        {/* What could go wrong */}
        <ScenarioCard a={a} />

        {/* Macro & cycle context */}
        <MacroContextCard ticker={a.ticker} fairValue={a.fair_value} />

        {/* Verdict memo (Apple News style) */}
        {narr?.blocks?.memo && (
          <div className="card memo">
            <div className="src">
              Verdict memo · {narr.blocks.memo.ai ? narr.blocks.memo.source : 'ValueScope engine'}
              {narr.blocks.memo.ai ? <span className="badge ai">AI</span> : <span className="badge">deterministic</span>}
              {narr.blocks.memo.guardrail && !narr.blocks.memo.guardrail.ok &&
                <span className="badge warn">guardrail</span>}
            </div>
            <div className="headline">Should you care about {a.ticker}?</div>
            <div className="body">{narr.blocks.memo.text}</div>
          </div>
        )}

        <Disclaimer />
      </CalcProvider>
    </Modal>
  )
}

function Modal({ children, onClose }) {
  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="sheet" onClick={(e) => e.stopPropagation()}>
        <div className="grabber" />
        <div className="sheet-head">
          <span className="badge">Asset 360</span>
          <button className="x" onClick={onClose} aria-label="close">✕</button>
        </div>
        {children}
      </div>
    </div>
  )
}

function Stat({ k, metric, children }) {
  return (
    <div className="cell">
      <div className="stat-k">{k}</div>
      <div className="stat-v tnum">
        {metric ? <Calc metricId={metric}>{children}</Calc> : children}
      </div>
    </div>
  )
}

function VerdictCard({ a }) {
  const v = a.verdict
  // Gauge: price position between 0 and 2x fair value; fair value at center.
  const ratio = Math.max(0, Math.min(1, a.price / (a.fair_value * 2)))
  return (
    <div className="card">
      <div className="eyebrow">Verdict</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ fontSize: 28, fontWeight: 800, color: verdictColor(v.action) }}>
          <Calc metricId="verdict">{v.action}</Calc>
        </span>
        <span className="muted">· {v.confidence} confidence · {v.horizon}</span>
      </div>
      <div className="gauge">
        <div className="fill" style={{ width: pctWidth(ratio), background: verdictColor(v.action) }} />
        <div className="mark" style={{ left: '50%' }} title="fair value" />
      </div>
      <div className="muted" style={{ fontSize: 13 }}>Price {usd(a.price)} vs fair value {usd(a.fair_value)}</div>
      <div style={{ marginTop: 8 }}>{v.sizing}</div>
      <ul style={{ margin: '8px 0 0', paddingLeft: 18, color: T.gray2, fontSize: 14 }}>
        {v.reasons.map((r, i) => <li key={i} style={{ marginBottom: 3 }}>{r}</li>)}
      </ul>
    </div>
  )
}

function NarrativeCard({ title, block, fallback }) {
  const text = block?.text || fallback
  return (
    <div className="card">
      <div className="eyebrow">{title}{block?.ai ? <span className="badge ai">AI</span> : null}</div>
      <div className="lead">{text}</div>
    </div>
  )
}

function QualityCard({ a }) {
  const q = a.traces.quality?.result
  if (!q) return null
  return (
    <div className="card">
      <div className="eyebrow">Quality</div>
      <div style={{ fontSize: 28, fontWeight: 800 }}>
        <Calc metricId="quality">{num(q.total, 0)}<span className="muted" style={{ fontSize: 16 }}> /100</span></Calc>
      </div>
      {Object.entries(q.bars).map(([k, val]) => (
        <div className="bar-row" key={k}>
          <div className="lab"><span>{k}</span><span className="tnum">{num(val, 0)}</span></div>
          <div className="bar"><div className="fill" style={{ width: pctWidth(val / 100), background: barColor(val) }} /></div>
        </div>
      ))}
      <div style={{ display: 'flex', gap: 12, marginTop: 12, flexWrap: 'wrap' }}>
        {a.traces.piotroski && <Pill metric="piotroski" label="Piotroski F" value={`${a.traces.piotroski.result.score}/9`} />}
        {a.traces.altman && <Pill metric="altman" label="Altman Z" value={num(a.traces.altman.result.z, 2)} tone={a.traces.altman.result.zone} />}
        {a.traces.beneish && <Pill metric="beneish" label="Beneish M" value={num(a.traces.beneish.result.m, 2)} tone={a.traces.beneish.result.likely_manipulator ? 'distress' : 'safe'} />}
      </div>
    </div>
  )
}

function Pill({ metric, label, value, tone }) {
  const color = tone === 'safe' ? T.green : tone === 'distress' ? T.red : tone === 'grey' ? T.amber : '#fff'
  return (
    <div style={{ background: T.elev, borderRadius: 10, padding: '8px 12px' }}>
      <div className="muted" style={{ fontSize: 12 }}>{label}</div>
      <div className="tnum" style={{ fontWeight: 700, color }}><Calc metricId={metric}>{value}</Calc></div>
    </div>
  )
}

function WorthCard({ a, narr }) {
  const [tab, setTab] = useState('Story')
  const tabs = ['Story', 'Assumptions', 'Reverse DCF', 'Monte Carlo']
  return (
    <div className="card">
      <div className="eyebrow">What is it worth?</div>
      <div className="tabs">
        {tabs.map((t) => <button key={t} className={'tab ' + (t === tab ? 'sel' : '')} onClick={() => setTab(t)}>{t}</button>)}
      </div>
      {tab === 'Story' && (
        <div className="lead">
          {narr?.blocks?.valuation?.text || 'Loading valuation story…'}
          {narr?.blocks?.valuation?.ai ? <span className="badge ai">AI</span> : null}
        </div>
      )}
      {tab === 'Assumptions' && <Sliders a={a} />}
      {tab === 'Reverse DCF' && (
        <div className="lead">
          At {usd(a.price)}, the market is pricing in about <Calc metricId="implied_growth"><b>{pct(a.implied_growth)}</b></Calc> revenue growth.
          The base case assumes {pct(assum(a).growth_initial)}. {a.implied_growth < assum(a).growth_initial
            ? 'The market is more pessimistic than the base case — a possible opportunity.'
            : 'The market is more optimistic than the base case — mind the risk.'}
        </div>
      )}
      {tab === 'Monte Carlo' && <MonteCarlo a={a} />}
    </div>
  )
}

function Sliders({ a }) {
  const base = assum(a)
  const [g, setG] = useState(base.growth_initial)
  const [m, setM] = useState(base.target_margin)
  const [w, setW] = useState(base.wacc_initial)
  const val = useMemo(() => valuePerShare({ ...base, growth_initial: g, target_margin: m, wacc_initial: w }),
    [base, g, m, w])
  const mos = (val - a.price) / val
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span className="muted">Live fair value</span>
        <span style={{ fontSize: 24, fontWeight: 800 }} className="tnum">{usd(val)}</span>
      </div>
      <div className="muted" style={{ fontSize: 13, marginBottom: 8 }}>
        Margin of safety {pct(mos)} at price {usd(a.price)}
      </div>
      <Slider label="Initial growth" value={g} min={-0.05} max={0.4} step={0.005} onChange={setG} fmt={pct} />
      <Slider label="Target margin" value={m} min={0.02} max={0.5} step={0.005} onChange={setM} fmt={pct} />
      {/* Bounds must include the base value — several firms' WACC sits below
          the terminal WACC, and only the (fixed) terminal WACC constrains TV. */}
      <Slider label="WACC" value={w} min={Math.min(0.03, base.wacc_initial)}
        max={Math.max(0.18, base.wacc_initial)} step={0.0025} onChange={setW} fmt={pct} />
      <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
        Sliders recompute the same 10-year FCFF model client-side. Reset by reopening.
      </div>
    </div>
  )
}

function Slider({ label, value, min, max, step, onChange, fmt }) {
  return (
    <div className="bar-row">
      <div className="lab"><span>{label}</span><span className="tnum">{fmt(value)}</span></div>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        style={{ width: '100%', accentColor: T.blue }} />
    </div>
  )
}

function MonteCarlo({ a }) {
  const mc = a.monte_carlo
  const lo = mc.p10, mid = mc.p50, hi = mc.p90
  const span = hi - lo || 1
  const priceLeft = Math.max(0, Math.min(1, (a.price - lo) / span))
  return (
    <div>
      <div className="lead" style={{ marginBottom: 10 }}>
        In <Calc metricId="monte_carlo"><b>{pct(mc.prob_value_gt_price)}</b></Calc> of {num(mc.runs, 0)} simulations the stock looked undervalued.
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }} className="muted">
        <span>P10 {usd(lo)}</span><span>P50 {usd(mid)}</span><span>P90 {usd(hi)}</span>
      </div>
      <div className="gauge" style={{ height: 10, marginTop: 6 }}>
        <div className="fill" style={{ left: 0, width: '100%', background: T.elev }} />
        <div className="fill" style={{ left: '10%', width: '80%', background: '#0a84ff55' }} />
        <div className="mark" style={{ left: pctWidth(priceLeft), background: '#fff' }} title="price" />
      </div>
      <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>White marker = today’s price.</div>
    </div>
  )
}

function ValueTrapCard({ a }) {
  const vt = a.traces.value_trap?.result
  if (!vt) return null
  return (
    <div className="card">
      <div className="eyebrow">Value-trap check <Calc metricId="value_trap"><span className="badge">{vt.flags}/8 flags</span></Calc></div>
      <div>
        {Object.entries(vt.signals).map(([k, on]) => (
          <div key={k} className="step" style={{ borderBottom: '0.5px solid ' + T.separator }}>
            <span>{k}</span>
            <span style={{ color: on ? T.red : T.green }}>{on ? '⚠ flag' : '✓ clear'}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function ScenarioCard({ a }) {
  const mc = a.monte_carlo
  const rows = [
    { k: 'Bear', v: mc.p10, p: '10%', c: T.red },
    { k: 'Base', v: mc.p50, p: '50%', c: T.amber },
    { k: 'Bull', v: mc.p90, p: '90%', c: T.green },
  ]
  return (
    <div className="card">
      <div className="eyebrow">What could go wrong?</div>
      {rows.map((r) => (
        <div key={r.k} className="step">
          <span><b style={{ color: r.c }}>{r.k}</b> <span className="muted">({r.p} percentile)</span></span>
          <span className="tnum">{usd(r.v)} · {signed((r.v - a.price) / a.price * 100, 0)}%</span>
        </div>
      ))}
      <ul style={{ margin: '10px 0 0', paddingLeft: 18, color: T.gray2, fontSize: 14 }}>
        {(a.traces.intrinsic_value.caveats || []).map((c, i) => <li key={i} style={{ marginBottom: 3 }}>{c}</li>)}
      </ul>
    </div>
  )
}

function MacroContextCard({ ticker, fairValue }) {
  const [row, setRow] = useState(null)
  useEffect(() => {
    api.rateSensitivity(50).then((d) => setRow(d.rows.find((r) => r.ticker === ticker))).catch(() => {})
  }, [ticker])
  if (!row) return null
  return (
    <div className="card">
      <div className="eyebrow">Macro &amp; cycle context — fair value at 10Y ±50bp</div>
      <div className="stats" style={{ marginTop: 6 }}>
        <div className="cell"><div className="stat-k">−50 bp</div><div className="stat-v tnum" style={{ color: T.green }}>{usd(row.minus_50bp)}</div></div>
        <div className="cell"><div className="stat-k">Base</div><div className="stat-v tnum">{usd(row.base)}</div></div>
        <div className="cell"><div className="stat-k">+50 bp</div><div className="stat-v tnum" style={{ color: T.red }}>{usd(row.plus_50bp)}</div></div>
      </div>
      <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
        Rates move fair value because they change the discount rate. Macro adjusts sizing, never the verdict.
      </div>
    </div>
  )
}

// helpers
function assum(a) { return a.dcf_assumptions }
function pctWidth(x) { return Math.max(0, Math.min(100, x * 100)) + '%' }
function barColor(v) { return v >= 66 ? T.green : v >= 33 ? T.amber : T.red }
