import pytest

from valuescope.engine.screening import margin_of_safety, ncav, magic_formula


def test_margin_of_safety():
    # MoS = (V-P)/V. V=100, P=75 -> 0.25
    assert abs(margin_of_safety(100, 75).result - 0.25) < 1e-12
    # Overvalued -> negative
    assert margin_of_safety(100, 120).result < 0
    # Value <= 0: a DCF can honestly conclude the equity is worthless —
    # MoS pins at -100% instead of exploding through the sign flip.
    assert margin_of_safety(0, 10).result == -1.0
    assert margin_of_safety(-1.75, 559.9).result == -1.0


def test_ncav():
    # NCAV = CA - TL. CA=500, TL=200 -> 300 ; /100 shares -> 3.0/share
    # buy zone = 2/3*3 = 2.0 ; price 1.5 < 2.0 -> net-net
    r = ncav(current_assets=500, total_liabilities=200, shares=100, price=1.5).result
    assert abs(r["ncav_per_share"] - 3.0) < 1e-12
    assert abs(r["buy_below"] - 2.0) < 1e-12
    assert r["is_net_net"] is True

    r2 = ncav(500, 200, 100, price=2.5).result
    assert r2["is_net_net"] is False


def test_magic_formula():
    # EY = EBIT/EV = 200/1000 = 0.20
    # ROC = EBIT/(NWC+NFA) = 200/(300+500) = 0.25
    r = magic_formula(ebit=200, enterprise_value=1000,
                      net_working_capital=300, net_fixed_assets=500).result
    assert abs(r["earnings_yield"] - 0.20) < 1e-12
    assert abs(r["return_on_capital"] - 0.25) < 1e-12
