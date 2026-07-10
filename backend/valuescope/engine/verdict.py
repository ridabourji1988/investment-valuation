"""Verdict rules & value-trap check (PRD §6.3, §9).

The verdict itself is rule-based and versioned ("ValueScope house rule v1").
The AI layer only explains it (PRD P2).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..registry import get_formula
from .trace import CalculationTrace, inp, step


# --------------------------------------------------------------------------- #
# Value-trap check — 8 signals (PRD §3.2)
# --------------------------------------------------------------------------- #
@dataclass
class ValueTrapInputs:
    revenue_declining: bool          # multi-year revenue decline
    margin_deteriorating: bool       # operating margin trend down
    rising_leverage: bool            # net debt/EBITDA increasing
    weak_cash_conversion: bool       # CFO < net income persistently
    falling_roic: bool               # ROIC trend down / below WACC
    high_beneish: bool               # M-score above threshold
    low_piotroski: bool              # F-score <= 3
    negative_fcf: bool               # negative free cash flow


def value_trap_check(x: ValueTrapInputs) -> CalculationTrace:
    signals = {
        "Revenue in decline": x.revenue_declining,
        "Margins deteriorating": x.margin_deteriorating,
        "Leverage rising": x.rising_leverage,
        "Weak cash conversion": x.weak_cash_conversion,
        "ROIC falling / below WACC": x.falling_roic,
        "Earnings-manipulation flag (Beneish)": x.high_beneish,
        "Low Piotroski F-Score": x.low_piotroski,
        "Negative free cash flow": x.negative_fcf,
    }
    flags = sum(1 for v in signals.values() if v)
    spec = get_formula("verdict_rules")
    return CalculationTrace(
        metric_id="value_trap",
        formula_id="verdict_rules",
        formula_version=spec.version,
        result={"flags": flags, "signals": {k: bool(v) for k, v in signals.items()}},
        unit="/8",
        plain="How many classic 'cheap for a reason' warning signs are present.",
        inputs=[inp("Fundamental trends", "8 checks", "", "computed", "engine")],
        steps=[step(k, "flag", v) for k, v in signals.items()]
              + [step("Total flags", "count", flags)],
        citation=spec.source_citation,
        caveats=["4+ flags materially raise the odds the discount is deserved."],
    )


# --------------------------------------------------------------------------- #
# Verdict — BUY / HOLD / SELL (PRD §9)
# --------------------------------------------------------------------------- #
IDEA_HORIZONS = {
    "mean_reversion": "1-2 years",
    "margin_recovery": "2-4 years",
    "turnaround": "2-4 years",
    "cyclical": "1-2 years",
    "compounder": "5+ years",
    "stalwart": "3-5 years",
    "asset_play": "2-4 years",
}


@dataclass
class VerdictInputs:
    mos: float               # margin of safety (decimal)
    quality: float           # quality composite 0-100
    prob_value_gt_price: float  # P(V>P) 0-1
    trap_flags: int          # value-trap flag count 0-8
    thesis_intact: bool = True
    sell_trigger_fired: bool = False
    quality_deteriorating: bool = False
    idea_category: str = "compounder"
    mc_confidence: float = 0.5  # verdict stability across Monte Carlo draws (0-1)


@dataclass
class Verdict:
    action: str
    horizon: str
    confidence: str
    sizing: str
    reasons: list = field(default_factory=list)


def _sizing_line(action: str, quality: float, regime_reduce: float = 1.0) -> str:
    """10k US$ portfolio sizing (Graham diversification; macro may only reduce)."""
    if action != "BUY":
        return "No new capital suggested."
    base_pct = 0.15 if quality >= 75 else 0.10
    pct = base_pct * max(0.4, min(1.0, regime_reduce))
    dollars = 10_000 * pct
    return f"≈ {pct*100:.0f}% of a 10 000 US$ portfolio (~{dollars:,.0f} US$); hold 5-10 positions."


def decide(x: VerdictInputs, *, regime_reduce: float = 1.0) -> CalculationTrace:
    reasons = []

    is_sell = (
        x.mos <= -0.10 or               # P >= V * 1.1  <=>  MoS <= -10%
        x.sell_trigger_fired or
        x.quality_deteriorating or
        x.trap_flags >= 4
    )
    is_buy = (
        x.mos >= 0.25 and
        x.quality >= 60 and
        x.prob_value_gt_price >= 0.70 and
        x.trap_flags <= 2 and
        x.thesis_intact
    )

    if is_sell:
        action = "SELL"
        if x.mos <= -0.10:
            reasons.append("Price ≥ 110% of fair value (negative margin of safety).")
        if x.sell_trigger_fired:
            reasons.append("A pre-defined sell trigger fired.")
        if x.quality_deteriorating:
            reasons.append("Business quality is deteriorating.")
        if x.trap_flags >= 4:
            reasons.append(f"{x.trap_flags} value-trap flags (≥4).")
    elif is_buy:
        action = "BUY"
        reasons.append(f"Margin of safety {x.mos:.0%} ≥ 25%.")
        reasons.append(f"Quality {x.quality:.0f} ≥ 60.")
        reasons.append(f"P(value>price) {x.prob_value_gt_price:.0%} ≥ 70%.")
        reasons.append(f"Value-trap flags {x.trap_flags} ≤ 2.")
    else:
        action = "HOLD"
        reasons.append("Undervaluation is modest or conviction is insufficient for a BUY, "
                       "but no SELL trigger is met.")

    # Confidence from Monte Carlo verdict stability.
    if x.mc_confidence >= 0.75:
        confidence = "High"
    elif x.mc_confidence >= 0.5:
        confidence = "Medium"
    else:
        confidence = "Low"

    horizon = IDEA_HORIZONS.get(x.idea_category, "3-5 years")
    sizing = _sizing_line(action, x.quality, regime_reduce)

    spec = get_formula("verdict_rules")
    return CalculationTrace(
        metric_id="verdict",
        formula_id="verdict_rules",
        formula_version=spec.version,
        result={"action": action, "horizon": horizon, "confidence": confidence,
                "sizing": sizing, "reasons": reasons},
        unit="verdict",
        plain="The rule-based Buy / Hold / Sell decision, with the exact rules that fired.",
        inputs=[
            inp("Margin of safety", x.mos, "decimal", "formula", "margin_of_safety"),
            inp("Quality", x.quality, "/100", "formula", "quality_composite"),
            inp("P(V>P)", x.prob_value_gt_price, "decimal", "formula", "monte_carlo_valuation"),
            inp("Trap flags", x.trap_flags, "/8", "formula", "value_trap_check"),
            inp("Idea category", x.idea_category, "label", "assumption", "Lynch category"),
        ],
        steps=[
            step("SELL test", "P≥1.1V ∨ trigger ∨ quality↓ ∨ flags≥4", is_sell),
            step("BUY test", "MoS≥25% ∧ Q≥60 ∧ P(V>P)≥70% ∧ flags≤2 ∧ thesis intact", is_buy),
            step("Verdict", "rule outcome", action),
            step("Horizon", "Lynch idea category", horizon),
            step("Confidence", "Monte Carlo stability", confidence),
        ],
        citation=spec.source_citation,
        caveats=["Macro regime may only reduce suggested size, never flip the verdict (PRD P4)."],
    )
