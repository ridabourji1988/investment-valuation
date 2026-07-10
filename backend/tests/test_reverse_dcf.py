from valuescope.engine.dcf import DCFAssumptions, value_firm
from valuescope.engine.reverse_dcf import implied_growth
from tests.test_dcf import base_assumptions


def test_reverse_dcf_roundtrip():
    """Pick a growth, compute the price it implies, then confirm the reverse DCF
    recovers that same growth."""
    a = base_assumptions(growth_initial=0.11)
    price = value_firm(a)["value_per_share"]

    # Solve starting from a base whose growth differs from the true 11%.
    solver_base = base_assumptions(growth_initial=0.05)
    t = implied_growth(solver_base, price)
    assert abs(t.result - 0.11) < 1e-3
    assert t.formula_id == "reverse_dcf"


def test_reverse_dcf_higher_price_implies_higher_growth():
    a = base_assumptions()
    v = value_firm(a)["value_per_share"]
    g_cheap = implied_growth(a, v * 0.8).result
    g_rich = implied_growth(a, v * 1.2).result
    assert g_rich > g_cheap
