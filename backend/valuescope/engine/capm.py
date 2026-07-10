"""Cost of equity via CAPM (PRD §6.1).

Re = Rf + beta * ERP
    Damodaran, Investment Valuation 3e, ch. 7-8.
"""
from __future__ import annotations

from ..registry import get_formula
from .trace import CalculationTrace, inp, step

_F = "capm_cost_of_equity"


def cost_of_equity(
    rf: float,
    beta: float,
    erp: float,
    *,
    rf_source: str = "FRED DGS10",
    rf_asof: str = "",
    erp_source: str = "Damodaran implied ERP",
    erp_asof: str = "",
    beta_trace_id: str | None = None,
) -> CalculationTrace:
    """Return cost of equity with its CalculationTrace.

    All rates are decimals (0.04 == 4%).
    """
    re = rf + beta * erp
    spec = get_formula(_F)
    return CalculationTrace(
        metric_id="cost_of_equity",
        formula_id=_F,
        formula_version=spec.version,
        result=re,
        unit="decimal",
        plain="The annual return equity investors require to hold this stock.",
        inputs=[
            inp("Rf", rf, "decimal", "fred", rf_source, rf_asof),
            inp("beta", beta, "unitless", "formula" if beta_trace_id else "damodaran",
                "bottom-up beta", "", beta_trace_id),
            inp("ERP", erp, "decimal", "damodaran", erp_source, erp_asof),
        ],
        steps=[
            step("Plug into CAPM", f"Re = {rf:.4f} + {beta:.4f} × {erp:.4f}", re),
        ],
        citation=spec.source_citation,
        caveats=[
            "CAPM assumes a single market factor and a stable ERP.",
            "Beta is estimated bottom-up from comparable firms, not a single regression.",
        ],
    )
