"""Weighted average cost of capital (PRD §6.1).

    WACC = (E/V) * Re + (D/V) * Rd * (1 - t)

    Damodaran, Applied Corporate Finance 4e, ch. 4.
"""
from __future__ import annotations

from ..registry import get_formula
from .trace import CalculationTrace, inp, step

_F = "wacc"


def wacc(
    equity_value: float,
    debt_value: float,
    cost_of_equity: float,
    pretax_cost_of_debt: float,
    tax_rate: float,
    *,
    re_trace_id: str | None = None,
) -> CalculationTrace:
    v = equity_value + debt_value
    if v <= 0:
        raise ValueError("Total capital (E + D) must be positive")
    we = equity_value / v
    wd = debt_value / v
    after_tax_rd = pretax_cost_of_debt * (1.0 - tax_rate)
    result = we * cost_of_equity + wd * after_tax_rd
    spec = get_formula(_F)
    return CalculationTrace(
        metric_id="wacc",
        formula_id=_F,
        formula_version=spec.version,
        result=result,
        unit="decimal",
        plain="The blended annual return the company must earn to satisfy both lenders and shareholders.",
        inputs=[
            inp("E", equity_value, "US$", "yfinance", "market capitalisation"),
            inp("D", debt_value, "US$", "edgar", "total debt (incl. capitalised leases)"),
            inp("Re", cost_of_equity, "decimal", "formula", "cost of equity (CAPM)", "", re_trace_id),
            inp("Rd", pretax_cost_of_debt, "decimal", "edgar", "pre-tax cost of debt"),
            inp("t", tax_rate, "decimal", "assumption", "marginal tax rate"),
        ],
        steps=[
            step("Equity weight", f"{equity_value:.0f} ÷ {v:.0f}", we),
            step("Debt weight", f"{debt_value:.0f} ÷ {v:.0f}", wd),
            step("After-tax cost of debt", f"{pretax_cost_of_debt:.4f} × (1 − {tax_rate:.4f})", after_tax_rd),
            step("Blend", f"{we:.4f} × {cost_of_equity:.4f} + {wd:.4f} × {after_tax_rd:.4f}", result),
        ],
        citation=spec.source_citation,
        caveats=["Uses market (not book) weights; leases are treated as debt."],
    )
