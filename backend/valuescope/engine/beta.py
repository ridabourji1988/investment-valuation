"""Bottom-up beta (PRD §6.1).

Unlever a sector average asset beta and relever at the firm's own D/E using the
Hamada relation:

    beta_L = beta_U * (1 + (1 - t) * D/E)     (relever)
    beta_U = beta_L / (1 + (1 - t) * D/E)      (unlever)

    Damodaran, Investment Valuation 3e, ch. 8.
"""
from __future__ import annotations

from ..registry import get_formula
from .trace import CalculationTrace, inp, step

_F = "bottom_up_beta"


def unlever_beta(beta_levered: float, tax_rate: float, debt_to_equity: float) -> float:
    return beta_levered / (1.0 + (1.0 - tax_rate) * debt_to_equity)


def relever_beta(
    beta_unlevered: float,
    tax_rate: float,
    debt_to_equity: float,
    *,
    sector: str = "",
    sector_source: str = "Damodaran sector betas",
    asof: str = "",
) -> CalculationTrace:
    """Relever a sector unlevered beta at the firm's own capital structure."""
    factor = 1.0 + (1.0 - tax_rate) * debt_to_equity
    beta_l = beta_unlevered * factor
    spec = get_formula(_F)
    return CalculationTrace(
        metric_id="levered_beta",
        formula_id=_F,
        formula_version=spec.version,
        result=beta_l,
        unit="unitless",
        plain="How much this stock moves relative to the market, adjusted for its debt load.",
        inputs=[
            inp("beta_U", beta_unlevered, "unitless", "damodaran",
                f"{sector or 'sector'} unlevered beta — {sector_source}", asof),
            inp("t", tax_rate, "decimal", "assumption", "marginal tax rate"),
            inp("D/E", debt_to_equity, "ratio", "edgar", "debt ÷ market equity"),
        ],
        steps=[
            step("Leverage factor", f"1 + (1 − {tax_rate:.4f}) × {debt_to_equity:.4f}", factor),
            step("Relever", f"{beta_unlevered:.4f} × {factor:.4f}", beta_l),
        ],
        citation=spec.source_citation,
        caveats=["Assumes debt beta is zero (standard Hamada simplification)."],
    )
