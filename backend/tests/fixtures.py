"""Offline test fixtures — deterministic CompanyInputs/macro dicts so API and
pipeline tests never touch the network. Test-only; production is 100% live."""
from __future__ import annotations

import math

from valuescope.engine.analyze import CompanyInputs
from valuescope.engine.quality import (AltmanInputs, BeneishInputs, PiotroskiInputs,
                                       QualityInputs)
from valuescope.engine.verdict import ValueTrapInputs

RISK_FREE = 0.0425


def make_company(ticker="TSTA", name="Test Alpha", price=88.0, shares=1.8e9,
                 revenue=42e9, margin=0.28, growth=0.14, net_debt=-8e9) -> CompanyInputs:
    ebit = revenue * margin
    ta = revenue * 1.4
    ni = ebit * 0.75
    cfo = ni * 1.15
    ca, cl = ta * 0.35, ta * 0.18
    ppe = ta * 0.30
    return CompanyInputs(
        ticker=ticker, name=name, exchange="NASDAQ", sector="Technology",
        price=price, shares=shares, net_debt=net_debt, idea_category="compounder",
        data_quality="high", beta_unlevered=1.1, tax_rate=0.21, debt_to_equity=0.10,
        risk_free=RISK_FREE, erp=0.045, pretax_cost_of_debt=0.05,
        revenue_base=revenue, ebit_margin_base=margin, target_margin=margin + 0.02,
        growth_initial=growth, growth_terminal=0.025, sales_to_capital=2.5,
        wacc_terminal=RISK_FREE + 0.045, roic_stable=0.20,
        quality=QualityInputs(roic=0.20, wacc=0.0,
                              revenue_growth_history=[growth, growth * 0.95, growth * 1.05],
                              net_debt=net_debt, ebitda=ebit * 1.2, cfo=cfo, net_income=ni),
        piotroski=PiotroskiInputs(
            net_income=ni, cfo=cfo, total_assets=ta, total_assets_prior=ta / 1.1,
            roa_prior=ni / ta * 0.9, long_term_debt=2e9, long_term_debt_prior=2.5e9,
            current_assets=ca, current_liabilities=cl,
            current_assets_prior=ca / 1.1, current_liabilities_prior=cl / 1.05,
            shares=shares, shares_prior=shares * 1.01,
            gross_margin=0.42, gross_margin_prior=0.40,
            asset_turnover=revenue / ta, asset_turnover_prior=revenue / ta * 0.95),
        altman=AltmanInputs(working_capital=ca - cl, retained_earnings=ta * 0.35,
                            ebit=ebit, market_value_equity=price * shares,
                            total_liabilities=ta * 0.45, sales=revenue, total_assets=ta),
        beneish=BeneishInputs(
            receivables=revenue * 0.12, receivables_prior=revenue * 0.11,
            sales=revenue, sales_prior=revenue / 1.1,
            cogs=revenue * 0.58, cogs_prior=revenue / 1.1 * 0.58,
            current_assets=ca, current_assets_prior=ca / 1.1,
            net_ppe=ppe, net_ppe_prior=ppe / 1.1,
            total_assets=ta, total_assets_prior=ta / 1.1,
            depreciation=ppe * 0.1, depreciation_prior=ppe / 1.1 * 0.1,
            sga=revenue * 0.15, sga_prior=revenue / 1.1 * 0.15,
            net_income=ni, cfo=cfo,
            current_liabilities=cl, current_liabilities_prior=cl / 1.1,
            long_term_debt=2e9, long_term_debt_prior=2e9),
        trap=ValueTrapInputs(False, False, False, False, False, False, False, False),
        ncav_current_assets=ca, ncav_total_liabilities=ta * 0.45,
        magic_nwc=ca - cl, magic_nfa=ppe,
        sources={"fundamentals": "test fixture", "prices": "test fixture"},
        asof="2026-06-30",
    )


def make_price_history(base: float, days: int = 300) -> list[dict]:
    return [{"t": i, "close": round(base * (1 + 0.05 * math.sin(i / 20)), 2)}
            for i in range(days)]


def make_macro() -> dict:
    return {
        "asof": "2026-06-30",
        "dgs10": RISK_FREE,
        "t10y3m": 0.0025,
        "unemployment_monthly": [3.7, 3.7, 3.8, 3.8, 3.9, 3.9, 3.9, 4.0, 4.0, 4.1,
                                 4.1, 4.1, 4.1, 4.2, 4.2],
        "hy_oas": 0.038,
        "credit_proxy": None,
        "ip_yoy": 0.012,
        "cpi_yoy": 0.026,
        "fed_target_low": 0.0400,
        "fed_target_high": 0.0425,
        "next_fomc": "2026-07-29",
        "sources": {"macro": "test fixture"},
    }
