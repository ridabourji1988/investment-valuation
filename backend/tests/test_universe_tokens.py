"""Universe expansion tokens (SP500 / EU) and the constituents parser."""
import pytest

from valuescope.config import DEFAULT_UNIVERSE, config
from valuescope.data import indexes, provider

_HTML = """
<table id="constituents">
<tr><th>Symbol</th><th>Security</th><th>GICS Sector</th></tr>
<tr><td><a href="/x">AAPL</a></td><td><a>Apple</a></td><td>Information Technology</td><td>x</td></tr>
<tr><td><a href="/x">BRK.B</a></td><td><a>Berkshire</a></td><td>Financials</td><td>x</td></tr>
<tr><td><a href="/x">PLD</a></td><td><a>Prologis</a></td><td>Real Estate</td><td>x</td></tr>
<tr><td><a href="/x">BF.B</a></td><td><a>Brown-Forman</a></td><td>Consumer Staples</td><td>x</td></tr>
</table>
"""


def test_parser_extracts_and_normalizes_class_shares():
    rows = indexes.parse_constituents(_HTML)
    assert ("AAPL", "Information Technology") in rows
    assert ("BRK-B", "Financials") in rows   # dot -> dash
    assert ("BF-B", "Consumer Staples") in rows


def test_sp500_token_expands_and_dedupes(monkeypatch):
    monkeypatch.setattr(config, "UNIVERSE", ["SP500", "AAPL", "TM"])
    monkeypatch.setattr(indexes, "sp500_tickers", lambda: ["AAPL", "MSFT"])
    assert provider.list_tickers() == ["AAPL", "MSFT", "TM"]


def test_sp500_failure_falls_back_to_default(monkeypatch):
    monkeypatch.setattr(config, "UNIVERSE", ["SP500"])
    monkeypatch.setattr(indexes, "sp500_tickers",
                        lambda: (_ for _ in ()).throw(RuntimeError("down")))
    out = provider.list_tickers()
    assert out == DEFAULT_UNIVERSE


def test_eu_token_selects_suffixed_names(monkeypatch):
    monkeypatch.setattr(config, "UNIVERSE", ["EU"])
    out = provider.list_tickers()
    assert out and all("." in t for t in out)
    assert "MC.PA" in out


def test_financials_and_real_estate_excluded():
    rows = indexes.parse_constituents(_HTML)
    kept = [t for t, s in rows if s not in ("Financials", "Real Estate")]
    assert "BRK-B" not in kept and "PLD" not in kept and "AAPL" in kept


def test_nasdaq100_token_uses_nasdaq_list(monkeypatch):
    monkeypatch.setattr(config, "UNIVERSE", ["NASDAQ100"])
    monkeypatch.setattr(indexes, "nasdaq100_tickers", lambda: ["AAPL", "NVDA"])
    assert provider.list_tickers() == ["AAPL", "NVDA"]


def test_cac40_token_is_fully_analyzable(monkeypatch):
    from valuescope.data import esef
    monkeypatch.setattr(config, "UNIVERSE", ["CAC40"])
    out = provider.list_tickers()
    assert out == indexes.CAC40
    for t in out:
        # every EU-suffixed member must be in the ESEF registry; the rest
        # are US-listed ADR symbols (plain tickers)
        if "." in t:
            assert t in esef.REGISTRY, t
