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
            for v in x.values():
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)
        elif isinstance(x, str):
            m = _to_float(x)
            if m is not None:
                nums.add(round(m, 6))

    walk(obj)
    # Also add common derived representations (percent<->decimal) for tolerance.
    expanded = set(nums)
    for n in nums:
        expanded.add(round(n * 100.0, 6))
        expanded.add(round(n / 100.0, 6))
    return expanded


def _matches_any(value: float, allowed: set[float], rel_tol: float = 0.02) -> bool:
    for a in allowed:
        tol = max(abs(a) * rel_tol, 0.01)
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
        if not _matches_any(v, allowed) and not _matches_any(v * 100, allowed) \
           and not _matches_any(v / 100, allowed):
            unverified.append(tok.strip())
    jargon = [w for w in BANNED_JARGON if w.lower() in text.lower()]
    return {"ok": not unverified and not jargon, "unverified": unverified, "jargon": jargon}
