"""AI guardrails (PRD §4).

The AI narrates deterministic numbers; it must not invent figures. The
validator extracts every number from the generated text and checks each one
appears (within tolerance) among the numbers present in the structured input
JSON that was handed to the model. Numbers that don't reconcile are flagged.
"""
from __future__ import annotations

import re

# Matches integers/decimals with optional %, $, commas, and sign.
_NUM_RE = re.compile(r"[-+−]?\$?\s?\d[\d,]*\.?\d*\s?%?")

BANNED_JARGON = [
    "idiosyncratic", "systematic risk", "heteroskedastic", "stochastic",
    "convexity", "alpha generation", "risk-adjusted basis", "beta-adjusted",
]


def _to_float(token: str) -> float | None:
    t = token.strip().replace("−", "-").replace("$", "").replace(",", "").replace(" ", "")
    is_pct = t.endswith("%")
    t = t.rstrip("%")
    try:
        v = float(t)
    except ValueError:
        return None
    return v / 100.0 if is_pct else v


def collect_numbers(obj) -> set[float]:
    """Recursively collect every numeric value from a JSON-like structure."""
    nums: set[float] = set()

    def walk(x):
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)):
            nums.add(round(float(x), 6))
        elif isinstance(x, dict):
            for k, v in x.items():
                # Keys are part of what the model sees — "p50", "plus_50bp"
                # license narrating "P50" or "±50bp".
                if isinstance(k, str):
                    walk(k)
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)
        elif isinstance(x, str):
            # Extract every numeric token, not just whole-string floats —
            # engine strings like the sizing line ("≈ 15% … (~1,500 US$)")
            # legitimately carry numbers the narrative may restate.
            for tok in _NUM_RE.findall(x):
                m = _to_float(tok)
                if m is not None:
                    nums.add(round(m, 6))

    walk(obj)
    # Also add common restatements: percent<->decimal, and millions/billions/
    # trillions for large figures ("416,161,000,000" is naturally narrated
    # as "416.2 billion" or "$416.2B").
    expanded = set(nums)
    for n in nums:
        expanded.add(round(n * 100.0, 6))
        expanded.add(round(n / 100.0, 6))
        if abs(n) >= 1e6:
            expanded.add(round(n / 1e6, 6))
            expanded.add(round(n / 1e9, 6))
            expanded.add(round(n / 1e12, 6))
    return expanded


def _matches_any(value: float, allowed: set[float], rel_tol: float = 0.02) -> bool:
    # 2% relative tolerance absorbs narrative rounding ("9.3%" for 0.0929);
    # the tiny absolute floor only covers exact-zero comparisons. A generous
    # floor here would let misstated small rates (e.g. 3.4% vs 2.5%) through.
    for a in allowed:
        tol = max(abs(a) * rel_tol, 0.001)
        if abs(value - a) <= tol:
            return True
    return False


def validate_numbers(text: str, allowed_source: object) -> dict:
    """Return {ok, unverified:[...], jargon:[...]} for a generated narrative."""
    allowed = collect_numbers(allowed_source)
    # Whitelist small ordinals/years that are narrative scaffolding, not claims.
    scaffolding = {round(float(y), 6) for y in range(1, 13)} | {
        round(float(y), 6) for y in range(2015, 2036)
    }
    unverified = []
    for tok in _NUM_RE.findall(text):
        v = _to_float(tok)
        if v is None:
            continue
        rv = round(v, 6)
        if rv in scaffolding:
            continue
        # collect_numbers already expands allowed values ×100 and ÷100 for
        # percent<->decimal, so a single comparison suffices — re-converting
        # here too would square the tolerance surface.
        if not _matches_any(v, allowed):
            unverified.append(tok.strip())
    jargon = [w for w in BANNED_JARGON if w.lower() in text.lower()]
    return {"ok": not unverified and not jargon, "unverified": unverified, "jargon": jargon}
