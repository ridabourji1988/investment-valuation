"""Full single-ticker analysis pipeline.

Takes an assembled `CompanyInputs` and runs the whole deterministic chain:
    beta -> CAPM -> WACC -> DCF -> reverse DCF -> Monte Carlo -> MoS
    -> quality (F/Z/M + composite) -> value-trap -> verdict.
Every metric carries its CalculationTrace so the frontend can render
"Show Calculation" for anything, including recursive drill-down.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict, replace

from . import beta as beta_mod
from . import capm as capm_mod
from . import wacc as wacc_mod
from . import dcf as dcf_mod
from . import reverse_dcf as rev_mod
from . import montecarlo as mc_mod
from . import screening as scr_mod
from . import quality as q_mod
from . import verdict as v_mod


@dataclass
class CompanyInputs:
    ticker: str
    name: str
    exchange: str
    sector: str
    price: float
    shares: float
    net_debt: float
    idea_category: str = "compounder"
    data_quality: str = "high"

    # beta / capm
    beta_unlevered: float = 1.0
    tax_rate: float = 0.25
    debt_to_equity: float = 0.3
    risk_free: float = 0.04
    erp: float = 0.045
    pretax_cost_of_debt: float = 0.05

    # dcf drivers
    revenue_base: float = 0.0
    ebit_margin_base: float = 0.15
    target_margin: float = 0.18
    growth_initial: float = 0.08
    growth_terminal: float = 0.025
    sales_to_capital: float = 2.0
    wacc_terminal: float = 0.08
    roic_stable: float | None = None

    # quality / forensics (optional; may be None if data is thin)
    quality: q_mod.QualityInputs | None = None
    piotroski: q_mod.PiotroskiInputs | None = None
    altman: q_mod.AltmanInputs | None = None
    beneish: q_mod.BeneishInputs | None = None
    trap: v_mod.ValueTrapInputs | None = None

    # screening extras
    ncav_current_assets: float = 0.0
    ncav_total_liabilities: float = 0.0
    magic_nwc: float = 0.0
    magic_nfa: float = 0.0

    sources: dict = field(default_factory=dict)
    links: dict = field(default_factory=dict)   # verify-at-source URLs
    asof: str = ""


def _market_cap(c: CompanyInputs) -> float:
    return c.price * c.shares


def analyze(c: CompanyInputs, *, mc_runs: int = 10_000, regime_reduce: float = 1.0) -> dict:
    traces: dict = {}

    # 1. Beta (relever sector unlevered beta at firm D/E)
    beta_t = beta_mod.relever_beta(c.beta_unlevered, c.tax_rate, c.debt_to_equity,
                                   sector=c.sector, asof=c.asof)
    traces["beta"] = beta_t

    # 2. Cost of equity (CAPM)
    re_t = capm_mod.cost_of_equity(c.risk_free, beta_t.result, c.erp, rf_asof=c.asof,
                                   beta_trace_id="beta")
    traces["cost_of_equity"] = re_t

    # 3. WACC
    equity = _market_cap(c)
    debt = c.debt_to_equity * equity  # market value of debt implied by D/E and market equity
    wacc_t = wacc_mod.wacc(equity, debt, re_t.result, c.pretax_cost_of_debt, c.tax_rate,
                           re_trace_id="cost_of_equity")
    traces["wacc"] = wacc_t

    # 4. DCF
    assumptions = dcf_mod.DCFAssumptions(
        revenue_base=c.revenue_base, ebit_margin_base=c.ebit_margin_base,
        target_margin=c.target_margin, growth_initial=c.growth_initial,
        growth_terminal=c.growth_terminal, sales_to_capital=c.sales_to_capital,
        wacc_initial=wacc_t.result, wacc_terminal=c.wacc_terminal, tax_rate=c.tax_rate,
        shares=c.shares, net_debt=c.net_debt, risk_free=c.risk_free, roic_stable=c.roic_stable,
    )
    dcf_t = dcf_mod.intrinsic_value(assumptions, price=c.price)
    traces["intrinsic_value"] = dcf_t
    fair_value = dcf_t.result

    # 5. Reverse DCF
    rev_t = rev_mod.implied_growth(assumptions, c.price)
    traces["implied_growth"] = rev_t

    # 6. Monte Carlo
    mc_t = mc_mod.simulate(assumptions, c.price, mc_mod.MCConfig(runs=mc_runs))
    traces["monte_carlo"] = mc_t
    p_v_gt_p = mc_t.result["prob_value_gt_price"]

    # 7. Margin of safety
    mos_t = scr_mod.margin_of_safety(fair_value, c.price, value_trace_id="intrinsic_value")
    traces["margin_of_safety"] = mos_t

    # 8. Enterprise value + magic formula + ncav
    ev = equity + c.net_debt
    ebit = c.revenue_base * c.ebit_margin_base
    magic_t = scr_mod.magic_formula(ebit, ev, c.magic_nwc, c.magic_nfa)
    traces["magic_formula"] = magic_t
    if c.ncav_current_assets:
        traces["ncav"] = scr_mod.ncav(c.ncav_current_assets, c.ncav_total_liabilities,
                                      c.shares, c.price)

    # 9. Quality & forensics
    if c.piotroski:
        traces["piotroski"] = q_mod.piotroski_f_score(c.piotroski)
    if c.altman:
        traces["altman"] = q_mod.altman_z_score(c.altman)
    if c.beneish:
        traces["beneish"] = q_mod.beneish_m_score(c.beneish)
    quality_score = 60.0
    if c.quality:
        # Inject the computed WACC via a copy — c.quality may be shared
        # provider state (get_company copies CompanyInputs shallowly), and
        # mutating it would pin the first-ever WACC across all later requests.
        q = c.quality
        if q.wacc == 0:
            q = replace(q, wacc=wacc_t.result)
        qc = q_mod.quality_composite(q)
        traces["quality"] = qc
        quality_score = qc.result["total"]

    # 10. Value-trap
    trap_flags = 0
    if c.trap:
        trap_t = v_mod.value_trap_check(c.trap)
        traces["value_trap"] = trap_t
        trap_flags = trap_t.result["flags"]

    # 11. Verdict
    # A decisive Monte Carlo probability (near 0 or 1) means the verdict is
    # stable across draws -> high confidence; a coin-flip p -> low confidence.
    mc_conf = abs(p_v_gt_p - 0.5) * 2.0
    verdict_t = v_mod.decide(v_mod.VerdictInputs(
        mos=mos_t.result, quality=quality_score, prob_value_gt_price=p_v_gt_p,
        trap_flags=trap_flags, idea_category=c.idea_category, mc_confidence=mc_conf,
    ), regime_reduce=regime_reduce)
    traces["verdict"] = verdict_t

    return {
        "ticker": c.ticker,
        "name": c.name,
        "exchange": c.exchange,
        "sector": c.sector,
        "price": c.price,
        "fair_value": fair_value,
        "margin_of_safety": mos_t.result,
        "quality": quality_score,
        "prob_value_gt_price": p_v_gt_p,
        "verdict": verdict_t.result,
        "monte_carlo": mc_t.result,
        "implied_growth": rev_t.result,
        "data_quality": c.data_quality,
        "idea_category": c.idea_category,
        "sources": c.sources,
        "links": c.links,
        "asof": c.asof,
        "dcf_assumptions": asdict(assumptions),
        "traces": {k: t.to_dict() for k, t in traces.items()},
    }
