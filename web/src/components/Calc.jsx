import { createContext, useContext, useState, useCallback } from 'react'
import { formatInput, num } from '../lib/format'

// Context carries the asset's traces (keyed by metric_id) and the formula
// registry, so any <Calc> can open its trace and drill into computed inputs.
const CalcCtx = createContext(null)

export function CalcProvider({ traces, formulas, children }) {
  const [stack, setStack] = useState([]) // stack of metric ids (recursive drill-down)

  const open = useCallback((metricId) => {
    if (traces && traces[metricId]) setStack((s) => [...s, metricId])
  }, [traces])

  const close = useCallback(() => setStack((s) => s.slice(0, -1)), [])
  const closeAll = useCallback(() => setStack([]), [])

  return (
    <CalcCtx.Provider value={{ traces, formulas, open }}>
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
                      <td className="tnum">{formatInput(inp.value, inp.unit)}</td>
                      <td className="src">
                        {inp.source_type}{inp.source_ref ? ` · ${inp.source_ref}` : ''}
                        {inp.asof ? ` (${inp.asof})` : ''}
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
                  <span className="tnum">{fmtStep(s.value)}</span>
                </div>
              ))}
              <div className="result-line">
                <span>Result</span>
                <span className="tnum">{fmtStep(trace.result)} <span className="muted" style={{ fontWeight: 400, fontSize: 13 }}>{trace.unit}</span></span>
              </div>
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

function fmtStep(v) {
  if (typeof v === 'boolean') return v ? 'true' : 'false'
  if (typeof v === 'number') {
    if (Math.abs(v) > 0 && Math.abs(v) < 1) return num(v, 4)
    return num(v, Math.abs(v) >= 1000 ? 0 : 2)
  }
  if (v && typeof v === 'object') return JSON.stringify(v)
  return String(v)
}
