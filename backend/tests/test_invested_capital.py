"""Invested capital must exclude acquisition goodwill (Damodaran).

Regression for the AMD case: ~$45B of Xilinx goodwill in book equity made
sales-to-capital 0.62 (=$1.61 of "required" reinvestment per $1 of new
revenue), producing ten years of phantom negative FCFF and a NEGATIVE fair
value for a profitable megacap.
"""
import pytest

from valuescope.data.live import operating_invested_capital


def test_goodwill_is_excluded():
    ic = operating_invested_capital(
        58_000e6, 3_000e6, 10_000e6, 45_000e6,
        market_cap=900_000e6, revenue=34_600e6)
    assert ic == pytest.approx(6_000e6)


def test_no_goodwill_matches_plain_book_capital():
    ic = operating_invested_capital(
        50_000e6, 10_000e6, 5_000e6, 0.0,
        market_cap=100_000e6, revenue=40_000e6)
    assert ic == pytest.approx(55_000e6)


def test_negative_ex_goodwill_falls_back_to_neutral_base():
    # All-goodwill balance sheet: ex-goodwill capital would be negative.
    ic = operating_invested_capital(
        20_000e6, 0.0, 5_000e6, 30_000e6,
        market_cap=50_000e6, revenue=12_000e6)
    assert ic == pytest.approx(6_000e6)  # revenue / 2


def test_missing_equity_uses_half_market_cap():
    ic = operating_invested_capital(
        None, 2_000e6, 1_000e6, 0.0,
        market_cap=40_000e6, revenue=10_000e6)
    assert ic == pytest.approx(21_000e6)
