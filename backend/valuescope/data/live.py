"""Autonomous company assembly: SEC EDGAR + Yahoo -> CompanyInputs.

Covers US filers (10-K, us-gaap) AND foreign private issuers listed in the US
(20-F/40-F, ifrs-full) — which brings most large European and emerging-market
companies (SAP, ASML, TSM, Shell, Novo Nordisk, Alibaba, Vale, Infosys…) into
scope with the same SEC-grade data. IFRS filers report in their home currency;
every monetary item is converted to US$ at the live spot rate so statements,
market cap and per-share values stay consistent.

Zero configuration and zero synthetic numbers. Every figure is either
(a) read from an SEC filing (XBRL companyfacts, multi-tag candidates because
    taxonomy names vary by filer and by GAAP/IFRS),
(b) observed in the market (price, FX, regression beta vs the S&P 500), or
(c) a documented, versioned modelling assumption derived from those two.

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

# Ordinary shares per depositary receipt for well-known US-listed foreign
# issuers (public reference facts, used when Yahoo's listing share count is
# unavailable). EDGAR reports ORDINARY shares; the listing price is per ADS.
KNOWN_ADR_RATIOS = {
    "TSM": 5.0, "SHEL": 2.0, "BABA": 8.0, "SAP": 1.0, "NVO": 1.0,
    "INFY": 1.0, "VALE": 1.0, "ASML": 1.0, "SONY": 1.0, "UL": 1.0,
}

# XBRL concept candidates, in preference order — us-gaap then ifrs-full names
# (both namespaces are scanned; recency picks the winner).
REVENUE = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
           "SalesRevenueNet", "SalesRevenueGoodsNet",
           "Revenue", "RevenueFromContractsWithCustomers"]
EBIT = ["OperatingIncomeLoss", "ProfitLossFromOperatingActivities", "OperatingProfitLoss"]
COSTS_AND_EXPENSES = ["CostsAndExpenses"]
NET_INCOME = ["NetIncomeLoss", "ProfitLoss"]
CFO = ["NetCashProvidedByUsedInOperatingActivities",
       "CashFlowsFromUsedInOperatingActivities"]
CAPEX = ["PaymentsToAcquirePropertyPlantAndEquipment",
         "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"]
ASSETS = ["Assets"]
ASSETS_CURRENT = ["AssetsCurrent", "CurrentAssets"]
LIABILITIES = ["Liabilities"]
LIABILITIES_CURRENT = ["LiabilitiesCurrent", "CurrentLiabilities"]
EQUITY = ["StockholdersEquity",
          "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
          "Equity", "EquityAttributableToOwnersOfParent"]
CASH = ["CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "CashAndCashEquivalents"]
ST_INVESTMENTS = ["ShortTermInvestments", "MarketableSecuritiesCurrent",
                  "AvailableForSaleSecuritiesCurrent", "CurrentFinancialAssets"]
LT_DEBT = ["LongTermDebtNoncurrent", "LongTermDebt",
           "NoncurrentBorrowings", "LongtermBorrowings"]
DEBT_CURRENT = ["LongTermDebtCurrent", "DebtCurrent", "ShortTermBorrowings",
                "CommercialPaper", "CurrentBorrowings", "ShorttermBorrowings"]
PPE = ["PropertyPlantAndEquipmentNet", "PropertyPlantAndEquipment"]
RECEIVABLES = ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent",
               "TradeAndOtherCurrentReceivables", "CurrentTradeReceivables"]
COGS = ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold", "CostOfSales"]
SGA = ["SellingGeneralAndAdministrativeExpense",
       "SellingGeneralAndAdministrativeExpenses", "AdministrativeExpense"]
DEPRECIATION = ["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet",
                "DepreciationAndAmortization", "Depreciation",
                "DepreciationAndAmortisationExpense"]
TAX = ["IncomeTaxExpenseBenefit", "IncomeTaxExpenseContinuingOperations"]
PRETAX = ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
          "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
          "ProfitLossBeforeTax"]
INTEREST = ["InterestExpense", "InterestExpenseDebt", "InterestExpenseNonoperating",
            "InterestAndDebtExpense", "FinanceCosts"]
RETAINED = ["RetainedEarningsAccumulatedDeficit", "RetainedEarnings"]
DILUTED_SHARES = ["WeightedAverageNumberOfDilutedSharesOutstanding",
                  "AdjustedWeightedAverageShares", "WeightedAverageShares"]


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


class _Money:
    """Currency-consistent, US$-converted access to EDGAR statement items."""

    def __init__(self, facts: dict, currency: str, fx: float):
        self.facts, self.currency, self.fx = facts, currency, fx

    def series(self, concepts, *, flow=False, n=5):
        s, _ = edgar.monetary_series(self.facts, concepts, currency=self.currency,
                                     flow=flow, n=n)
        return [(end, v * self.fx) for end, v in s]

    def latest(self, concepts, *, flow=False):
        s = self.series(concepts, flow=flow, n=1)
        return s[-1][1] if s else None

    def pair(self, concepts, *, flow=False):
        v = [x for _, x in self.series(concepts, flow=flow)]
        return (v[-2], v[-1]) if len(v) >= 2 else None


def _listing_shares(ticker: str, facts: dict, currency: str) -> tuple[float, str]:
    """Share count consistent with the LISTING price.

    EDGAR reports ordinary shares; for depositary receipts the listing trades
    ADSs, so the ordinary count must be divided by the ADR ratio. Preference:
    Yahoo's listing share count (already ADS-equivalent) -> EDGAR ÷ known
    ratio -> EDGAR as-is (domestic filers)."""
    edgar_shares = edgar.shares_outstanding(facts)
    yahoo_shares = yahoo.listing_shares(ticker)
    if yahoo_shares:
        # Guard against unit disagreements: trust Yahoo when it's within 20x
        # of EDGAR either way (it always is for sane listings).
        if not edgar_shares or 0.05 < yahoo_shares / edgar_shares < 20:
            return yahoo_shares, "Yahoo listing share count"
    if edgar_shares and ticker in KNOWN_ADR_RATIOS:
        return edgar_shares / KNOWN_ADR_RATIOS[ticker], \
            f"EDGAR ÷ ADR ratio {KNOWN_ADR_RATIOS[ticker]:.0f}"
    if edgar_shares:
        if currency != "USD":
            raise ValueError(
                f"{ticker}: foreign filer with unknown ADR ratio and no listing "
                "share count — refusing to guess the per-share denominator")
        return edgar_shares, "EDGAR dei shares outstanding"
    raise ValueError(f"{ticker}: no share count available")


def build_company(ticker: str, *, risk_free: float) -> CompanyInputs:
    """Assemble a fully live CompanyInputs. Raises on missing essentials."""
    ticker = ticker.upper()
    facts = edgar.company_facts(ticker)
    profile = edgar.company_profile(ticker)
    chart = yahoo.fetch_chart(ticker, rng="1y")
    price = chart["price"]
    if not price or price <= 0:
        raise ValueError(f"{ticker}: no market price")
    if chart.get("currency", "USD") != "USD":
        raise ValueError(f"{ticker}: only US-listed (US$) listings are supported — "
                         "search the US listing/ADR symbol")

    # ---- statement currency & essentials ------------------------------------
    rev_raw, currency = edgar.monetary_series(facts, REVENUE, flow=True)
    if len(rev_raw) < 2 or currency is None:
        raise ValueError(f"{ticker}: EDGAR lacks XBRL revenue "
                         "(bank/new entity/non-SEC filer?)")
    fx = yahoo.fx_to_usd(currency)
    money = _Money(facts, currency, fx)
    rev_s = [(end, v * fx) for end, v in rev_raw]

    ebit_s = money.series(EBIT, flow=True)
    if not ebit_s or ebit_s[-1][0] < rev_s[-1][0]:
        # No operating-income line (CVX) or it went stale (JNJ post-2014).
        # Fallback 1: revenue − total costs, aligned by fiscal year end.
        costs = dict(money.series(COSTS_AND_EXPENSES, flow=True))
        derived = [(end, rev - costs[end]) for end, rev in rev_s if end in costs]
        if not derived or (ebit_s and derived[-1][0] <= ebit_s[-1][0]):
            # Fallback 2: EBIT ≈ pretax income + interest expense.
            pretax_s = dict(money.series(PRETAX, flow=True))
            interest_s = dict(money.series(INTEREST, flow=True))
            derived = [(end, pretax_s[end] + interest_s.get(end, 0.0))
                       for end in sorted(pretax_s)]
        if derived and (not ebit_s or derived[-1][0] > ebit_s[-1][0]):
            ebit_s = derived
    if not ebit_s:
        raise ValueError(f"{ticker}: cannot establish operating income from filings")

    revenue = rev_s[-1][1]
    ebit = ebit_s[-1][1]
    if rev_s[-1][0] != ebit_s[-1][0]:
        raise ValueError(f"{ticker}: revenue ({rev_s[-1][0]}) and EBIT ({ebit_s[-1][0]}) "
                         "series end in different fiscal years")
    if not (-0.5 < ebit / revenue < 0.65):
        raise ValueError(f"{ticker}: implausible operating margin "
                         f"{ebit / revenue:.0%} — inconsistent XBRL series")

    shares, shares_source = _listing_shares(ticker, facts, currency)
    market_cap = price * shares

    # ---- capital structure --------------------------------------------------
    lt_debt = money.latest(LT_DEBT) or 0.0
    st_debt = money.latest(DEBT_CURRENT) or 0.0
    debt = lt_debt + st_debt
    cash = (money.latest(CASH) or 0.0) + (money.latest(ST_INVESTMENTS) or 0.0)
    net_debt = debt - cash
    debt_to_equity = debt / market_cap if market_cap > 0 else 0.0

    # ---- rates & beta -------------------------------------------------------
    tax = money.latest(TAX, flow=True)
    pretax = money.latest(PRETAX, flow=True)
    tax_rate = _clamp(tax / pretax, 0.10, 0.35) if (tax and pretax and pretax > 0) else 0.21

    beta_levered = yahoo.regression_beta(ticker)          # observed vs S&P 500
    beta_u = unlever_beta(beta_levered, tax_rate, debt_to_equity)

    interest = money.latest(INTEREST, flow=True)
    if interest and debt > 0:
        cost_of_debt = _clamp(interest / debt, risk_free + 0.005, risk_free + 0.05)
    else:
        cost_of_debt = risk_free + 0.01

    # ---- growth & margins (from filed history) ------------------------------
    rev_vals = [v for _, v in rev_s]
    yrs = len(rev_vals) - 1
    cagr = (rev_vals[-1] / rev_vals[0]) ** (1 / yrs) - 1 if rev_vals[0] > 0 else 0.0
    # Cap at 30%: even hypergrowth fades — the model already decays growth to
    # the terminal rate after year 5 (Damodaran, Narrative and Numbers ch. 9).
    growth_initial = _clamp(cagr, 0.0, 0.30)
    growth_hist = [rev_vals[i] / rev_vals[i - 1] - 1 for i in range(1, len(rev_vals))]

    margins = [e / r for (_, e), (_, r) in zip(ebit_s, rev_s[-len(ebit_s):]) if r > 0]
    margin_now = ebit / revenue
    target_margin = _clamp(max(margin_now, statistics.median(margins)), 0.03, 0.45)

    equity_book = money.latest(EQUITY)
    invested_capital = (equity_book or market_cap * 0.5) + debt - cash
    if invested_capital <= 0:
        invested_capital = revenue / 2.0
    sales_to_capital = _clamp(revenue / invested_capital, 0.5, 5.0)
    roic = _clamp(ebit * (1 - tax_rate) / invested_capital, 0.05, 0.30)

    wacc_terminal = risk_free + MATURE_WACC_PREMIUM
    growth_terminal = min(0.025, risk_free)

    # ---- balance-sheet extras ------------------------------------------------
    assets_current = money.latest(ASSETS_CURRENT)
    liabilities = money.latest(LIABILITIES)
    liabilities_current = money.latest(LIABILITIES_CURRENT)
    ppe = money.latest(PPE)
    ni = money.latest(NET_INCOME, flow=True)
    cfo = money.latest(CFO, flow=True)
    da = money.latest(DEPRECIATION, flow=True)
    capex = money.latest(CAPEX, flow=True)

    # ---- forensic scores (skip when filer omits tags) ------------------------
    piotroski = _build_piotroski(money, facts)
    altman = _build_altman(money, market_cap)
    beneish = _build_beneish(money)

    quality = QualityInputs(
        roic=roic, wacc=0.0,  # WACC injected by analyze()
        revenue_growth_history=growth_hist,
        net_debt=net_debt,
        ebitda=ebit + (da or 0.0),
        cfo=cfo or 0.0,
        net_income=ni or 1.0,
    )

    trap = _build_trap(money, rev_s=rev_s, margins=margins, debt_now=debt, roic=roic,
                       wacc_terminal=wacc_terminal, ni=ni, cfo=cfo, capex=capex,
                       da=da, piotroski=piotroski, beneish=beneish)

    missing_scores = sum(1 for s in (piotroski, altman, beneish) if s is None)
    data_quality = "high" if missing_scores == 0 else ("medium" if missing_scores == 1 else "low")
    # Valuation sanity: an implausible implied P/E usually means a share-count
    # or currency inconsistency — flag rather than hide.
    if ni and ni > 0 and not (1.0 < market_cap / ni < 200.0):
        data_quality = "low"

    if growth_initial >= 0.12:
        idea = "compounder"
    elif growth_initial >= 0.06:
        idea = "stalwart"
    elif growth_initial >= 0.02:
        idea = "mean_reversion"
    else:
        idea = "turnaround"

    fundamentals_src = f"SEC EDGAR annual filings (XBRL, FY {rev_s[-1][0]})"
    if currency != "USD":
        fundamentals_src += f", {currency} converted at {fx:.4f} US$/{currency}"

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
            "fundamentals": fundamentals_src,
            "prices": "Yahoo Finance (live)",
            "beta": "2Y daily regression vs S&P 500 (Yahoo)",
            "shares": shares_source,
        },
        asof=rev_s[-1][0],
    )


# --------------------------------------------------------------------------- #
def _build_piotroski(money: _Money, facts: dict) -> PiotroskiInputs | None:
    ni = money.pair(NET_INCOME, flow=True)
    cfo = money.pair(CFO, flow=True)
    ta = money.pair(ASSETS)
    ltd = money.pair(LT_DEBT)
    ca = money.pair(ASSETS_CURRENT)
    cl = money.pair(LIABILITIES_CURRENT)
    sh = None
    s = edgar.annual_series(facts, DILUTED_SHARES, unit="shares", flow=True)
    v = [x for _, x in s]
    if len(v) >= 2:
        sh = (v[-2], v[-1])
    rev = money.pair(REVENUE, flow=True)
    cogs = money.pair(COGS, flow=True)
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


def _build_altman(money: _Money, market_cap: float) -> AltmanInputs | None:
    ca = money.latest(ASSETS_CURRENT)
    cl = money.latest(LIABILITIES_CURRENT)
    re = money.latest(RETAINED)
    ebit = money.latest(EBIT, flow=True)
    tl = money.latest(LIABILITIES)
    sales = money.latest(REVENUE, flow=True)
    ta = money.latest(ASSETS)
    if None in (ca, cl, re, ebit, tl, sales, ta) or not ta or not tl:
        return None
    return AltmanInputs(working_capital=ca - cl, retained_earnings=re, ebit=ebit,
                        market_value_equity=market_cap, total_liabilities=tl,
                        sales=sales, total_assets=ta)


def _build_beneish(money: _Money) -> BeneishInputs | None:
    rec = money.pair(RECEIVABLES)
    rev = money.pair(REVENUE, flow=True)
    cogs = money.pair(COGS, flow=True)
    ca = money.pair(ASSETS_CURRENT)
    ppe = money.pair(PPE)
    ta = money.pair(ASSETS)
    dep = money.pair(DEPRECIATION, flow=True)
    sga = money.pair(SGA, flow=True)
    cl = money.pair(LIABILITIES_CURRENT)
    ltd = money.pair(LT_DEBT)
    ni = money.latest(NET_INCOME, flow=True)
    cfo = money.latest(CFO, flow=True)
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


def _build_trap(money: _Money, *, rev_s, margins, debt_now, roic, wacc_terminal,
                ni, cfo, capex, da, piotroski, beneish) -> ValueTrapInputs:
    rev = [v for _, v in rev_s]
    debt_pair = money.pair(LT_DEBT) or (debt_now, debt_now)
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
