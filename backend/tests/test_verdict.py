from valuescope.engine.verdict import (
    VerdictInputs, decide, ValueTrapInputs, value_trap_check,
)


def test_buy_verdict():
    r = decide(VerdictInputs(mos=0.30, quality=72, prob_value_gt_price=0.80,
                             trap_flags=1, idea_category="compounder",
                             mc_confidence=0.8)).result
    assert r["action"] == "BUY"
    assert r["horizon"] == "5+ years"
    assert r["confidence"] == "High"
    assert "%" in r["sizing"]


def test_sell_verdict_overvalued():
    # MoS <= -10% means P >= 1.1*V -> SELL
    r = decide(VerdictInputs(mos=-0.15, quality=80, prob_value_gt_price=0.2,
                             trap_flags=0)).result
    assert r["action"] == "SELL"


def test_sell_verdict_trap_flags():
    r = decide(VerdictInputs(mos=0.30, quality=80, prob_value_gt_price=0.9,
                             trap_flags=5)).result
    assert r["action"] == "SELL"


def test_hold_verdict():
    r = decide(VerdictInputs(mos=0.10, quality=65, prob_value_gt_price=0.6,
                             trap_flags=1)).result
    assert r["action"] == "HOLD"


def test_buy_blocked_by_low_quality():
    r = decide(VerdictInputs(mos=0.40, quality=50, prob_value_gt_price=0.9,
                             trap_flags=0)).result
    assert r["action"] == "HOLD"  # quality < 60 blocks BUY, but no SELL trigger


def test_macro_only_reduces_size():
    full = decide(VerdictInputs(mos=0.30, quality=80, prob_value_gt_price=0.8,
                                trap_flags=0), regime_reduce=1.0).result
    reduced = decide(VerdictInputs(mos=0.30, quality=80, prob_value_gt_price=0.8,
                                   trap_flags=0), regime_reduce=0.5).result
    # Same verdict, smaller suggested size.
    assert full["action"] == reduced["action"] == "BUY"
    assert full["sizing"] != reduced["sizing"]


def test_value_trap_count():
    r = value_trap_check(ValueTrapInputs(
        revenue_declining=True, margin_deteriorating=True, rising_leverage=True,
        weak_cash_conversion=False, falling_roic=True, high_beneish=False,
        low_piotroski=False, negative_fcf=False)).result
    assert r["flags"] == 4
