"""Bundled demo dataset.

Lets the whole app run end-to-end (feed -> Asset 360 -> Show Calculation ->
macro) without any network. Figures are illustrative and internally consistent,
clearly labelled as demo sources. When live data is enabled and reachable the
provider prefers EDGAR/yfinance/FRED and falls back to this only on failure.
"""
from __future__ import annotations

import math

from ..engine.analyze import CompanyInputs
from ..engine.quality import PiotroskiInputs, AltmanInputs, BeneishInputs, QualityInputs
from ..engine.verdict import ValueTrapInputs

# Global macro assumptions used as CAPM inputs across the demo universe.
RISK_FREE = 0.0425      # 10Y Treasury (FRED DGS10)
ERP = 0.0450            # Damodaran implied equity risk premium
DEMO_ASOF = "2026-06-30"


def _synth(
    *, ticker, name, exchange, sector, price, shares, revenue, ebit_margin,
    target_margin, growth, terminal_growth, net_debt, debt_to_equity, beta_u,
    sales_to_capital, idea_category, tax_rate=0.24, wacc_terminal=0.08,
    roic_stable=0.12, healthy=True, total_assets=None, growth_hist=None,
):
    """Build a fully-populated CompanyInputs (incl. forensic sub-inputs) from a
    compact set of summary financials, keeping every derived statement item
    internally consistent."""
    ebit = revenue * ebit_margin
    total_assets = total_assets or revenue * 1.4
    ta_prior = total_assets / (1 + growth)
    net_income = ebit * (1 - tax_rate) - net_debt * 0.05 * (1 - tax_rate)
    cfo = net_income * (1.15 if healthy else 0.75)
    cogs = revenue * (1 - 0.42)                 # ~42% gross margin
    gross_margin = (revenue - cogs) / revenue
    current_assets = total_assets * 0.35
    current_liabilities = total_assets * 0.18
    net_ppe = total_assets * 0.30
    retained_earnings = total_assets * (0.35 if healthy else 0.05)
    total_liabilities = total_assets * (0.45 if healthy else 0.72)
    working_capital = current_assets - current_liabilities
    market_cap = price * shares

    piotroski = PiotroskiInputs(
        net_income=net_income, cfo=cfo, total_assets=total_assets,
        total_assets_prior=ta_prior, roa_prior=(net_income / ta_prior) * (0.9 if healthy else 1.2),
        long_term_debt=net_debt * 0.9, long_term_debt_prior=net_debt * (0.85 if healthy else 1.0),
        current_assets=current_assets, current_liabilities=current_liabilities,
        current_assets_prior=current_assets / (1 + growth),
        current_liabilities_prior=current_liabilities / (1 + (growth if healthy else growth * 1.5)),
        shares=shares, shares_prior=shares * (0.99 if healthy else 1.03),
        gross_margin=gross_margin, gross_margin_prior=gross_margin - (0.01 if healthy else -0.02),
        asset_turnover=revenue / total_assets,
        asset_turnover_prior=(revenue / (1 + growth)) / ta_prior - (0.0 if healthy else 0.05),
    )
    altman = AltmanInputs(
        working_capital=working_capital, retained_earnings=retained_earnings, ebit=ebit,
        market_value_equity=market_cap, total_liabilities=total_liabilities,
        sales=revenue, total_assets=total_assets,
    )
    beneish = BeneishInputs(
        receivables=revenue * 0.12, receivables_prior=revenue * 0.12 / (1 + growth) * (1.0 if healthy else 1.25),
        sales=revenue, sales_prior=revenue / (1 + growth),
        cogs=cogs, cogs_prior=cogs / (1 + growth),
        current_assets=current_assets, current_assets_prior=current_assets / (1 + growth),
        net_ppe=net_ppe, net_ppe_prior=net_ppe / (1 + growth),
        total_assets=total_assets, total_assets_prior=ta_prior,
        depreciation=net_ppe * 0.10, depreciation_prior=net_ppe / (1 + growth) * 0.10,
        sga=revenue * 0.15, sga_prior=revenue / (1 + growth) * 0.15,
        net_income=net_income if healthy else net_income * 1.6,   # unhealthy: income > cash
        cfo=cfo,
        current_liabilities=current_liabilities, current_liabilities_prior=current_liabilities / (1 + growth),
        long_term_debt=net_debt * 0.9, long_term_debt_prior=net_debt * 0.85,
    )
    quality = QualityInputs(
        roic=roic_stable, wacc=0.0,  # wacc injected by analyze()
        revenue_growth_history=growth_hist or ([growth, growth * 0.95, growth * 1.05, growth * 0.9]
                                               if healthy else [growth, -0.03, 0.12, -0.06]),
        net_debt=net_debt, ebitda=ebit * 1.2, cfo=cfo, net_income=net_income,
    )
    trap = ValueTrapInputs(
        revenue_declining=not healthy and growth < 0.02,
        margin_deteriorating=not healthy,
        rising_leverage=not healthy,
        weak_cash_conversion=cfo < net_income,
        falling_roic=not healthy,
        high_beneish=False,   # set by analyze consumers if needed
        low_piotroski=False,
        negative_fcf=cfo < 0,
    )
    return CompanyInputs(
        ticker=ticker, name=name, exchange=exchange, sector=sector, price=price,
        shares=shares, net_debt=net_debt, idea_category=idea_category,
        data_quality="high", beta_unlevered=beta_u, tax_rate=tax_rate,
        debt_to_equity=debt_to_equity, risk_free=RISK_FREE, erp=ERP,
        pretax_cost_of_debt=0.052, revenue_base=revenue, ebit_margin_base=ebit_margin,
        target_margin=target_margin, growth_initial=growth, growth_terminal=terminal_growth,
        sales_to_capital=sales_to_capital, wacc_terminal=wacc_terminal, roic_stable=roic_stable,
        quality=quality, piotroski=piotroski, altman=altman, beneish=beneish, trap=trap,
        ncav_current_assets=current_assets, ncav_total_liabilities=total_liabilities,
        magic_nwc=working_capital, magic_nfa=net_ppe,
        sources={"fundamentals": "ValueScope demo dataset", "prices": "ValueScope demo dataset"},
        asof=DEMO_ASOF,
    )


