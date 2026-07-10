from valuescope.engine.capm import cost_of_equity


def test_capm_worked_example():
    # Damodaran CAPM: Re = Rf + beta*ERP.  Rf=4%, beta=1.20, ERP=5% -> 10%.
    t = cost_of_equity(rf=0.04, beta=1.20, erp=0.05)
    assert t.result == 0.04 + 1.20 * 0.05
    assert abs(t.result - 0.10) < 1e-12
    assert t.formula_id == "capm_cost_of_equity"
    assert t.citation  # must carry a citation


def test_capm_zero_beta_is_riskfree():
    t = cost_of_equity(rf=0.045, beta=0.0, erp=0.055)
    assert abs(t.result - 0.045) < 1e-12
