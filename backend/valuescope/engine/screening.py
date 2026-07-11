"""Screening & margin of safety (PRD §6.2)."""
from __future__ import annotations

from ..registry import get_formula
from .trace import CalculationTrace, inp, step


def margin_of_safety(value: float, price: float, *, value_trace_id: str | None = None) -> CalculationTrace:
    """MoS = (V - P) / V — Graham, The Intelligent Investor ch. 20.

    When the estimated value is zero or negative (a DCF can honestly conclude
    the equity is worth nothing under its assumptions), the ratio flips sign
    and explodes — so MoS is pinned at −100%: the price sits entirely above
    value, with no cushion."""
    capped = value <= 0
    mos = -1.0 if capped else (value - price) / value
    spec = get_formula("margin_of_safety")
    return CalculationTrace(
        metric_id="margin_of_safety",
        formula_id="margin_of_safety",
        formula_version=spec.version,
        result=mos,
        unit="decimal",
        plain="How far below fair value the stock trades — your cushion against being wrong.",
        inputs=[
            inp("V", value, "US$/share", "formula", "intrinsic value", "", value_trace_id),
            inp("P", price, "US$/share", "yfinance", "last close"),
        ],
        steps=[step("Discount to value",
                    f"({value:,.2f} − {price:,.2f}) ÷ {value:,.2f}"
                    + (" → pinned at −100% (value ≤ 0)" if capped else ""), mos)],
        citation=spec.source_citation,
        caveats=["A large margin of safety is only meaningful if the value estimate is sound."]
        + (["The value estimate is zero or negative under current assumptions, "
            "so MoS is pinned at −100%."] if capped else []),
    )


def ncav(current_assets: float, total_liabilities: float, shares: float, price: float) -> CalculationTrace:
    """Net current asset value and the Graham 2/3 net-net test."""
    ncav_total = current_assets - total_liabilities
    per_share = ncav_total / shares if shares else 0.0
    buy_threshold = (2.0 / 3.0) * per_share
    is_net_net = price < buy_threshold and per_share > 0
    spec = get_formula("ncav")
    return CalculationTrace(
        metric_id="ncav",
        formula_id="ncav",
        formula_version=spec.version,
        result={"ncav_per_share": per_share, "buy_below": buy_threshold, "is_net_net": is_net_net},
        unit="US$/share",
        plain="The per-share liquidation value using only current assets; a classic deep-value floor.",
        inputs=[
            inp("Current assets", current_assets, "US$", "edgar", "balance sheet"),
            inp("Total liabilities", total_liabilities, "US$", "edgar", "balance sheet"),
            inp("Shares", shares, "count", "edgar", "shares outstanding"),
            inp("Price", price, "US$/share", "yfinance", "last close"),
        ],
        steps=[
            step("NCAV", f"{current_assets:,.0f} − {total_liabilities:,.0f}", ncav_total),
            step("Per share", f"{ncav_total:,.0f} ÷ {shares:,.0f}", per_share),
            step("Net-net buy zone", f"⅔ × {per_share:,.2f}", buy_threshold),
        ],
        citation=spec.source_citation,
        caveats=["Ignores off-balance-sheet liabilities and asset quality."],
    )


def magic_formula(ebit: float, enterprise_value: float, net_working_capital: float,
                  net_fixed_assets: float) -> CalculationTrace:
    """Earnings yield and return on capital — Greenblatt."""
    if enterprise_value == 0:
        raise ValueError("enterprise value must be non-zero")
    capital = net_working_capital + net_fixed_assets
    earnings_yield = ebit / enterprise_value
    roc = ebit / capital if capital else 0.0
    spec = get_formula("magic_formula")
    return CalculationTrace(
        metric_id="magic_formula",
        formula_id="magic_formula",
        formula_version=spec.version,
        result={"earnings_yield": earnings_yield, "return_on_capital": roc},
        unit="decimal",
        plain="Greenblatt's twin ranks: cheapness (earnings yield) and business quality (return on capital).",
        inputs=[
            inp("EBIT", ebit, "US$", "edgar", "operating income"),
            inp("Enterprise value", enterprise_value, "US$", "computed", "mktcap + debt − cash"),
            inp("Net working capital", net_working_capital, "US$", "edgar", "CA − CL (ex cash/debt)"),
            inp("Net fixed assets", net_fixed_assets, "US$", "edgar", "net PP&E"),
        ],
        steps=[
            step("Earnings yield", f"{ebit:,.0f} ÷ {enterprise_value:,.0f}", earnings_yield),
            step("Return on capital", f"{ebit:,.0f} ÷ ({net_working_capital:,.0f} + {net_fixed_assets:,.0f})", roc),
        ],
        citation=spec.source_citation,
        caveats=["Greenblatt ranks the whole universe on both metrics and sums the ranks."],
    )
