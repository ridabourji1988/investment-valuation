import pytest

from valuescope.engine.macro import (
    sahm_rule, classify_regime, RegimeInputs, rate_sensitivity,
)
from valuescope.engine.dcf import value_firm
from tests.test_dcf import base_assumptions


def test_sahm_rule_trigger():
    # Flat 3.5% for a year, then a jump to 4.2% for last 3 months.
    series = [3.5] * 12 + [4.2, 4.2, 4.2]
    r = sahm_rule(series).result
    # current 3-mo avg 4.2 ; trailing min of the 3-mo avg ~3.5 -> ~0.7 >= 0.5
    assert r["triggered"] is True
    assert r["value"] >= 0.5


def test_sahm_rule_calm():
    series = [3.5 + 0.01 * i for i in range(15)]  # gently rising, small moves
    r = sahm_rule(series).result
    assert r["triggered"] is False


def test_sahm_requires_enough_history():
    with pytest.raises(ValueError):
        sahm_rule([3.5] * 10)


def test_regime_expansion():
    r = classify_regime(RegimeInputs(t10y3m=0.015, pmi=54, hy_oas=0.035,
                                     sahm_triggered=False)).result
    assert r["label"] == "Expansion"


def test_regime_stress():
    r = classify_regime(RegimeInputs(t10y3m=-0.005, pmi=47, hy_oas=0.07,
                                     sahm_triggered=True)).result
    assert r["label"].startswith("Contraction")


def test_regime_late_cycle_single_signal():
    r = classify_regime(RegimeInputs(t10y3m=-0.002, pmi=52, hy_oas=0.04,
                                     sahm_triggered=False)).result
    assert r["label"] == "Late cycle"


def test_rate_sensitivity_monotonic():
    a = base_assumptions()
    r = rate_sensitivity(a, bp=50).result
    # Higher rates -> lower value; lower rates -> higher value.
    assert r["plus_50bp"] < r["base"] < r["minus_50bp"]
