from valuescope.engine.wacc import wacc


def test_wacc_worked_example():
    # E=800, D=200, Re=10%, Rd=5%, t=25%
    # WACC = 0.8*0.10 + 0.2*0.05*0.75 = 0.08 + 0.0075 = 0.0875
    t = wacc(equity_value=800, debt_value=200, cost_of_equity=0.10,
             pretax_cost_of_debt=0.05, tax_rate=0.25)
    assert abs(t.result - 0.0875) < 1e-12
    assert t.formula_id == "wacc"


def test_wacc_all_equity_equals_cost_of_equity():
    t = wacc(equity_value=1000, debt_value=0, cost_of_equity=0.09,
             pretax_cost_of_debt=0.05, tax_rate=0.21)
    assert abs(t.result - 0.09) < 1e-12


def test_wacc_requires_positive_capital():
    import pytest
    with pytest.raises(ValueError):
        wacc(0, 0, 0.1, 0.05, 0.25)
