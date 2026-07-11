import { createContext, useContext, useState, useCallback } from 'react'
import { formatInput, formatValue, num } from '../lib/format'
import { InlineSeries } from './Charts'

// Context carries the asset's traces (keyed by metric_id) and the formula
// registry, so any <Calc> can open its trace and drill into computed inputs.
const CalcCtx = createContext(null)

export function CalcProvider({ traces, formulas, links, children }) {
  const [stack, setStack] = useState([]) // stack of metric ids (recursive drill-down)

  const open = useCallback((metricId) => {
    if (traces && traces[metricId]) setStack((s) => [...s, metricId])
  }, [traces])

  const close = useCallback(() => setStack((s) => s.slice(0, -1)), [])
  const closeAll = useCallback(() => setStack([]), [])

  return (
    <CalcCtx.Provider value={{ traces, formulas, links, open }}>
      {children}
      {stack.length > 0 && (
        <CalcSheet
          trace={traces[stack[stack.length - 1]]}
          depth={stack.length}
          onBack={close}
          onClose={closeAll}
        />
      )}
    </CalcCtx.Provider>
  )
}

export function Calc({ metricId, children }) {
  const ctx = useContext(CalcCtx)
  if (!ctx || !ctx.traces || !ctx.traces[metricId]) return <span>{children}</span>
  return (
    <span className="calc" onClick={() => ctx.open(metricId)} role="button" tabIndex={0}>
      {children}
    </span>
  )
}

function CalcSheet({ trace, depth, onBack, onClose }) {
  const ctx = useContext(CalcCtx)
  const formula = ctx.formulas?.[trace.formula_id]
  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="sheet" onClick={(e) => e.stopPropagation()}>
        <div className="grabber" />
        <div className="sheet-head">
          {depth > 1 && (
            <button className="x" onClick={onBack} aria-label="back">‹</button>
          )}
          <strong style={{ fontSize: 17 }}>Show Calculation</strong>
          <button className="x" onClick={onClose} aria-label="close">✕</button>
        </div>
        <div className="sheet-body">
          {/* 1. What this means */}
          {trace.plain && (
            <div className="sheet-section">
              <div className="h">What this means</div>
              <div>{trace.plain}</div>
            </div>
          )}

          {/* 2. Formula */}
          <div className="sheet-section">
            <div className="h">Formula</div>
            <div style={{ fontFamily: 'ui-monospace, Menlo, monospace', fontSize: 14 }}>
              {formula?.expression || trace.formula_id}
            </div>
          </div>

          {/* 3. Inputs table with recursive drill-down */}
          {trace.inputs?.length > 0 && (
            <div className="sheet-section">
              <div className="h">Inputs</div>
              <table className="inputs">
                <tbody>
                  {trace.inputs.map((inp, i) => (
                    <tr key={i}>
                      <td style={{ width: '42%' }}>
                        {inp.name}
                        {inp.trace_id && ctx.traces[inp.trace_id] && (
                          <span className="drill" onClick={() => ctx.open(inp.trace_id)}> ↗</span>
                        )}
                      </td>
                      <td className="tnum"><InputValue value={inp.value} unit={inp.unit} /></td>
                      <td className="src">
                        <SourceRef input={inp} links={ctx.links} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* 4. Substitution steps */}
          {trace.steps?.length > 0 && (
            <div className="sheet-section">
              <div className="h">Step by step</div>
              {trace.steps.map((s, i) => (
                <div className="step" key={i}>
                  <span>{s.label} <span className="expr">{s.expression}</span></span>
                  <span className="tnum">{formatValue(s.value)}</span>
                </div>
              ))}
              <ResultBlock result={trace.result} unit={trace.unit} />
            </div>
          )}

          {/* 5. Source citation */}
          {trace.citation && (
            <div className="sheet-section">
              <div className="h">Source</div>
              <div className="src" style={{ color: 'var(--gray2)' }}>{trace.citation}</div>
              <div className="src" style={{ marginTop: 4 }}>
                Formula <code>{trace.formula_id}</code> v{trace.formula_version} ·
                engine v{trace.engine_version}
              </div>
            </div>
          )}

          {/* 6. Caveats */}
          {trace.caveats?.length > 0 && (
            <div className="sheet-section">
              <div className="h">Caveats</div>
              <ul style={{ margin: 0, paddingLeft: 18, color: 'var(--gray2)', fontSize: 14 }}>
                {trace.caveats.map((c, i) => <li key={i} style={{ marginBottom: 4 }}>{c}</li>)}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// Source label with a verify-at-source link when the input came from a
// linkable origin (SEC filing for edgar inputs, quote page for market data).
function SourceRef({ input, links }) {
  const text = `${input.source_type}${input.source_ref ? ` · ${input.source_ref}` : ''}${input.asof ? ` (${input.asof})` : ''}`
  const url = input.source_type === 'edgar'
    ? (links?.filing?.url || links?.filings_index)
    : ['yfinance', 'market', 'price'].includes(input.source_type) ? links?.prices : null
  if (!url) return <>{text}</>
  return <a href={url} target="_blank" rel="noreferrer">{text} ↗</a>
}

function InputValue({ value, unit }) {
  if (Array.isArray(value) && value.length > 4 && value.every((v) => typeof v === 'number')) {
    return (
      <span>
        <InlineSeries values={value} />
        <span className="muted" style={{ marginLeft: 8, fontSize: 12 }}>
          last {formatInput(value[value.length - 1], unit)}
        </span>
      </span>
    )
  }
  if (value === null || value === undefined) {
    return <span className="badge warn">unavailable</span>
  }
  return <>{formatInput(value, unit)}</>
}

// Dict results (regime, Monte Carlo, scores…) render as labelled rows, never
// as raw JSON. Booleans become status dots; nested dicts become sub-lists.
function ResultBlock({ result, unit }) {
  if (result === null || result === undefined || typeof result !== 'object') {
    return (
      <div className="result-line">
        <span>Result</span>
        <span className="tnum">{formatValue(result)}{' '}
          <span className="muted" style={{ fontWeight: 400, fontSize: 13 }}>{unit}</span></span>
      </div>
    )
  }
  const scalar = Object.entries(result).filter(([, v]) => typeof v !== 'object' || v === null)
  const nested = Object.entries(result).filter(([, v]) => v && typeof v === 'object')
  return (
    <div style={{ marginTop: 10 }}>
      <div className="result-line" style={{ paddingBottom: 8 }}>
        <span>Result</span>
        <span className="muted" style={{ fontWeight: 400, fontSize: 13 }}>{unit}</span>
      </div>
      {scalar.map(([k, v]) => (
        <div className="step" key={k}>
          <span>{labelize(k)}</span>
          <span className="tnum">{formatValue(v)}</span>
        </div>
      ))}
      {nested.map(([k, obj]) => (
        <div key={k} style={{ margin: '8px 0' }}>
          <div className="h" style={{ color: 'var(--gray)', fontSize: 12, margin: '6px 0 2px' }}>{labelize(k)}</div>
          {Object.entries(obj).map(([kk, vv]) => (
            <div className="step" key={kk}>
              <span>{labelize(kk)}</span>
              {typeof vv === 'boolean' ? (
                <span><span className="dot" style={{ background: vv ? 'var(--blue)' : 'var(--elev)', marginRight: 6 }} />{vv ? 'yes' : 'no'}</span>
              ) : (
                <span className="tnum">{formatValue(vv)}</span>
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

function labelize(key) {
  const nice = String(key).replace(/_/g, ' ')
  return nice.charAt(0).toUpperCase() + nice.slice(1)
}
