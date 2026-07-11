"""Narrator — turns engine output into AI explanations, with guardrails and a
deterministic fallback so the app always renders something truthful.

Blocks are cached content-addressed: decoding is greedy (temperature 0), so a
block is fully determined by (model, prompt kind, facts). Reopening an asset
whose numbers haven't changed serves the cached text instantly — no repeated
AI calls; when the engine numbers change, the digest changes and the block
regenerates so the story always matches the sheet.
"""
from __future__ import annotations

import hashlib
import json

from ..config import config
from ..data.cache import get_cached
from . import prompts
from .guardrails import validate_numbers
from . import openrouter

_AI_TTL = 7 * 24 * 3600  # the digest, not the clock, is what invalidates


def _cached_block(kind: str, facts: object, generate, fallback_fn) -> dict:
    """Serve the block from cache when (model, kind, facts) is unchanged.
    Deterministic fallbacks (AI off, guardrail trip, provider error) are never
    cached, so AI recovery is picked up on the next view."""
    digest = hashlib.sha256(
        json.dumps([config.OPENROUTER_MODEL, kind, facts],
                   sort_keys=True, default=str).encode()).hexdigest()[:20]
    holder: dict = {}

    def build():
        block = _finalize(generate(), fallback_fn)
        if not block.get("ai"):
            holder["fallback"] = block
            raise RuntimeError("fallback — not cached")
        return block

    try:
        return get_cached(f"ai:block:{digest}", _AI_TTL, build)
    except Exception:  # noqa: BLE001 — serve the uncached fallback
        return holder.get("fallback") or _finalize({"text": None}, fallback_fn)


def _fmt_pct(x: float) -> str:
    return f"{x*100:.1f}%"


def _generate(system: str, user: str, allowed: object) -> dict:
    """Call the model, validate numbers, and report provenance/usage."""
    if not config.ai_ready():
        return {"text": None, "source": "unavailable", "usage": None, "guardrail": None}
    try:
        res = openrouter.chat(system, user)  # max_tokens from config (default 20000)
    except Exception as e:  # noqa: BLE001
        return {"text": None, "source": f"error: {e}", "usage": None, "guardrail": None}
    guard = validate_numbers(res["text"], allowed)
    return {
        "text": res["text"],
        "source": f"GLM via {res.get('provider') or config.OPENROUTER_PROVIDER}",
        "usage": res["usage"],
        "guardrail": guard,
    }


# --------------------------------------------------------------------------- #
# Deterministic fallbacks (used when AI is disabled or a guardrail trips).
# --------------------------------------------------------------------------- #
def _fallback_valuation(a: dict) -> str:
    gap = "below" if a["price"] < a["fair_value"] else "above"
    return (f"{a['name']} trades at {a['price']:,.2f} US$, {gap} its estimated fair value of "
            f"{a['fair_value']:,.2f} US$. That is a margin of safety of "
            f"{_fmt_pct(a['margin_of_safety'])}. The estimate assumes revenue grows about "
            f"{_fmt_pct(a['growth_initial'])} a year at first, fading toward "
            f"{_fmt_pct(a['growth_terminal'])}, with a discount rate (WACC) near "
            f"{_fmt_pct(a['wacc'])}. Most of the value sits in the later years, so the answer "
            f"is sensitive to those assumptions.")


def _fallback_memo(a: dict) -> str:
    v = a["verdict"]
    reasons = " ".join(v.get("reasons", []))
    return (f"{a['name']} ({a['ticker']}) — verdict: {v['action']} (confidence {v['confidence']}). "
            f"The share price is {a['price']:,.2f} US$ against an estimated fair value of "
            f"{a['fair_value']:,.2f} US$, a margin of safety of {_fmt_pct(a['margin_of_safety'])}. "
            f"Business quality scores {a['quality']:.0f} out of 100. In a Monte Carlo simulation "
            f"the stock looked undervalued in {_fmt_pct(a['prob_value_gt_price'])} of runs. "
            f"Rules that fired: {reasons} Suggested position: {v['sizing']} Horizon: {v['horizon']}. "
            f"Watch these sell triggers: price rising above 1.1x fair value; the margin of safety "
            f"turning negative; or business quality dropping below 60. This is an educational "
            f"estimate, not advice.")


