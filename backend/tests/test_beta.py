from valuescope.engine.beta import relever_beta, unlever_beta


def test_relever_beta_worked_example():
    # Hamada: beta_L = beta_U*(1+(1-t)*D/E).
    # beta_U=0.90, t=0.25, D/E=0.50 -> 0.90*(1+0.75*0.5)=0.90*1.375=1.2375
    t = relever_beta(beta_unlevered=0.90, tax_rate=0.25, debt_to_equity=0.50)
    assert abs(t.result - 1.2375) < 1e-12
    assert t.formula_id == "bottom_up_beta"


def test_unlever_relever_roundtrip():
    beta_l = 1.30
    bu = unlever_beta(beta_l, tax_rate=0.21, debt_to_equity=0.4)
    back = relever_beta(bu, tax_rate=0.21, debt_to_equity=0.4).result
    assert abs(back - beta_l) < 1e-12


def test_no_debt_leaves_beta_unchanged():
    t = relever_beta(1.1, tax_rate=0.25, debt_to_equity=0.0)
    assert abs(t.result - 1.1) < 1e-12
