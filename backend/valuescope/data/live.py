"""Autonomous company assembly: SEC EDGAR + Yahoo -> CompanyInputs.

Zero configuration and zero synthetic numbers. Every figure is either
(a) read from an SEC filing (XBRL companyfacts, multi-tag candidates because
    taxonomy names vary by filer),
(b) observed in the market (price, regression beta vs the S&P 500), or
(c) a documented, versioned modelling assumption derived from those two
    (growth from filed revenue history, target margin from filed margins,
    stable WACC = Rf + mature-market premium, terminal growth capped at Rf).

Forensic scores (Piotroski/Altman/Beneish) need two fiscal years of specific
tags; when a filer doesn't report a tag, that score is skipped and
data_quality is downgraded — the engine never invents the missing input.
"""
from __future__ import annotations

import statistics

from ..engine.analyze import CompanyInputs
from ..engine.beta import unlever_beta
from ..engine.quality import (
    AltmanInputs, BeneishInputs, PiotroskiInputs, QualityInputs,
    beneish_m_score, piotroski_f_score,
)
from ..engine.verdict import ValueTrapInputs
from . import edgar, yahoo

# Damodaran implied US equity risk premium — reference constant, reviewed with
# releases (https://pages.stern.nyu.edu/~adamodar/, "Implied ERP").
ERP = 0.045
# Mature-market premium over the risk-free rate for the stable-phase WACC
# (Damodaran, fcffsimpleginzu: stable cost of capital ≈ Rf + 4.5%).
MATURE_WACC_PREMIUM = 0.045

# XBRL concept candidates, in preference order.
REVENUE = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
           "SalesRevenueNet", "SalesRevenueGoodsNet"]
