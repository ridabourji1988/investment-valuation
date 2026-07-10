"""Formula Registry loader (PRD §5).

The YAML file is the single source of truth. Each entry maps a formula_id to
its symbolic expression, variable glossary, canonical citation, implementation
reference and the test(s) that reproduce a worked example from the source.
"""
from __future__ import annotations

import functools
import os
from dataclasses import dataclass

import yaml

_HERE = os.path.dirname(__file__)
FORMULAS_PATH = os.path.join(_HERE, "formulas.yaml")

FORMULA_VERSION = "1.0.0"


@dataclass(frozen=True)
class FormulaSpec:
    formula_id: str
    name: str
    expression: str
    variables: dict
    source_citation: str
    implementation_ref: str
    tests: list
    version: str = FORMULA_VERSION


@functools.lru_cache(maxsize=1)
def load_registry(path: str = FORMULAS_PATH) -> dict[str, FormulaSpec]:
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    specs: dict[str, FormulaSpec] = {}
    for fid, body in raw.items():
        specs[fid] = FormulaSpec(
            formula_id=fid,
            name=body["name"],
            expression=body["expression"],
            variables=body.get("variables", {}),
            source_citation=body["source_citation"],
            implementation_ref=body["implementation_ref"],
            tests=body.get("tests", []),
        )
    return specs


REGISTRY = load_registry()


def get_formula(formula_id: str) -> FormulaSpec:
    reg = load_registry()
    if formula_id not in reg:
        raise KeyError(f"Unknown formula_id '{formula_id}'. Registered: {sorted(reg)}")
    return reg[formula_id]
