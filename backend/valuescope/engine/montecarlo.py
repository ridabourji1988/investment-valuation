"""Monte Carlo valuation (PRD §6.1).

Draw growth, target margin and WACC from distributions; revalue each draw;
report P(V>P) and the P10/P50/P90 value percentiles over >= 10 000 runs.

Source: Damodaran, "Probabilistic Approaches: Scenario Analysis, Decision Trees
and Simulations".
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

import numpy as np

from ..registry import get_formula
from .dcf import DCFAssumptions, value_firm
from .trace import CalculationTrace, inp, step


@dataclass
class MCConfig:
    runs: int = 10_000
    growth_sd: float = 0.02        # std dev around base growth (abs, decimal)
    margin_sd: float = 0.02        # std dev around target margin (abs, decimal)
    wacc_sd: float = 0.01          # std dev around WACC (abs, decimal)
    seed: int = 12345


def simulate(base: DCFAssumptions, price: float, cfg: MCConfig | None = None) -> CalculationTrace:
    cfg = cfg or MCConfig()
    rng = np.random.default_rng(cfg.seed)

    n = cfg.runs
    growth_draws = rng.normal(base.growth_initial, cfg.growth_sd, n)
    margin_draws = rng.normal(base.target_margin, cfg.margin_sd, n)
    wacc_draws = rng.normal(base.wacc_initial, cfg.wacc_sd, n)

    values = np.empty(n, dtype=float)
    valid = 0
    for i in range(n):
        a = copy.copy(base)
        a.growth_initial = float(growth_draws[i])
        a.target_margin = max(0.01, float(margin_draws[i]))
        # No clamp: only the (undrawn) terminal WACC must exceed terminal
        # growth. Clamping the drawn initial WACC truncates the distribution
        # and biases P(V>P) whenever the firm's WACC sits near/below the
        # terminal level; invalid draws are discarded by validate() below.
        a.wacc_initial = float(wacc_draws[i])
        try:
            values[i] = value_firm(a)["value_per_share"]
            valid += 1
        except ValueError:
            values[i] = np.nan

    vals = values[~np.isnan(values)]
    if vals.size == 0:
        raise ValueError("Monte Carlo produced no valid draws")

    p10, p50, p90 = (float(x) for x in np.percentile(vals, [10, 50, 90]))
    prob_above = float(np.mean(vals > price))

    spec = get_formula("monte_carlo_valuation")
    return CalculationTrace(
        metric_id="monte_carlo",
        formula_id="monte_carlo_valuation",
        formula_version=spec.version,
        result={"p10": p10, "p50": p50, "p90": p90, "prob_value_gt_price": prob_above,
                "mean": float(np.mean(vals)), "runs": int(vals.size)},
        unit="US$/share",
        plain="The range of fair values when the key assumptions are uncertain, and the odds the stock is undervalued.",
        inputs=[
            inp("Runs", int(cfg.runs), "count", "constant", "simulation draws"),
            inp("Growth σ", cfg.growth_sd, "decimal", "assumption", "growth uncertainty"),
            inp("Margin σ", cfg.margin_sd, "decimal", "assumption", "margin uncertainty"),
            inp("WACC σ", cfg.wacc_sd, "decimal", "assumption", "discount-rate uncertainty"),
            inp("Price", price, "US$/share", "yfinance", "last close"),
            inp("Seed", cfg.seed, "int", "constant", "reproducibility seed"),
        ],
        steps=[
            step("P10 (pessimistic)", "10th percentile of value", p10),
            step("P50 (median)", "50th percentile of value", p50),
            step("P90 (optimistic)", "90th percentile of value", p90),
            step("P(V > P)", f"share of draws with value > {price:,.2f}", prob_above),
        ],
        citation=spec.source_citation,
        caveats=[
            "Distributions are assumed Gaussian and independent; real drivers are correlated and skewed.",
            "Draws violating model constraints (e.g. margin ≤ 1%) are discarded, not clamped.",
        ],
    )
