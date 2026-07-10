import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { Disclaimer } from './Feed'

// Learn / Methodology — the formula registry rendered as human-readable pages
// with book citations (PRD §3.6).
export default function Learn() {
  const [data, setData] = useState(null)
  const [open, setOpen] = useState(null)
  useEffect(() => { api.formulas().then(setData).catch(() => {}) }, [])
  if (!data) return <div className="loading">Loading methodology…</div>

  return (
    <div>
      <div className="title-lg">Learn</div>
      <div className="subtitle">Every formula, its source, and its test</div>

      <div className="card">
        <div className="lead">
          ValueScope shows no unexplained number. Every metric is computed by a versioned engine and
          cites the book or paper it comes from. Continuous integration fails if any formula lacks a
          citation or a unit test that reproduces a worked example from its source.
        </div>
      </div>

      <div className="card" style={{ padding: 0 }}>
        {data.formulas.map((f) => (
          <div key={f.formula_id}>
            <div className="row hairline" onClick={() => setOpen(open === f.formula_id ? null : f.formula_id)}>
              <div className="row-main">
                <div className="row-ticker" style={{ fontSize: 15 }}>{f.name}</div>
                <div className="row-name">{f.citation}</div>
              </div>
              <span className="muted">{open === f.formula_id ? '−' : '+'}</span>
            </div>
            {open === f.formula_id && (
              <div style={{ padding: '4px 16px 16px' }}>
                <div className="sheet-section">
                  <div className="h" style={{ color: 'var(--gray)', fontSize: 13 }}>Formula</div>
                  <div style={{ fontFamily: 'ui-monospace, Menlo, monospace', fontSize: 13.5 }}>{f.expression}</div>
                </div>
                <div className="sheet-section">
                  <div className="h" style={{ color: 'var(--gray)', fontSize: 13 }}>Variables</div>
                  <table className="inputs">
                    <tbody>
                      {Object.entries(f.variables).map(([k, v]) => (
                        <tr key={k}><td style={{ width: '32%' }}><code>{k}</code></td><td className="src">{v}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="src">Implementation: <code>{f.implementation}</code> · v{f.version}</div>
                <div className="src">Tests: {f.tests.join(', ')}</div>
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="card">
        <div className="eyebrow">Transparency</div>
        <div className="lead">
          Data sources: SEC EDGAR (filings), Yahoo Finance (prices), FRED (macro), Damodaran NYU
          datasets (betas, ERP, margins). Update cadence: on-demand per ticker; macro refreshed on
          rate moves. Limitations: valuations are estimates dependent on assumptions; demo data is
          illustrative until live sources are enabled. Open source, MIT/AGPL.
        </div>
      </div>
      <Disclaimer />
    </div>
  )
}