# --------------------------------------------------------------------------- #
# Demo universe — a spread of sectors, quality levels and verdicts.
# --------------------------------------------------------------------------- #
_UNIVERSE_SPECS = [
    dict(ticker="NVSC", name="NovaScale Compute", exchange="NASDAQ", sector="Technology",
         price=88.0, shares=1.8e9, revenue=42e9, ebit_margin=0.28, target_margin=0.32,
         growth=0.16, terminal_growth=0.025, net_debt=-8e9, debt_to_equity=0.10, beta_u=1.15,
         sales_to_capital=2.6, idea_category="compounder", roic_stable=0.22),
    dict(ticker="ORCH", name="Orchard Foods", exchange="NYSE", sector="Consumer Staples",
         price=54.0, shares=900e6, revenue=28e9, ebit_margin=0.14, target_margin=0.15,
         growth=0.04, terminal_growth=0.02, net_debt=6e9, debt_to_equity=0.45, beta_u=0.55,
         sales_to_capital=1.8, idea_category="stalwart", roic_stable=0.13),
    dict(ticker="RAIL", name="Ironline Rail", exchange="NYSE", sector="Industrials",
         price=132.0, shares=420e6, revenue=19e9, ebit_margin=0.34, target_margin=0.36,
         growth=0.05, terminal_growth=0.02, net_debt=14e9, debt_to_equity=0.60, beta_u=0.95,
         sales_to_capital=0.9, idea_category="cyclical", roic_stable=0.14),
    dict(ticker="HELX", name="Helix Bio", exchange="NASDAQ", sector="Health Care",
         price=41.0, shares=310e6, revenue=6.2e9, ebit_margin=0.22, target_margin=0.28,
         growth=0.11, terminal_growth=0.025, net_debt=-1.2e9, debt_to_equity=0.08, beta_u=1.05,
         sales_to_capital=1.9, idea_category="compounder", roic_stable=0.18),
    dict(ticker="DGWL", name="Dogwood Retail", exchange="NYSE", sector="Consumer Discretionary",
         price=17.5, shares=260e6, revenue=9.4e9, ebit_margin=0.05, target_margin=0.05,
         growth=0.01, terminal_growth=0.015, net_debt=3.1e9, debt_to_equity=0.85, beta_u=1.1,
         sales_to_capital=2.2, idea_category="turnaround", roic_stable=0.06, healthy=False),
    dict(ticker="MERD", name="Meridian Bancorp", exchange="NYSE", sector="Financials",
         price=63.0, shares=520e6, revenue=12e9, ebit_margin=0.40, target_margin=0.40,
         growth=0.06, terminal_growth=0.025, net_debt=0.0, debt_to_equity=0.20, beta_u=0.9,
         sales_to_capital=3.0, idea_category="stalwart", roic_stable=0.15),
]

UNIVERSE: dict[str, CompanyInputs] = {s["ticker"]: _synth(**s) for s in _UNIVERSE_SPECS}


def price_history(ticker: str, days: int = 400) -> list[dict]:
    """Deterministic synthetic daily price series for the chart (demo only)."""
    c = UNIVERSE.get(ticker)
    base = c.price if c else 100.0
    seed = sum(ord(ch) for ch in ticker)
    out = []
    for i in range(days):
        # smooth deterministic wiggle: two sine waves + slow drift
        drift = -0.12 * (1 - i / days)      # start ~12% lower, trend up to today
        wave = 0.05 * math.sin((i + seed) / 22.0) + 0.03 * math.sin((i + seed) / 7.0)
        px = base * (1 + drift + wave)
        out.append({"t": i, "close": round(px, 2)})
    out[-1]["close"] = base
    return out


# --------------------------------------------------------------------------- #
# Demo macro snapshot (FRED-shaped).
# --------------------------------------------------------------------------- #
DEMO_MACRO = {
    "asof": DEMO_ASOF,
    "unemployment_monthly": [3.7, 3.7, 3.8, 3.8, 3.9, 3.9, 3.9, 4.0, 4.0, 4.1, 4.1, 4.1,
                             4.1, 4.2, 4.2],   # UNRATE, last 15 months
    "t10y3m": 0.0025,     # +25bp, barely positive
    "pmi": 49.2,          # ISM manufacturing, mild contraction
    "hy_oas": 0.038,      # BAMLH0A0HYM2, benign
    "dgs10": RISK_FREE,
    "cpi_yoy": 0.026,
    "fed_target_low": 0.0400,
    "fed_target_high": 0.0425,
    "next_fomc": "2026-07-29",
    "sources": {"macro": "ValueScope demo dataset (FRED-shaped)"},
}