def narrate_asset(analysis: dict, *, want: tuple = ("business", "valuation", "memo")) -> dict:
    """Produce the AI blocks for an Asset 360 view."""
    a = analysis
    # Compact, number-only payload handed to the model (and to the validator).
    payload = {
        "ticker": a["ticker"], "name": a["name"], "sector": a["sector"],
        "price": round(a["price"], 2), "fair_value": round(a["fair_value"], 2),
        "margin_of_safety": round(a["margin_of_safety"], 4),
        "quality": round(a["quality"], 1),
        "prob_value_gt_price": round(a["prob_value_gt_price"], 3),
        "implied_growth": round(a["implied_growth"], 4),
        "growth_initial": round(_input(a, "intrinsic_value", "Growth (yrs 1-5)"), 4),
        "growth_terminal": round(_input(a, "intrinsic_value", "Terminal growth"), 4),
        "wacc": round(a["traces"]["wacc"]["result"], 4),
        "verdict": a["verdict"],
        "monte_carlo": {k: round(v, 2) if isinstance(v, (int, float)) else v
                        for k, v in a["monte_carlo"].items()},
        # Versioned house-rule thresholds (verdict_rules v1). Including them
        # here both lets the model cite them and whitelists them for the
        # number-validator guardrail — derived arithmetic stays banned.
        "rules": {"buy_mos_min": 0.25, "buy_quality_min": 60,
                  "buy_prob_min": 0.70, "buy_trap_flags_max": 2,
                  "sell_price_to_value": 1.1, "sell_trap_flags_min": 4},
    }

    out: dict = {"payload": payload, "blocks": {}}

    if "business" in want:
        facts = {
            "name": a["name"], "ticker": a["ticker"], "sector": a["sector"],
            "exchange": a["exchange"],
            "revenue_ttm_usd": round(_input(a, "intrinsic_value", "Revenue₀"), 0),
            "operating_margin": round(_input(a, "intrinsic_value", "Operating margin₀"), 4),
        }
        out["blocks"]["business"] = _cached_block(
            "business", facts,
            lambda: _generate(prompts.SYSTEM_PROMPT,
                              prompts.business_description(a["name"], a["sector"], facts),
                              facts),
            lambda: f"{a['name']} ({a['ticker']}) operates in the {a['sector']} sector "
                    f"and is listed on {a['exchange']}.")
    if "valuation" in want:
        out["blocks"]["valuation"] = _cached_block(
            "valuation", payload,
            lambda: _generate(prompts.SYSTEM_PROMPT,
                              prompts.valuation_narrative(payload), payload),
            lambda: _fallback_valuation(payload))
    if "memo" in want:
        out["blocks"]["memo"] = _cached_block(
            "memo", payload,
            lambda: _generate(prompts.SYSTEM_PROMPT, prompts.verdict_memo(payload), payload),
            lambda: _fallback_memo(payload))
    return out


def narrate_brief(scan: dict) -> dict:
    payload = {
        "ideas": scan.get("count"), "buys": scan.get("buys"),
        "regime": scan.get("regime"),
        "top": [{"ticker": t["ticker"], "margin_of_safety": round(t["margin_of_safety"], 3)}
                for t in scan.get("top", [])],
    }
    def fallback():
        return (f"Today's scan surfaced {payload['ideas']} ideas, {payload['buys']} rated Buy. "
                f"The macro regime reads '{payload['regime']}'. "
                + (f"Standouts include {payload['top'][0]['ticker']} at "
                   f"{_fmt_pct(payload['top'][0]['margin_of_safety'])} margin of safety."
                   if payload["top"] else ""))
    block = _cached_block(
        "brief", payload,
        lambda: _generate(prompts.SYSTEM_PROMPT, prompts.market_brief(payload), payload),
        fallback)
    return {"payload": payload, "block": block}


def _finalize(gen: dict, fallback_fn) -> dict:
    """Prefer the AI text when it passes guardrails; otherwise use the fallback."""
    if gen.get("text") and (gen.get("guardrail") or {}).get("ok"):
        return {"text": gen["text"], "source": gen["source"], "usage": gen["usage"],
                "guardrail": gen["guardrail"], "ai": True}
    return {"text": fallback_fn(), "source": "ValueScope engine (deterministic)",
            "usage": gen.get("usage"), "guardrail": gen.get("guardrail"),
            "ai": False, "ai_source": gen.get("source")}


def _input(analysis: dict, trace_key: str, input_name: str) -> float:
    for i in analysis["traces"][trace_key]["inputs"]:
        if i["name"] == input_name:
            return i["value"]
    return 0.0
