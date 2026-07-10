"""CalculationTrace — the reproducible record behind every number (PRD §5).

Every metric the engine emits carries a trace so the frontend can render the
"Show Calculation" sheet: formula -> inputs (with sources) -> substitution
steps -> result -> citation -> caveats. The frontend NEVER re-computes; it only
renders these traces.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from .. import ENGINE_VERSION


@dataclass
class Input:
    """A single named input to a calculation."""

    name: str
    value: Any
    unit: str = ""
    source_type: str = "computed"  # edgar | fred | damodaran | yfinance | formula | assumption | constant
    source_ref: str = ""
    asof: str = ""
    trace_id: Optional[str] = None  # link to another metric's trace (recursive drill-down)


@dataclass
class Step:
    """One line of the worked substitution."""

    label: str
    expression: str
    value: Any


@dataclass
class CalculationTrace:
    """The full, storable record for a computed metric."""

    metric_id: str
    formula_id: str
    formula_version: str
    result: Any
    unit: str = ""
    inputs: list[Input] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    citation: str = ""
    caveats: list[str] = field(default_factory=list)
    plain: str = ""  # "What this means" one-liner
    computed_at: str = ""  # stamped by caller/API (engine has no clock, keeps it pure)
    engine_version: str = ENGINE_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


def inp(name, value, unit="", source_type="computed", source_ref="", asof="", trace_id=None) -> Input:
    return Input(name, value, unit, source_type, source_ref, asof, trace_id)


def step(label, expression, value) -> Step:
    return Step(label, expression, value)
