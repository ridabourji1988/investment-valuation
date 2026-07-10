from fastapi.testclient import TestClient

from valuescope.api.app import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_feed_ranked_by_margin_of_safety():
    r = client.get("/api/feed").json()
    mos = [row["margin_of_safety"] for row in r["rows"]]
    assert mos == sorted(mos, reverse=True)
    assert r["count"] == len(r["rows"]) > 0


def test_asset_has_all_traces():
    a = client.get("/api/asset/NVSC").json()
    for key in ("beta", "cost_of_equity", "wacc", "intrinsic_value", "monte_carlo",
                "margin_of_safety", "verdict", "quality"):
        assert key in a["traces"], key
    assert a["traces"]["intrinsic_value"]["citation"]


def test_calc_endpoint_returns_trace():
    t = client.get("/api/asset/NVSC/calc/intrinsic_value").json()
    assert t["result"] > 0
    assert len(t["steps"]) == 16
    assert t["formula_id"] == "intrinsic_value_fcff"


def test_rate_sensitivity_base_matches_fair_value():
    a = client.get("/api/asset/RAIL").json()
    rs = client.get("/api/macro/rate-sensitivity").json()
    row = next(r for r in rs["rows"] if r["ticker"] == "RAIL")
    assert abs(row["base"] - a["fair_value"]) < 1e-6
    assert row["plus_50bp"] < row["base"] < row["minus_50bp"]


def test_unknown_ticker_404():
    assert client.get("/api/asset/ZZZZ").status_code == 404


def test_formulas_all_cited():
    fm = client.get("/api/formulas").json()["formulas"]
    assert len(fm) >= 18
    assert all(f["citation"] for f in fm)
