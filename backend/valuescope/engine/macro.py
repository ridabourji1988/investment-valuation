"""Macro & cycle analytics (PRD §6.4).

Sahm recession rule, a transparent regime classifier, and rate-linked
revaluation helpers.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

from ..registry import get_formula
from .dcf import DCFAssumptions, value_firm
from .trace import CalculationTrace, inp, step


def _avg3(series, end_idx):
    return sum(series[end_idx - 2:end_idx + 1]) / 3.0


def sahm_rule(unemployment_monthly: list) -> CalculationTrace:
    """3-month average unemployment minus its trailing-12-month minimum.

    Trigger at >= 0.50pp. Requires >= 15 monthly observations (12-month lookback
    of the 3-month average). Sahm (2019); FRED SAHMREALTIME.
    """
    n = len(unemployment_monthly)
    if n < 15:
        raise ValueError("need at least 15 monthly unemployment observations")
    current_avg3 = _avg3(unemployment_monthly, n - 1)
    # trailing 12 months of the 3-month average (including current)
    avg3_series = [_avg3(unemployment_monthly, i) for i in range(n - 12, n)]
    trailing_min = min(avg3_series)
    value = current_avg3 - trailing_min
    triggered = value >= 0.50
    spec = get_formula("sahm_rule")
    return CalculationTrace(
        metric_id="sahm",
        formula_id="sahm_rule",
        formula_version=spec.version,
        result={"value": value, "triggered": triggered, "current_avg3": current_avg3,
                "trailing_min": trailing_min},
        unit="pp",
        plain="An early recession signal: recent unemployment vs. its recent low.",
        inputs=[inp("Unemployment (monthly)", unemployment_monthly[-15:], "%", "fred", "UNRATE")],
        steps=[
            step("3-month average (now)", "mean of last 3 months", current_avg3),
            step("Trailing 12-month min of 3-mo avg", "min", trailing_min),
            step("Sahm value", f"{current_avg3:.2f} − {trailing_min:.2f}", value),
            step("Triggered?", "value ≥ 0.50", triggered),
        ],
        citation=spec.source_citation,
        caveats=["A trigger indicates the early stage of a recession, not its depth."],
    )


@dataclass
class RegimeInputs:
    t10y3m: float       # 10Y minus 3M spread (decimal, e.g. -0.005 = -50bp)
    pmi: float          # ISM manufacturing PMI
    hy_oas: float       # high-yield OAS (decimal, e.g. 0.045 = 4.5%)
    sahm_triggered: bool


def classify_regime(x: RegimeInputs) -> CalculationTrace:
    """Rule-table regime label over the four macro signals."""
    inverted = x.t10y3m < 0
    pmi_contraction = x.pmi < 50
    credit_stress = x.hy_oas > 0.06

    stress_count = sum([inverted, pmi_contraction, credit_stress, x.sahm_triggered])
    if x.sahm_triggered or stress_count >= 3:
        label = "Contraction / Late-cycle stress"
    elif stress_count == 2:
        label = "Slowdown"
    elif inverted or pmi_contraction or credit_stress:
        label = "Late cycle"
    else:
        label = "Expansion"

    implications = {
        "Expansion": "Full position sizing acceptable; favour quality compounders.",
        "Late cycle": "Trim cyclicals; keep dry powder; prefer defensives and strong balance sheets.",
        "Slowdown": "Reduce sizing; emphasise margin of safety and low leverage.",
        "Contraction / Late-cycle stress": "Smallest sizing; deep value & net-nets; wait for capitulation.",
    }[label]

    spec = get_formula("regime_classifier")
    return CalculationTrace(
        metric_id="regime",
        formula_id="regime_classifier",
        formula_version=spec.version,
        result={"label": label, "implication": implications, "stress_count": stress_count,
                "signals": {"yield_curve_inverted": inverted, "pmi_contraction": pmi_contraction,
                            "credit_stress": credit_stress, "sahm_triggered": x.sahm_triggered}},
        unit="label",
        plain="Where we are in the market cycle, from four transparent signals.",
        inputs=[
            inp("10Y − 3M", x.t10y3m, "decimal", "fred", "T10Y3M"),
            inp("ISM PMI", x.pmi, "index", "ism", "manufacturing PMI"),
            inp("HY OAS", x.hy_oas, "decimal", "fred", "BAMLH0A0HYM2"),
            inp("Sahm triggered", x.sahm_triggered, "bool", "formula", "sahm_rule"),
        ],
        steps=[
            step("Yield curve inverted", "10Y−3M < 0", inverted),
            step("PMI contraction", "PMI < 50", pmi_contraction),
            step("Credit stress", "HY OAS > 6%", credit_stress),
            step("Stress count", "sum of triggered signals", stress_count),
            step("Regime", "rule table", label),
        ],
        citation=spec.source_citation,
        caveats=["Macro is context only — it adjusts sizing/risk labels, never flips a verdict (PRD P4)."],
    )


def rate_sensitivity(base: DCFAssumptions, *, bp: int = 50) -> CalculationTrace:
    """Re-run the DCF at risk-free ±bp (flows through to WACC one-for-one)."""
    d = bp / 10000.0
    base_v = value_firm(base)["value_per_share"]

    up = copy.copy(base)
    up.wacc_initial += d
    up.wacc_terminal += d
    up.risk_free += d
    up_v = value_firm(up)["value_per_share"]

    down = copy.copy(base)
    down.wacc_initial -= d
    down.wacc_terminal -= d
    down.risk_free -= d
    # keep g <= Rf constraint valid
    down.growth_terminal = min(down.growth_terminal, down.risk_free)
    down_v = value_firm(down)["value_per_share"]

    spec = get_formula("intrinsic_value_fcff")
    return CalculationTrace(
        metric_id="rate_sensitivity",
        formula_id="intrinsic_value_fcff",
        formula_version=spec.version,
        result={"base": base_v, f"minus_{bp}bp": down_v, f"plus_{bp}bp": up_v},
        unit="US$/share",
        plain=f"How fair value moves if the 10-year yield shifts ±{bp} basis points.",
        inputs=[inp("10Y move", d, "decimal", "fred", f"±{bp}bp on DGS10")],
        steps=[
            step(f"Rf −{bp}bp", "lower discount rate", down_v),
            step("Base", "current rates", base_v),
            step(f"Rf +{bp}bp", "higher discount rate", up_v),
        ],
        citation=spec.source_citation,
        caveats=["Holds the equity risk premium fixed; in practice ERP and rates co-move."],
    )
