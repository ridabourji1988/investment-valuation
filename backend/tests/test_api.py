"""API contract tests — offline: the provider is monkeypatched with fixtures
so no network is touched. Production data flow (EDGAR/Yahoo/FRED) is exercised
by scripts/live_check.py instead."""
import pytest
from fastapi.testclient import TestClient

from valuescope.api import service
from valuescope.api.app import app
from valuescope.data import provider
from tests import fixtures

client = TestClient(app)

TICKERS = ["TSTA", "TSTB"]


@pytest.fixture(autouse=True)
def offline_provider(monkeypatch):
    companies = {
        "TSTA": fixtures.make_company("TSTA", "Test Alpha", price=88.0),
        "TSTB": fixtures.make_company("TSTB", "Test Beta", price=300.0, revenue=20e9,
                                      margin=0.18, growth=0.05, net_debt=5e9),
    }
    monkeypatch.setattr(provider, "list_tickers", lambda: list(TICKERS))
    monkeypatch.setattr(provider, "get_company", lambda t: companies[t.upper()])
    monkeypatch.setattr(provider, "get_price_history",
                        lambda t: fixtures.make_price_history(companies[t.upper()].price))
    monkeypatch.setattr(provider, "get_macro", fixtures.make_macro)
    service.reset_for_tests()
    # Pre-warm synchronously so feed() has rows without racing the warm thread.
    for t in TICKERS:
        service.analyze_ticker(t)
        service._WARM["attempted"].add(t)
    yield
    service.reset_for_tests()


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert set(body["data"]["universe"]) == set(TICKERS)


def test_feed_ranked_by_margin_of_safety():
    r = client.get("/api/feed").json()
    mos = [row["margin_of_safety"] for row in r["rows"]]
    assert mos == sorted(mos, reverse=True)
    assert r["count"] == len(r["rows"]) == len(TICKERS)
    assert r["warming"] is False


def test_asset_has_all_traces():
    a = client.get("/api/asset/TSTA").json()
    for key in ("beta", "cost_of_equity", "wacc", "intrinsic_value", "monte_carlo",
                "margin_of_safety", "verdict", "quality"):
        assert key in a["traces"], key
    assert a["traces"]["intrinsic_value"]["citation"]


def test_calc_endpoint_returns_trace():
    t = client.get("/api/asset/TSTA/calc/intrinsic_value").json()
    assert t["result"] > 0
    assert len(t["steps"]) == 16
    assert t["formula_id"] == "intrinsic_value_fcff"


def test_rate_sensitivity_base_matches_fair_value():
    a = client.get("/api/asset/TSTB").json()
    rs = client.get("/api/macro/rate-sensitivity").json()
    row = next(r for r in rs["rows"] if r["ticker"] == "TSTB")
    assert abs(row["base"] - a["fair_value"]) < 1e-6
    assert row["plus_50bp"] < row["base"] < row["minus_50bp"]


def test_macro_dashboard_regime_and_sahm():
    m = client.get("/api/macro").json()
    assert m["regime"]["result"]["label"]
    assert m["sahm"]["result"]["triggered"] in (True, False)
    ids = {i["id"] for i in m["indicators"]}
    assert {"DGS10", "T10Y3M", "IPMAN", "HYOAS", "UNRATE", "CPI"} <= ids


def test_unknown_ticker_404():
    assert client.get("/api/asset/ZZZZ").status_code == 404


def test_formulas_all_cited():
    fm = client.get("/api/formulas").json()["formulas"]
    assert len(fm) >= 18
    assert all(f["citation"] for f in fm)
