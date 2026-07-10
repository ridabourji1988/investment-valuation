import pytest

from valuescope.engine.dcf import (
    DCFAssumptions, fcff, terminal_value, value_firm, intrinsic_value,
)


def base_assumptions(**kw):
    d = dict(
        revenue_base=1_000.0, ebit_margin_base=0.20, target_margin=0.20,
        growth_initial=0.08, growth_terminal=0.025, sales_to_capital=2.0,
        wacc_initial=0.09, wacc_terminal=0.08, tax_rate=0.25, shares=100.0,
        net_debt=0.0, risk_free=0.03, roic_stable=None,
    )
    d.update(kw)
    return DCFAssumptions(**d)


def test_fcff_definition():
    # FCFF = EBIT*(1-t) - dRevenue/SalesToCapital
    # EBIT=200, t=25% -> NOPAT=150 ; dRev=80, s2c=2 -> reinvest=40 -> FCFF=110
    assert fcff(ebit=200, tax_rate=0.25, delta_revenue=80, sales_to_capital=2.0) == 110.0


def test_terminal_value_worked_example():
    # TV = FCFF_next / (WACC - g). 110 / (0.08-0.03) = 2200
    assert abs(terminal_value(110, 0.08, 0.03) - 2200.0) < 1e-9
    with pytest.raises(ValueError):
        terminal_value(110, 0.03, 0.05)  # g >= WACC


def test_ginzu_no_growth_equals_perpetuity():
    """With zero growth, constant margin and constant WACC, the whole 10-year
    model + terminal value must collapse to a simple perpetuity NOPAT/WACC.
    This is a closed-form invariant independent of the fade machinery."""
    a = base_assumptions(
        growth_initial=0.0, growth_terminal=0.0, ebit_margin_base=0.20,
        target_margin=0.20, wacc_initial=0.08, wacc_terminal=0.08, roic_stable=0.08,
    )
    r = value_firm(a)
    nopat = a.revenue_base * a.ebit_margin_base * (1 - a.tax_rate)  # 1000*0.2*0.75 = 150
    expected_ev = nopat / a.wacc_terminal                          # 150 / 0.08 = 1875
    assert abs(r["enterprise_value"] - expected_ev) < 1e-6
    assert abs(r["value_per_share"] - expected_ev / a.shares) < 1e-9


def _independent_value(a: DCFAssumptions) -> float:
    """A from-scratch re-implementation of the documented model, used purely to
    cross-check the engine (PRD §5: reproduce the spreadsheet within tolerance)."""
    yh, yt = a.years_high, a.years_total
    fade = yt - yh
    growth = [a.growth_initial] * yh + [
        a.growth_initial + (a.growth_terminal - a.growth_initial) * k / fade
        for k in range(1, fade + 1)
    ]
    margins = [a.ebit_margin_base + (a.target_margin - a.ebit_margin_base) * i / (yh - 1)
               for i in range(yh)] + [a.target_margin] * fade
    waccs = [a.wacc_initial] * yh + [
        a.wacc_initial + (a.wacc_terminal - a.wacc_initial) * k / fade
        for k in range(1, fade + 1)
    ]
    rev = a.revenue_base
    df = 1.0
    pv = 0.0
    for t in range(yt):
        prev = rev
        rev = rev * (1 + growth[t])
        ebit = rev * margins[t]
        nopat = ebit * (1 - a.tax_rate)
        reinvest = (rev - prev) / a.sales_to_capital
        f = nopat - reinvest
        df *= 1 / (1 + waccs[t])
        pv += f * df
    roic = a.roic_stable if a.roic_stable is not None else a.wacc_terminal
    g = a.growth_terminal
    rev11 = rev * (1 + g)
    nopat11 = rev11 * a.target_margin * (1 - a.tax_rate)
    fcff11 = nopat11 * (1 - g / roic)
    tv = fcff11 / (a.wacc_terminal - g)
    ev = pv + tv * df
    return (ev - a.net_debt) / a.shares


def test_intrinsic_value_worked_example():
    a = base_assumptions(ebit_margin_base=0.15, target_margin=0.22, net_debt=500,
                         growth_initial=0.10, growth_terminal=0.025)
    engine = value_firm(a)["value_per_share"]
    independent = _independent_value(a)
    assert abs(engine - independent) < 1e-6


def test_intrinsic_value_trace_has_full_steps():
    a = base_assumptions()
    trace = intrinsic_value(a, price=25.0)
    # 10 yearly steps + 6 summary steps
    assert len(trace.steps) == 16
    assert trace.unit == "US$/share"
    assert any("terminal" in c.lower() for c in trace.caveats)


def test_value_increases_with_growth():
    lo = value_firm(base_assumptions(growth_initial=0.05))["value_per_share"]
    hi = value_firm(base_assumptions(growth_initial=0.12))["value_per_share"]
    assert hi > lo


def test_terminal_growth_capped_at_risk_free():
    with pytest.raises(ValueError):
        value_firm(base_assumptions(growth_terminal=0.05, risk_free=0.03))
