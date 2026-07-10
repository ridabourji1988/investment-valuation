"""Registry integrity (PRD §5): CI fails if any formula lacks a citation, a
resolvable implementation, or a unit test against a worked example."""
import importlib
import os

from valuescope.registry import REGISTRY


def test_every_formula_has_citation_and_tests():
    for fid, spec in REGISTRY.items():
        assert spec.source_citation.strip(), f"{fid} missing citation"
        assert spec.tests, f"{fid} has no unit test referenced"


def test_implementation_refs_resolve():
    for fid, spec in REGISTRY.items():
        module_path, _, attr = spec.implementation_ref.partition(":")
        mod = importlib.import_module(module_path)
        assert hasattr(mod, attr), f"{fid}: cannot resolve {spec.implementation_ref}"


def test_referenced_test_files_exist():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for fid, spec in REGISTRY.items():
        for node in spec.tests:
            path = node.split("::")[0]
            assert os.path.exists(os.path.join(here, path)), f"{fid}: missing {path}"
