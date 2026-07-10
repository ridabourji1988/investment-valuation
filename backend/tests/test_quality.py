from valuescope.engine.quality import (
    PiotroskiInputs, piotroski_f_score,
    AltmanInputs, altman_z_score,
    BeneishInputs, beneish_m_score,
    QualityInputs, quality_composite,
)


def test_piotroski_full_marks():
    x = PiotroskiInputs(
        net_income=100, cfo=150, total_assets=1000, total_assets_prior=900,
        roa_prior=0.05, long_term_debt=200, long_term_debt_prior=250,
        current_assets=600, current_liabilities=300,
        current_assets_prior=500, current_liabilities_prior=300,
        shares=100, shares_prior=100,
        gross_margin=0.40, gross_margin_prior=0.35,
        asset_turnover=0.9, asset_turnover_prior=0.8,
    )
    assert piotroski_f_score(x).result["score"] == 9


def test_piotroski_weak_firm():
    x = PiotroskiInputs(
        net_income=-10, cfo=-20, total_assets=1000, total_assets_prior=900,
        roa_prior=0.05, long_term_debt=300, long_term_debt_prior=200,
        current_assets=300, current_liabilities=400,
        current_assets_prior=500, current_liabilities_prior=300,
        shares=110, shares_prior=100,
        gross_margin=0.30, gross_margin_prior=0.35,
        asset_turnover=0.7, asset_turnover_prior=0.8,
    )
    assert piotroski_f_score(x).result["score"] == 0


def test_altman_z_worked_example():
    # A=0.2,B=0.3,C=0.1,D=1.5,E=1.8
    # Z = 1.2*.2+1.4*.3+3.3*.1+0.6*1.5+1.0*1.8 = .24+.42+.33+.9+1.8 = 3.69
    x = AltmanInputs(working_capital=200, retained_earnings=300, ebit=100,
                     market_value_equity=1500, total_liabilities=1000,
                     sales=1800, total_assets=1000)
    r = altman_z_score(x).result
    assert abs(r["z"] - 3.69) < 1e-9
    assert r["zone"] == "safe"


def test_altman_distress_zone():
    x = AltmanInputs(working_capital=-50, retained_earnings=-100, ebit=-20,
                     market_value_equity=50, total_liabilities=800,
                     sales=300, total_assets=1000)
    assert altman_z_score(x).result["zone"] == "distress"


def _clean_beneish():
    return BeneishInputs(
        receivables=100, receivables_prior=100,
        sales=1000, sales_prior=1000,
        cogs=600, cogs_prior=600,
        current_assets=400, current_assets_prior=400,
        net_ppe=300, net_ppe_prior=300,
        total_assets=1000, total_assets_prior=1000,
        depreciation=50, depreciation_prior=50,
        sga=100, sga_prior=100,
        net_income=120, cfo=120,
        current_liabilities=150, current_liabilities_prior=150,
        long_term_debt=200, long_term_debt_prior=200,
    )


def test_beneish_m_worked_example():
    # All indices = 1 and TATA = 0 -> M = -4.84 + sum(coeffs) = -2.48
    r = beneish_m_score(_clean_beneish()).result
    assert abs(r["m"] - (-2.48)) < 1e-9
    assert r["likely_manipulator"] is False


def test_beneish_flags_aggressive_accruals():
    x = _clean_beneish()
    x.net_income = 400   # income far above cash flow -> large positive TATA
    x.cfo = 50
    r = beneish_m_score(x).result
    assert r["m"] > -1.78
    assert r["likely_manipulator"] is True


def test_quality_composite_bounds():
    good = quality_composite(QualityInputs(
        roic=0.20, wacc=0.08, revenue_growth_history=[0.10, 0.12, 0.11, 0.09],
        net_debt=0, ebitda=100, cfo=120, net_income=100)).result
    weak = quality_composite(QualityInputs(
        roic=0.03, wacc=0.10, revenue_growth_history=[-0.10, 0.20, -0.05, 0.15],
        net_debt=500, ebitda=100, cfo=20, net_income=100)).result
    assert 0 <= weak["total"] <= good["total"] <= 100
    assert good["total"] > 70
    assert weak["total"] < 40
