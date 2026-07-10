"""Quality & red-flag scores (PRD §6.3).

Piotroski F-Score, Altman Z-Score, Beneish M-Score, and a documented quality
composite ("ValueScope house rule v1").
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass

from ..registry import get_formula
from .trace import CalculationTrace, inp, step


# --------------------------------------------------------------------------- #
# Piotroski F-Score — Piotroski (2000), Journal of Accounting Research
# --------------------------------------------------------------------------- #
@dataclass
class PiotroskiInputs:
    net_income: float
    cfo: float                        # cash flow from operations
    total_assets: float               # current year-end
    total_assets_prior: float
    roa_prior: float                  # net income_{t-1} / total_assets_{t-1}
    long_term_debt: float
    long_term_debt_prior: float
    current_assets: float
    current_liabilities: float
    current_assets_prior: float
    current_liabilities_prior: float
    shares: float
    shares_prior: float
    gross_margin: float               # (sales - cogs)/sales, current
    gross_margin_prior: float
    asset_turnover: float             # sales/total_assets, current
    asset_turnover_prior: float


def piotroski_f_score(x: PiotroskiInputs) -> CalculationTrace:
    roa = x.net_income / x.total_assets if x.total_assets else 0.0
    cfo_ta = x.cfo / x.total_assets if x.total_assets else 0.0
    lev = x.long_term_debt / x.total_assets if x.total_assets else 0.0
    lev_prior = x.long_term_debt_prior / x.total_assets_prior if x.total_assets_prior else 0.0
    cr = x.current_assets / x.current_liabilities if x.current_liabilities else 0.0
    cr_prior = x.current_assets_prior / x.current_liabilities_prior if x.current_liabilities_prior else 0.0

    signals = {
        "ROA > 0": roa > 0,
        "CFO > 0": x.cfo > 0,
        "ΔROA > 0": roa > x.roa_prior,
        "Accruals (CFO/TA > ROA)": cfo_ta > roa,
        "ΔLeverage < 0": lev < lev_prior,
        "ΔCurrent ratio > 0": cr > cr_prior,
        "No new shares": x.shares <= x.shares_prior,
        "ΔGross margin > 0": x.gross_margin > x.gross_margin_prior,
        "ΔAsset turnover > 0": x.asset_turnover > x.asset_turnover_prior,
    }
    score = sum(1 for v in signals.values() if v)
    spec = get_formula("piotroski_f_score")
    return CalculationTrace(
        metric_id="piotroski_f",
        formula_id="piotroski_f_score",
        formula_version=spec.version,
        result={"score": score, "signals": {k: bool(v) for k, v in signals.items()}},
        unit="/9",
        plain="A 0-9 checklist of improving fundamentals; 8-9 is strong, 0-2 is weak.",
        inputs=[
            inp("Net income", x.net_income, "US$", "edgar", "income statement"),
            inp("CFO", x.cfo, "US$", "edgar", "cash flow statement"),
            inp("Total assets", x.total_assets, "US$", "edgar", "balance sheet"),
        ],
        steps=[step(k, "signal", v) for k, v in signals.items()]
              + [step("F-Score", "sum of true signals", score)],
        citation=spec.source_citation,
        caveats=["Designed by Piotroski for high book-to-market (value) firms."],
    )


# --------------------------------------------------------------------------- #
# Altman Z-Score — Altman (1968)
# --------------------------------------------------------------------------- #
@dataclass
class AltmanInputs:
    working_capital: float
    retained_earnings: float
    ebit: float
    market_value_equity: float
    total_liabilities: float
    sales: float
    total_assets: float


def altman_z_score(x: AltmanInputs) -> CalculationTrace:
    if x.total_assets == 0 or x.total_liabilities == 0:
        raise ValueError("total assets and liabilities must be non-zero")
    A = x.working_capital / x.total_assets
    B = x.retained_earnings / x.total_assets
    C = x.ebit / x.total_assets
    D = x.market_value_equity / x.total_liabilities
    E = x.sales / x.total_assets
    z = 1.2 * A + 1.4 * B + 3.3 * C + 0.6 * D + 1.0 * E
    zone = "safe" if z > 2.99 else ("distress" if z < 1.81 else "grey")
    spec = get_formula("altman_z_score")
    return CalculationTrace(
        metric_id="altman_z",
        formula_id="altman_z_score",
        formula_version=spec.version,
        result={"z": z, "zone": zone},
        unit="score",
        plain="Bankruptcy-risk score: above 2.99 is safe, below 1.81 is distress.",
        inputs=[
            inp("Working capital", x.working_capital, "US$", "edgar", "CA − CL"),
            inp("Retained earnings", x.retained_earnings, "US$", "edgar", "balance sheet"),
            inp("EBIT", x.ebit, "US$", "edgar", "income statement"),
            inp("Market value of equity", x.market_value_equity, "US$", "yfinance", "market cap"),
            inp("Total liabilities", x.total_liabilities, "US$", "edgar", "balance sheet"),
            inp("Sales", x.sales, "US$", "edgar", "income statement"),
            inp("Total assets", x.total_assets, "US$", "edgar", "balance sheet"),
        ],
        steps=[
            step("A · 1.2", f"1.2 × {A:.4f}", 1.2 * A),
            step("B · 1.4", f"1.4 × {B:.4f}", 1.4 * B),
            step("C · 3.3", f"3.3 × {C:.4f}", 3.3 * C),
            step("D · 0.6", f"0.6 × {D:.4f}", 0.6 * D),
            step("E · 1.0", f"1.0 × {E:.4f}", 1.0 * E),
            step("Z", "sum", z),
        ],
        citation=spec.source_citation,
        caveats=["Manufacturing form; use Z″ for services/emerging-market firms."],
    )


# --------------------------------------------------------------------------- #
# Beneish M-Score — Beneish (1999)
# --------------------------------------------------------------------------- #
@dataclass
class BeneishInputs:
    # current (t) and prior (t-1) year items
    receivables: float; receivables_prior: float
    sales: float; sales_prior: float
    cogs: float; cogs_prior: float
    current_assets: float; current_assets_prior: float
    net_ppe: float; net_ppe_prior: float
    total_assets: float; total_assets_prior: float
    depreciation: float; depreciation_prior: float
    sga: float; sga_prior: float
    net_income: float
    cfo: float
    current_liabilities: float; current_liabilities_prior: float
    long_term_debt: float; long_term_debt_prior: float


def beneish_m_score(x: BeneishInputs) -> CalculationTrace:
    dsri = (x.receivables / x.sales) / (x.receivables_prior / x.sales_prior)
    gm_t = (x.sales - x.cogs) / x.sales
    gm_p = (x.sales_prior - x.cogs_prior) / x.sales_prior
    gmi = gm_p / gm_t
    aqi_t = 1 - (x.current_assets + x.net_ppe) / x.total_assets
    aqi_p = 1 - (x.current_assets_prior + x.net_ppe_prior) / x.total_assets_prior
    aqi = aqi_t / aqi_p
    sgi = x.sales / x.sales_prior
    depi_t = x.depreciation / (x.depreciation + x.net_ppe)
    depi_p = x.depreciation_prior / (x.depreciation_prior + x.net_ppe_prior)
    depi = depi_p / depi_t
    sgai = (x.sga / x.sales) / (x.sga_prior / x.sales_prior)
    lev_t = (x.long_term_debt + x.current_liabilities) / x.total_assets
    lev_p = (x.long_term_debt_prior + x.current_liabilities_prior) / x.total_assets_prior
    lvgi = lev_t / lev_p
    tata = (x.net_income - x.cfo) / x.total_assets

    m = (-4.84 + 0.92 * dsri + 0.528 * gmi + 0.404 * aqi + 0.892 * sgi
         + 0.115 * depi - 0.172 * sgai + 4.679 * tata - 0.327 * lvgi)
    likely = m > -1.78
    spec = get_formula("beneish_m_score")
    parts = {"DSRI": dsri, "GMI": gmi, "AQI": aqi, "SGI": sgi, "DEPI": depi,
             "SGAI": sgai, "TATA": tata, "LVGI": lvgi}
    return CalculationTrace(
        metric_id="beneish_m",
        formula_id="beneish_m_score",
        formula_version=spec.version,
        result={"m": m, "likely_manipulator": likely, "components": parts},
        unit="score",
        plain="Earnings-manipulation detector; above −1.78 flags a likely manipulator.",
        inputs=[
            inp("Sales (t, t-1)", [x.sales, x.sales_prior], "US$", "edgar", "income statement"),
            inp("Receivables (t, t-1)", [x.receivables, x.receivables_prior], "US$", "edgar", "balance sheet"),
            inp("Net income", x.net_income, "US$", "edgar", "income statement"),
            inp("CFO", x.cfo, "US$", "edgar", "cash flow statement"),
        ],
        steps=[step(k, "index", round(v, 4)) for k, v in parts.items()]
              + [step("M-Score", "Beneish 8-variable model", m)],
        citation=spec.source_citation,
        caveats=["A high score flags manipulation risk, not proof; investigate before acting."],
    )


# --------------------------------------------------------------------------- #
# Quality composite (0-100) — ValueScope house rule v1
# --------------------------------------------------------------------------- #
def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


@dataclass
class QualityInputs:
    roic: float                 # return on invested capital (decimal)
    wacc: float                 # cost of capital (decimal)
    revenue_growth_history: list  # list of yearly growth rates (decimals)
    net_debt: float
    ebitda: float
    cfo: float
    net_income: float


def quality_composite(x: QualityInputs) -> CalculationTrace:
    # 1. ROIC vs WACC spread (weight 0.40): +10pp spread -> ~full marks.
    spread = x.roic - x.wacc
    s_spread = _clamp((spread + 0.05) / 0.20)  # -5pp -> 0, +15pp -> 1

    # 2. Growth consistency (weight 0.20): reward positive, low-variance growth.
    hist = [g for g in x.revenue_growth_history if g is not None]
    if len(hist) >= 2:
        mean_g = statistics.fmean(hist)
        sd_g = statistics.pstdev(hist)
        level = _clamp((mean_g + 0.05) / 0.25)           # -5% -> 0, +20% -> 1
        stability = _clamp(1 - sd_g / 0.15)              # 15% sd -> 0
        s_growth = 0.5 * level + 0.5 * stability
    else:
        s_growth = 0.5

    # 3. Leverage (weight 0.20): net debt / EBITDA, lower is better.
    nd_ebitda = (x.net_debt / x.ebitda) if x.ebitda > 0 else 5.0
    s_leverage = _clamp(1 - nd_ebitda / 4.0)             # 0x -> 1, 4x+ -> 0

    # 4. Cash conversion (weight 0.20): CFO / net income near/above 1 is good.
    conv = (x.cfo / x.net_income) if x.net_income > 0 else 0.0
    s_cash = _clamp(conv / 1.2)                          # 1.2x+ -> full marks

    total = 100 * (0.40 * s_spread + 0.20 * s_growth + 0.20 * s_leverage + 0.20 * s_cash)
    spec = get_formula("quality_composite")
    return CalculationTrace(
        metric_id="quality_composite",
        formula_id="quality_composite",
        formula_version=spec.version,
        result={
            "total": total,
            "bars": {
                "ROIC vs WACC": round(100 * s_spread, 1),
                "Growth consistency": round(100 * s_growth, 1),
                "Balance sheet": round(100 * s_leverage, 1),
                "Cash conversion": round(100 * s_cash, 1),
            },
        },
        unit="/100",
        plain="A single 0-100 read on business quality from returns, growth, leverage and cash.",
        inputs=[
            inp("ROIC", x.roic, "decimal", "computed", "NOPAT ÷ invested capital"),
            inp("WACC", x.wacc, "decimal", "formula", "cost of capital"),
            inp("Net debt / EBITDA", nd_ebitda, "ratio", "edgar", "leverage"),
            inp("CFO / net income", conv, "ratio", "edgar", "cash conversion"),
        ],
        steps=[
            step("ROIC-WACC spread (40%)", f"spread={spread:+.2%}", round(100 * s_spread, 1)),
            step("Growth consistency (20%)", "level & stability", round(100 * s_growth, 1)),
            step("Balance sheet (20%)", f"net debt/EBITDA={nd_ebitda:.2f}", round(100 * s_leverage, 1)),
            step("Cash conversion (20%)", f"CFO/NI={conv:.2f}", round(100 * s_cash, 1)),
            step("Composite", "weighted sum", round(total, 1)),
        ],
        citation=spec.source_citation,
        caveats=["House rule v1 weighting; the ROIC-WACC spread grounding is standard (Applied Corporate Finance 4e)."],
    )
