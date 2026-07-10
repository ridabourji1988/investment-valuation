"""10-year FCFF discounted cash flow (PRD §6.1).

A faithful implementation of Damodaran's fcffsimpleginzu structure:

  * Years 1-5: revenue grows at the high-growth rate; the operating margin
    ramps linearly from today's margin to the target margin.
  * Years 6-10: growth fades linearly to the stable (terminal) rate and the
    cost of capital fades to its mature level.
  * Reinvestment is growth-driven:  Reinvestment = dRevenue / SalesToCapital.
  * FCFF = EBIT*(1-t) - Reinvestment.
  * Terminal value uses the stable-phase reinvestment rate g / ROIC:
        FCFF_11 = NOPAT_11 * (1 - g/ROIC_stable)
        TV_10   = FCFF_11 / (WACC_stable - g)      with  g <= Rf.

Sources: Damodaran, Investment Valuation 3e ch. 12-15; fcffsimpleginzu
spreadsheet (NYU Stern).
"""
from __future__ import annotations

from dataclasses import dataclass

from ..registry import get_formula
from .trace import CalculationTrace, inp, step


@dataclass
class DCFAssumptions:
    revenue_base: float           # current annual revenue (US$)
    ebit_margin_base: float       # current operating margin (decimal)
    target_margin: float          # terminal operating margin (decimal)
    growth_initial: float         # years 1-5 revenue growth (decimal)
    growth_terminal: float        # stable growth (decimal); must be <= risk_free
    sales_to_capital: float       # reinvestment efficiency (revenue per $1 capital)
    wacc_initial: float           # high-growth cost of capital (decimal)
    wacc_terminal: float          # mature cost of capital (decimal)
    tax_rate: float               # marginal tax rate (decimal)
    shares: float                 # diluted shares outstanding
    net_debt: float               # total debt - cash & equivalents (US$)
    risk_free: float              # 10Y Treasury; hard cap on terminal growth
    roic_stable: float | None = None  # mature ROIC; defaults to wacc_terminal
    years_high: int = 5
    years_total: int = 10

    def validate(self) -> None:
        if self.shares <= 0:
            raise ValueError("shares must be positive")
        if self.sales_to_capital <= 0:
            raise ValueError("sales_to_capital must be positive")
        if self.wacc_terminal <= self.growth_terminal:
            raise ValueError("WACC_stable must exceed terminal growth for a finite terminal value")
        if self.growth_terminal > self.risk_free + 1e-9:
            raise ValueError("terminal growth must not exceed the risk-free rate (g <= Rf)")


def fcff(ebit: float, tax_rate: float, delta_revenue: float, sales_to_capital: float) -> float:
    """Growth-driven free cash flow to the firm for a single year."""
    reinvestment = delta_revenue / sales_to_capital
    return ebit * (1.0 - tax_rate) - reinvestment


def terminal_value(fcff_next: float, wacc_stable: float, growth: float) -> float:
    """Gordon-growth terminal value on FCFF."""
    if wacc_stable <= growth:
        raise ValueError("WACC_stable must exceed growth")
    return fcff_next / (wacc_stable - growth)


def _linspace(start: float, end: float, n: int) -> list[float]:
    if n <= 1:
        return [end]
    return [start + (end - start) * i / (n - 1) for i in range(n)]


def _project(a: DCFAssumptions):
    """Return per-year projection dicts for years 1..10 (list of dicts)."""
    yh, yt = a.years_high, a.years_total
    fade_years = yt - yh  # e.g. 5

    # Growth path: constant for high phase, linear fade to terminal thereafter.
    growth_path = [a.growth_initial] * yh
    if fade_years > 0:
        # interpolate from growth_initial (at year yh) down to growth_terminal (at year yt)
        for k in range(1, fade_years + 1):
            g = a.growth_initial + (a.growth_terminal - a.growth_initial) * k / fade_years
            growth_path.append(g)

    # Margin path: ramp from base to target over the high phase, then hold.
    margin_ramp = _linspace(a.ebit_margin_base, a.target_margin, yh)
    margin_path = margin_ramp + [a.target_margin] * fade_years

    # WACC path: constant in high phase, fade to terminal over fade phase.
    wacc_path = [a.wacc_initial] * yh
    if fade_years > 0:
        for k in range(1, fade_years + 1):
            w = a.wacc_initial + (a.wacc_terminal - a.wacc_initial) * k / fade_years
            wacc_path.append(w)

    rows = []
    prev_rev = a.revenue_base
    cum_df = 1.0
    for t in range(1, yt + 1):
        g = growth_path[t - 1]
        margin = margin_path[t - 1]
        w = wacc_path[t - 1]
        rev = prev_rev * (1.0 + g)
        ebit = rev * margin
        nopat = ebit * (1.0 - a.tax_rate)
        reinvest = (rev - prev_rev) / a.sales_to_capital
        f = nopat - reinvest
        cum_df *= 1.0 / (1.0 + w)
        rows.append({
            "year": t, "growth": g, "revenue": rev, "margin": margin, "ebit": ebit,
            "nopat": nopat, "reinvestment": reinvest, "fcff": f, "wacc": w,
            "discount_factor": cum_df, "pv_fcff": f * cum_df,
        })
        prev_rev = rev
    return rows