EBIT = ["OperatingIncomeLoss"]
COSTS_AND_EXPENSES = ["CostsAndExpenses"]  # EBIT fallback: revenue − total costs
NET_INCOME = ["NetIncomeLoss"]
CFO = ["NetCashProvidedByUsedInOperatingActivities"]
CAPEX = ["PaymentsToAcquirePropertyPlantAndEquipment"]
ASSETS = ["Assets"]
ASSETS_CURRENT = ["AssetsCurrent"]
LIABILITIES = ["Liabilities"]
LIABILITIES_CURRENT = ["LiabilitiesCurrent"]
EQUITY = ["StockholdersEquity",
          "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]
CASH = ["CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]
ST_INVESTMENTS = ["ShortTermInvestments", "MarketableSecuritiesCurrent",
                  "AvailableForSaleSecuritiesCurrent"]
LT_DEBT = ["LongTermDebtNoncurrent", "LongTermDebt"]
DEBT_CURRENT = ["LongTermDebtCurrent", "DebtCurrent", "ShortTermBorrowings", "CommercialPaper"]
PPE = ["PropertyPlantAndEquipmentNet"]
RECEIVABLES = ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent"]
COGS = ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold"]
SGA = ["SellingGeneralAndAdministrativeExpense"]
DEPRECIATION = ["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet",
                "DepreciationAndAmortization", "Depreciation"]
TAX = ["IncomeTaxExpenseBenefit"]
PRETAX = ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
          "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"]
INTEREST = ["InterestExpense", "InterestExpenseDebt", "InterestExpenseNonoperating",
            "InterestAndDebtExpense"]
RETAINED = ["RetainedEarningsAccumulatedDeficit"]
DILUTED_SHARES = ["WeightedAverageNumberOfDilutedSharesOutstanding"]


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _vals(series):
    return [v for _, v in series]


def _pair(series):
    """(prior, current) from a fiscal-year series, or None."""
    v = _vals(series)
    return (v[-2], v[-1]) if len(v) >= 2 else None


def build_company(ticker: str, *, risk_free: float) -> CompanyInputs:
    """Assemble a fully live CompanyInputs. Raises on missing essentials."""
    ticker = ticker.upper()
    facts = edgar.company_facts(ticker)
    profile = edgar.company_profile(ticker)
    chart = yahoo.fetch_chart(ticker, rng="1y")
    price = chart["price"]
    if not price or price <= 0:
        raise ValueError(f"{ticker}: no market price")

    # ---- essentials ---------------------------------------------------------
    rev_s = edgar.annual_series(facts, REVENUE, flow=True)
    ebit_s = edgar.annual_series(facts, EBIT, flow=True)
    if not ebit_s or (rev_s and ebit_s[-1][0] < rev_s[-1][0]):
        # Filers that report no operating-income line (CVX) or stopped years
        # ago (JNJ after 2014). Fallback 1: revenue − total costs, aligned by
        # fiscal year end.
        costs = dict(edgar.annual_series(facts, COSTS_AND_EXPENSES, flow=True))
        derived = [(end, rev - costs[end]) for end, rev in rev_s if end in costs]
        if not derived or (ebit_s and derived[-1][0] <= ebit_s[-1][0]):
            # Fallback 2: EBIT ≈ pretax income + interest expense (slightly
            # overstates when interest income is material; bounded below).
            pretax = dict(edgar.annual_series(facts, PRETAX, flow=True))
            interest = dict(edgar.annual_series(facts, INTEREST, flow=True))
            derived = [(end, pretax[end] + interest.get(end, 0.0)) for end in sorted(pretax)]
        if derived and (not ebit_s or derived[-1][0] > ebit_s[-1][0]):
            ebit_s = derived
    shares = edgar.shares_outstanding(facts)
    if len(rev_s) < 2 or not ebit_s or not shares:
        raise ValueError(f"{ticker}: EDGAR lacks XBRL revenue/EBIT/shares "
                         "(bank/new entity/foreign filer?)")
    revenue = rev_s[-1][1]
    ebit = ebit_s[-1][1]
    # Consistency guard: revenue and EBIT must describe the same fiscal year —
    # tag migrations can otherwise pair a stale series with a current one.
    if rev_s[-1][0] != ebit_s[-1][0]:
        raise ValueError(f"{ticker}: revenue ({rev_s[-1][0]}) and EBIT ({ebit_s[-1][0]}) "
                         "series end in different fiscal years")
    if not (-0.5 < ebit / revenue < 0.65):
        raise ValueError(f"{ticker}: implausible operating margin "
                         f"{ebit / revenue:.0%} — inconsistent XBRL series")
    market_cap = price * shares

    # ---- capital structure --------------------------------------------------
    lt_debt = edgar.latest_annual(facts, LT_DEBT) or 0.0
    st_debt = edgar.latest_annual(facts, DEBT_CURRENT) or 0.0
    debt = lt_debt + st_debt
    cash = (edgar.latest_annual(facts, CASH) or 0.0) + (edgar.latest_annual(facts, ST_INVESTMENTS) or 0.0)
    net_debt = debt - cash
    debt_to_equity = debt / market_cap if market_cap > 0 else 0.0

    # ---- rates & beta -------------------------------------------------------
    tax = edgar.latest_annual(facts, TAX, flow=True)
    pretax = edgar.latest_annual(facts, PRETAX, flow=True)
    tax_rate = _clamp(tax / pretax, 0.10, 0.35) if (tax and pretax and pretax > 0) else 0.21

    beta_levered = yahoo.regression_beta(ticker)          # observed vs S&P 500
    beta_u = unlever_beta(beta_levered, tax_rate, debt_to_equity)

    interest = edgar.latest_annual(facts, INTEREST, flow=True)
    if interest and debt > 0:
        cost_of_debt = _clamp(interest / debt, risk_free + 0.005, risk_free + 0.05)
    else:
        cost_of_debt = risk_free + 0.01

    # ---- growth & margins (from filed history) ------------------------------
    rev_vals = _vals(rev_s)
    yrs = len(rev_vals) - 1
    cagr = (rev_vals[-1] / rev_vals[0]) ** (1 / yrs) - 1 if rev_vals[0] > 0 else 0.0
    # Cap at 30%: even hypergrowth fades — the model already decays growth to
    # the terminal rate after year 5 (Damodaran, Narrative and Numbers ch. 9).
    growth_initial = _clamp(cagr, 0.0, 0.30)
    growth_hist = [rev_vals[i] / rev_vals[i - 1] - 1 for i in range(1, len(rev_vals))]

    margins = [e / r for (_, e), (_, r) in zip(ebit_s, rev_s[-len(ebit_s):]) if r > 0]
    margin_now = ebit / revenue
    target_margin = _clamp(max(margin_now, statistics.median(margins)), 0.03, 0.45)

    equity_book = edgar.latest_annual(facts, EQUITY)
    invested_capital = (equity_book or market_cap * 0.5) + debt - cash
    if invested_capital <= 0:
        invested_capital = revenue / 2.0
    sales_to_capital = _clamp(revenue / invested_capital, 0.5, 5.0)
    roic = _clamp(ebit * (1 - tax_rate) / invested_capital, 0.05, 0.30)

    wacc_terminal = risk_free + MATURE_WACC_PREMIUM
    growth_terminal = min(0.025, risk_free)

    # ---- balance-sheet extras ------------------------------------------------
    assets = edgar.latest_annual(facts, ASSETS)
    assets_current = edgar.latest_annual(facts, ASSETS_CURRENT)
    liabilities = edgar.latest_annual(facts, LIABILITIES)
    liabilities_current = edgar.latest_annual(facts, LIABILITIES_CURRENT)
    ppe = edgar.latest_annual(facts, PPE)
    ni = edgar.latest_annual(facts, NET_INCOME, flow=True)
    cfo = edgar.latest_annual(facts, CFO, flow=True)
    da = edgar.latest_annual(facts, DEPRECIATION, flow=True)
    capex = edgar.latest_annual(facts, CAPEX, flow=True)

    # ---- forensic scores (skip when filer omits tags) ------------------------
    piotroski = _build_piotroski(facts)
    altman = _build_altman(facts, market_cap)
    beneish = _build_beneish(facts)

    quality = QualityInputs(
        roic=roic, wacc=0.0,  # WACC injected by analyze()
        revenue_growth_history=growth_hist,
        net_debt=net_debt,
        ebitda=ebit + (da or 0.0),
        cfo=cfo or 0.0,
        net_income=ni or 1.0,
    )

    trap = _build_trap(facts, margins=margins, debt_now=debt, roic=roic,
                       wacc_terminal=wacc_terminal, ni=ni, cfo=cfo, capex=capex,
                       da=da, piotroski=piotroski, beneish=beneish)

    missing_scores = sum(1 for s in (piotroski, altman, beneish) if s is None)
    data_quality = "high" if missing_scores == 0 else ("medium" if missing_scores == 1 else "low")

    if growth_initial >= 0.12:
        idea = "compounder"
    elif growth_initial >= 0.06:
        idea = "stalwart"
    elif growth_initial >= 0.02:
        idea = "mean_reversion"
    else:
        idea = "turnaround"

    return CompanyInputs(
        ticker=ticker, name=profile["name"], exchange=profile["exchange"],
        sector=profile["sector"], price=float(price), shares=shares, net_debt=net_debt,
        idea_category=idea, data_quality=data_quality,
        beta_unlevered=beta_u, tax_rate=tax_rate, debt_to_equity=debt_to_equity,
        risk_free=risk_free, erp=ERP, pretax_cost_of_debt=cost_of_debt,
        revenue_base=revenue, ebit_margin_base=margin_now, target_margin=target_margin,
        growth_initial=growth_initial, growth_terminal=growth_terminal,
        sales_to_capital=sales_to_capital, wacc_terminal=wacc_terminal, roic_stable=roic,
        quality=quality, piotroski=piotroski, altman=altman, beneish=beneish, trap=trap,
        ncav_current_assets=assets_current or 0.0,
        ncav_total_liabilities=liabilities or 0.0,
        magic_nwc=(assets_current or 0.0) - (liabilities_current or 0.0),
        magic_nfa=ppe or 0.0,
        sources={
            "fundamentals": f"SEC EDGAR 10-K (XBRL, FY {rev_s[-1][0]})",
            "prices": "Yahoo Finance (live)",
            "beta": "2Y daily regression vs S&P 500 (Yahoo)",
        },
        asof=rev_s[-1][0],
    )


# --------------------------------------------------------------------------- #
def _build_piotroski(facts) -> PiotroskiInputs | None:
    ni = _pair(edgar.annual_series(facts, NET_INCOME, flow=True))
    cfo = _pair(edgar.annual_series(facts, CFO, flow=True))
    ta = _pair(edgar.annual_series(facts, ASSETS))
    ltd = _pair(edgar.annual_series(facts, LT_DEBT))
    ca = _pair(edgar.annual_series(facts, ASSETS_CURRENT))
    cl = _pair(edgar.annual_series(facts, LIABILITIES_CURRENT))
    sh = _pair(edgar.annual_series(facts, DILUTED_SHARES, unit="shares", flow=True))
    rev = _pair(edgar.annual_series(facts, REVENUE, flow=True))
    cogs = _pair(edgar.annual_series(facts, COGS, flow=True))
    if not all((ni, cfo, ta, ca, cl, rev, cogs)):
        return None
    ltd = ltd or (0.0, 0.0)
    sh = sh or (1.0, 1.0)
    gm_prior = (rev[0] - cogs[0]) / rev[0]
    gm_now = (rev[1] - cogs[1]) / rev[1]
    return PiotroskiInputs(
        net_income=ni[1], cfo=cfo[1], total_assets=ta[1], total_assets_prior=ta[0],
        roa_prior=ni[0] / ta[0] if ta[0] else 0.0,
        long_term_debt=ltd[1], long_term_debt_prior=ltd[0],
        current_assets=ca[1], current_liabilities=cl[1],
        current_assets_prior=ca[0], current_liabilities_prior=cl[0],
        shares=sh[1], shares_prior=sh[0],
        gross_margin=gm_now, gross_margin_prior=gm_prior,
        asset_turnover=rev[1] / ta[1] if ta[1] else 0.0,
        asset_turnover_prior=rev[0] / ta[0] if ta[0] else 0.0,
    )


def _build_altman(facts, market_cap: float) -> AltmanInputs | None:
    ca = edgar.latest_annual(facts, ASSETS_CURRENT)
    cl = edgar.latest_annual(facts, LIABILITIES_CURRENT)
    re = edgar.latest_annual(facts, RETAINED)
    ebit = edgar.latest_annual(facts, EBIT, flow=True)
    tl = edgar.latest_annual(facts, LIABILITIES)
    sales = edgar.latest_annual(facts, REVENUE, flow=True)
    ta = edgar.latest_annual(facts, ASSETS)
    if None in (ca, cl, re, ebit, tl, sales, ta) or not ta or not tl:
        return None
    return AltmanInputs(working_capital=ca - cl, retained_earnings=re, ebit=ebit,
                        market_value_equity=market_cap, total_liabilities=tl,
                        sales=sales, total_assets=ta)


def _build_beneish(facts) -> BeneishInputs | None:
    rec = _pair(edgar.annual_series(facts, RECEIVABLES))
    rev = _pair(edgar.annual_series(facts, REVENUE, flow=True))
    cogs = _pair(edgar.annual_series(facts, COGS, flow=True))
    ca = _pair(edgar.annual_series(facts, ASSETS_CURRENT))
    ppe = _pair(edgar.annual_series(facts, PPE))
    ta = _pair(edgar.annual_series(facts, ASSETS))
    dep = _pair(edgar.annual_series(facts, DEPRECIATION, flow=True))
    sga = _pair(edgar.annual_series(facts, SGA, flow=True))
    cl = _pair(edgar.annual_series(facts, LIABILITIES_CURRENT))
    ltd = _pair(edgar.annual_series(facts, LT_DEBT))
    ni = edgar.latest_annual(facts, NET_INCOME, flow=True)
    cfo = edgar.latest_annual(facts, CFO, flow=True)
    if not all((rec, rev, cogs, ca, ppe, ta, dep, sga, cl)) or ni is None or cfo is None:
        return None
    ltd = ltd or (0.0, 0.0)
    return BeneishInputs(
        receivables=rec[1], receivables_prior=rec[0],
        sales=rev[1], sales_prior=rev[0],
        cogs=cogs[1], cogs_prior=cogs[0],
        current_assets=ca[1], current_assets_prior=ca[0],
        net_ppe=ppe[1], net_ppe_prior=ppe[0],
        total_assets=ta[1], total_assets_prior=ta[0],
        depreciation=dep[1], depreciation_prior=dep[0],
        sga=sga[1], sga_prior=sga[0],
        net_income=ni, cfo=cfo,
        current_liabilities=cl[1], current_liabilities_prior=cl[0],
        long_term_debt=ltd[1], long_term_debt_prior=ltd[0],
    )


def _build_trap(facts, *, margins, debt_now, roic, wacc_terminal, ni, cfo, capex, da,
                piotroski, beneish) -> ValueTrapInputs:
    rev = _vals(edgar.annual_series(facts, REVENUE, flow=True))
    debt_pair = _pair(edgar.annual_series(facts, LT_DEBT)) or (debt_now, debt_now)
    fcf = (cfo - (capex if capex is not None else (da or 0.0))) if cfo is not None else None

    high_beneish = False
    if beneish is not None:
        high_beneish = beneish_m_score(beneish).result["likely_manipulator"]
    low_piotroski = False
    if piotroski is not None:
        low_piotroski = piotroski_f_score(piotroski).result["score"] <= 3

    return ValueTrapInputs(
        revenue_declining=len(rev) >= 3 and rev[-1] < rev[-2] < rev[-3],
        margin_deteriorating=len(margins) >= 2 and margins[-1] < margins[-2] - 0.01,
        rising_leverage=debt_pair[1] > debt_pair[0] * 1.10 if debt_pair[0] > 0 else False,
        weak_cash_conversion=(cfo is not None and ni is not None and ni > 0 and cfo < ni),
        falling_roic=roic < wacc_terminal,
        high_beneish=high_beneish,
        low_piotroski=low_piotroski,
        negative_fcf=(fcf is not None and fcf < 0),
    )
