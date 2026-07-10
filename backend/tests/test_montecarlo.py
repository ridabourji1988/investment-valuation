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
