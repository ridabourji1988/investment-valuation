from valuescope.engine.dcf import value_firm
from valuescope.engine.montecarlo import MCConfig, simulate
from tests.test_dcf import base_assumptions


def test_percentile_ordering():
    a = base_assumptions()
    t = simulate(a, price=20.0, cfg=MCConfig(runs=3000, seed=7))
    r = t.result
    assert r["p10"] <= r["p50"] <= r["p90"]
    assert r["runs"] > 0


def test_prob_above_price():
    a = base_assumptions()
    fair = simulate(a, price=1e9, cfg=MCConfig(runs=2000, seed=1)).result
    # An impossibly high price -> almost never undervalued.
    assert fair["prob_value_gt_price"] < 0.01

    cheap = simulate(a, price=-1e9, cfg=MCConfig(runs=2000, seed=1)).result
    # A negative price -> always "undervalued".
    assert cheap["prob_value_gt_price"] > 0.99


def test_reproducible_with_seed():
    a = base_assumptions()
    r1 = simulate(a, 20.0, MCConfig(runs=1500, seed=42)).result
    r2 = simulate(a, 20.0, MCConfig(runs=1500, seed=42)).result
    assert r1["p50"] == r2["p50"]


def test_median_unbiased_when_wacc_below_terminal():
    """Regression: draws must not be clamped. With symmetric input
    distributions the median value must sit near the deterministic base case
    even when the firm's WACC is below the terminal WACC (previously a clamp
    truncated ~98% of draws for such firms and shifted P(V>P))."""
    a = base_assumptions(wacc_initial=0.065, wacc_terminal=0.08)
    base_value = value_firm(a)["value_per_share"]
    r = simulate(a, price=base_value, cfg=MCConfig(runs=8000, seed=3)).result
    assert abs(r["p50"] - base_value) / base_value < 0.05
    # Price at the base value -> roughly a coin flip, not a skewed verdict.
    assert 0.35 < r["prob_value_gt_price"] < 0.65
