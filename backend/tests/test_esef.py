"""ESEF xBRL-JSON (OIM) -> EDGAR-companyfacts-shape adapter.

The adapter must produce exactly the structure edgar.annual_series /
monetary_series / _shares_from_eps consume, so the whole live.py assembly
(fallbacks, forensic scores, share identities) works on EU filings unchanged.
"""
import pytest

from valuescope.data import edgar, esef


def _fact(concept, value, period, unit=None, extra_dims=None):
    dims = {"concept": concept, "entity": "scheme:LEI123", "period": period}
    if unit:
        dims["unit"] = unit
    if extra_dims:
        dims.update(extra_dims)
    return {"value": value, "dimensions": dims}


OIM = {
    "facts": {
        "f1": _fact("ifrs-full:Revenue", "31459000000",
                    "2024-01-01T00:00:00/2025-01-01T00:00:00", "iso4217:EUR"),
        "f2": _fact("ifrs-full:Revenue", "30000000000",
                    "2023-01-01T00:00:00/2024-01-01T00:00:00", "iso4217:EUR"),
        # dimensioned (segment) fact -> must be dropped
        "f3": _fact("ifrs-full:Revenue", "99000000000",
                    "2024-01-01T00:00:00/2025-01-01T00:00:00", "iso4217:EUR",
                    {"ifrs-full:SegmentsAxis": "x:Wines"}),
        # balance-sheet instant: FY-end + 1 day midnight -> end 2024-12-31
        "f4": _fact("ifrs-full:CashAndCashEquivalents", "8500000000",
                    "2025-01-01T00:00:00", "iso4217:EUR"),
        # EPS in EUR/share and profit -> supports the shares-from-EPS identity
        "f5": _fact("ifrs-full:BasicEarningsLossPerShare", "10.0",
                    "2024-01-01T00:00:00/2025-01-01T00:00:00",
                    "iso4217:EUR/xbrli:shares"),
        "f6": _fact("ifrs-full:ProfitLossAttributableToOwnersOfParent", "5000000000",
                    "2024-01-01T00:00:00/2025-01-01T00:00:00", "iso4217:EUR"),
        # pure share count
        "f7": _fact("ifrs-full:NumberOfSharesOutstanding", "500000000",
                    "2025-01-01T00:00:00", "xbrli:shares"),
        # extension-taxonomy concept -> dropped (v1: ifrs-full only)
        "f8": _fact("lvmh:FancyCustomKPI", "42",
                    "2024-01-01T00:00:00/2025-01-01T00:00:00", "iso4217:EUR"),
        # language-dimension text fact -> ignored (non-numeric anyway)
        "f9": _fact("ifrs-full:NameOfUltimateParentOfGroup", "LVMH SE",
                    "2024-01-01T00:00:00/2025-01-01T00:00:00", None,
                    {"language": "en"}),
    }
}


@pytest.fixture()
def facts():
    out = {"facts": {}}
    esef.merge_oim(out, OIM, filed="2025-03-01")
    return out


def test_duration_period_maps_to_fiscal_year_end(facts):
    series, ccy = edgar.monetary_series(facts, ["Revenue"], flow=True)
    assert ccy == "EUR"
    assert series == [("2023-12-31", 30000000000.0), ("2024-12-31", 31459000000.0)]


def test_dimensioned_facts_are_dropped(facts):
    series, _ = edgar.monetary_series(facts, ["Revenue"], flow=True)
    assert all(v < 90e9 for _, v in series)


def test_instant_maps_to_prior_day(facts):
    series, ccy = edgar.monetary_series(facts, ["CashAndCashEquivalents"])
    assert series == [("2024-12-31", 8.5e9)] and ccy == "EUR"


def test_shares_direct_tag(facts):
    assert edgar.shares_outstanding(facts) == 500000000.0


def test_shares_from_eps_identity(facts):
    del facts["facts"]["ifrs-full"]["NumberOfSharesOutstanding"]
    assert edgar.shares_outstanding(facts) == pytest.approx(5e8)


def test_extension_namespace_dropped(facts):
    assert "lvmh" not in facts["facts"]
    assert "FancyCustomKPI" not in facts["facts"].get("ifrs-full", {})


def test_merge_prefers_latest_filed():
    out = {"facts": {}}
    esef.merge_oim(out, OIM, filed="2025-03-01")
    amended = {"facts": {"a1": _fact(
        "ifrs-full:Revenue", "31500000000",
        "2024-01-01T00:00:00/2025-01-01T00:00:00", "iso4217:EUR")}}
    esef.merge_oim(out, amended, filed="2025-06-01")
    series, _ = edgar.monetary_series(out, ["Revenue"], flow=True)
    assert series[-1] == ("2024-12-31", 31.5e9)


def test_registry_is_sane():
    assert len(esef.REGISTRY) >= 10
    for ticker, meta in esef.REGISTRY.items():
        assert ticker == ticker.upper() and "." in ticker
        assert len(meta["lei"]) == 20
        assert meta["name"] and meta["sector"] and meta["exchange"]
