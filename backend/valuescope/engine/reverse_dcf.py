"""Reverse DCF (PRD §6.1).

Solve for the high-growth rate that makes the model's per-share value equal the
market price, by bisection. Answers "what is the market assuming?".

Sources: Damodaran, Narrative and Numbers ch. 11; Mauboussin & Rappaport,
Expectations Investing.
"""
from __future__ import annotations

import copy

from ..registry import get_formula
from .dcf import DCFAssumptions, value_firm
from .trace import CalculationTrace, inp, step


def _value_at_growth(base: DCFAssumptions, g: float) -> float:
    a = copy.copy(base)
    a.growth_initial = g
    return value_firm(a)["value_per_share"]


def implied_growth(
    base: DCFAssumptions,
    price: float,
    *,
    low: float = -0.20,
    high: float = 0.60,
    tol: float = 1e-4,
    max_iter: int = 200,
) -> CalculationTrace:
    """Bisection solve for growth_initial such that value_per_share == price."""
    f_low = _value_at_growth(base, low) - price
    f_high = _value_at_growth(base, high) - price

    spec = get_formula("reverse_dcf")
    steps = []
    root = None
    bracketed = f_low * f_high <= 0

    if bracketed:
        lo, hi = low, high
        for i in range(max_iter):
            mid = 0.5 * (lo + hi)
            fmid = _value_at_growth(base, mid) - price
            if abs(fmid) < tol or (hi - lo) < 1e-6:
                root = mid
                break
            if f_low * fmid < 0:
                hi = mid
                f_high = fmid
            else:
                lo = mid
                f_low = fmid
        else:
            root = 0.5 * (lo + hi)
        steps.append(step("Bracket", f"value({low:.2%})={_value_at_growth(base, low):.2f} … "
                                     f"value({high:.2%})={_value_at_growth(base, high):.2f}", "brackets price"))
        steps.append(step("Converged growth", "value(g*) = price", root))
    else:
        # Price outside model range: report the nearer bound.
        root = low if abs(f_low) < abs(f_high) else high
        steps.append(step("Outside model range",
                          "price not reproducible within [-20%, 60%] growth; reporting nearest bound", root))

    result = root
    return CalculationTrace(
        metric_id="implied_growth",
        formula_id="reverse_dcf",
        formula_version=spec.version,
        result=result,
        unit="decimal",
        plain="The revenue growth rate the current share price already assumes.",
        inputs=[
            inp("Market price", price, "US$/share", "yfinance", "last close"),
            inp("DCF assumptions", "held fixed except growth", "", "formula", "intrinsic_value_fcff"),
        ],
        steps=steps,
        citation=spec.source_citation,
        caveats=[
            "Only the high-growth rate is solved; other assumptions are held at base-case values.",
            "If the price cannot be reproduced within the search bracket, the nearest bound is returned.",
        ],
    )