def value_firm(a: DCFAssumptions) -> dict:
    """Compute enterprise value, equity value and per-share value.

    Returns a plain dict (used by Monte Carlo hot loop; no trace overhead)."""
    a.validate()
    rows = _project(a)
    pv_explicit = sum(r["pv_fcff"] for r in rows)

    last = rows[-1]
    roic = a.roic_stable if a.roic_stable is not None else a.wacc_terminal
    g = a.growth_terminal
    reinvest_rate = 0.0 if roic <= 0 else g / roic
    rev_11 = last["revenue"] * (1.0 + g)
    ebit_11 = rev_11 * a.target_margin
    nopat_11 = ebit_11 * (1.0 - a.tax_rate)
    fcff_11 = nopat_11 * (1.0 - reinvest_rate)
    tv_10 = terminal_value(fcff_11, a.wacc_terminal, g)
    pv_tv = tv_10 * last["discount_factor"]

    ev = pv_explicit + pv_tv
    equity = ev - a.net_debt
    per_share = equity / a.shares
    return {
        "rows": rows,
        "pv_explicit": pv_explicit,
        "fcff_11": fcff_11,
        "terminal_value": tv_10,
        "pv_terminal": pv_tv,
        "enterprise_value": ev,
        "equity_value": equity,
        "value_per_share": per_share,
        "reinvestment_rate_stable": reinvest_rate,
    }


def intrinsic_value(a: DCFAssumptions, *, price: float | None = None) -> CalculationTrace:
    """Full valuation with a CalculationTrace (per-year FCFF steps)."""
    r = value_firm(a)
    spec = get_formula("intrinsic_value_fcff")
    steps = []
    for row in r["rows"]:
        steps.append(step(
            f"Year {row['year']}",
            f"FCFF={row['fcff']:,.0f} · DF={row['discount_factor']:.4f}",
            row["pv_fcff"],
        ))
    steps.append(step("Sum of PV(FCFF₁…₁₀)", "Σ discounted FCFF", r["pv_explicit"]))
    steps.append(step("Terminal value at year 10",
                      f"FCFF₁₁ {r['fcff_11']:,.0f} ÷ (WACC {a.wacc_terminal:.4f} − g {a.growth_terminal:.4f})",
                      r["terminal_value"]))
    steps.append(step("PV of terminal value", "TV × DF₁₀", r["pv_terminal"]))
    steps.append(step("Enterprise value", "PV(FCFF) + PV(TV)", r["enterprise_value"]))
    steps.append(step("Equity value", f"EV − net debt {a.net_debt:,.0f}", r["equity_value"]))
    steps.append(step("Value per share", f"equity ÷ {a.shares:,.0f} shares", r["value_per_share"]))

    caveats = [
        "Assumes terminal growth ≤ risk-free rate (no perpetual out-growth of the economy).",
        "Terminal value is the majority of the estimate; small WACC/growth changes move it materially.",
        f"Reinvestment in perpetuity assumes ROIC = {(a.roic_stable if a.roic_stable is not None else a.wacc_terminal):.1%}.",
    ]
    if price is not None:
        caveats.append(f"At {price:,.2f} the market implies different assumptions — see Reverse DCF.")

    return CalculationTrace(
        metric_id="value_per_share",
        formula_id="intrinsic_value_fcff",
        formula_version=spec.version,
        result=r["value_per_share"],
        unit="US$/share",
        plain="What one share is worth today, based on the cash the whole business will generate.",
        inputs=[
            inp("Revenue₀", a.revenue_base, "US$", "edgar", "trailing-twelve-month revenue"),
            inp("Operating margin₀", a.ebit_margin_base, "decimal", "edgar", "EBIT ÷ revenue"),
            inp("Target margin", a.target_margin, "decimal", "assumption", "mature operating margin"),
            inp("Growth (yrs 1-5)", a.growth_initial, "decimal", "assumption", "high-growth revenue CAGR"),
            inp("Terminal growth", a.growth_terminal, "decimal", "assumption", "stable growth (≤ Rf)"),
            inp("Sales-to-capital", a.sales_to_capital, "ratio", "damodaran", "reinvestment efficiency"),
            inp("WACC (high)", a.wacc_initial, "decimal", "formula", "cost of capital"),
            inp("WACC (stable)", a.wacc_terminal, "decimal", "formula", "mature cost of capital"),
            inp("Tax rate", a.tax_rate, "decimal", "assumption", "marginal tax rate"),
            inp("Net debt", a.net_debt, "US$", "edgar", "total debt − cash"),
            inp("Shares", a.shares, "count", "edgar", "diluted shares outstanding"),
        ],
        steps=steps,
        citation=spec.source_citation,
        caveats=caveats,
    )
