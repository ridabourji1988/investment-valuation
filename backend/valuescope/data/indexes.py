"""Index membership lists — universe expansion tokens, keyless.

`VALUESCOPE_UNIVERSE=SP500` (or "SP500,MC.PA,...") expands to the current
S&P 500 constituents. Financials and real estate are excluded for the same
reason banks are excluded from the default universe: an FCFF DCF misvalues
balance-sheet businesses (debt is their raw material — Damodaran); they need
a dedicated equity model before they can be shown honestly.

Membership comes from the Wikipedia constituents table (kept current by
editors within days of index changes; this is a reference list, not market
data — prices/fundamentals still come only from primary sources).
"""
from __future__ import annotations

import re

from .cache import get_cached, http_get

_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
_TTL = 7 * 24 * 3600

_EXCLUDED_SECTORS = ("Financials", "Real Estate")


def parse_constituents(html: str) -> list[tuple[str, str]]:
    """[(ticker, gics_sector), ...] from the first wikitable. Row shape:
    <tr><td><a ...>SYM</a></td><td><a>Name</a></td><td>Sector</td>..."""
    table = html.split('id="constituents"', 1)[-1]
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table, flags=re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S)
        if len(cells) < 3:
            continue
        sym = re.sub(r"<[^>]+>", "", cells[0]).strip()
        sector = re.sub(r"<[^>]+>", "", cells[2]).strip()
        if not re.fullmatch(r"[A-Z]{1,6}([.-][A-Z])?", sym):
            continue
        # EDGAR/Yahoo/Cboe use dashes for share classes (BRK.B -> BRK-B);
        # dots are reserved for EU venue suffixes in this app.
        out.append((sym.replace(".", "-"), sector))
    return out


def sp500_tickers() -> list[str]:
    """Current S&P 500 ex-financials/real-estate, cached a week."""
    def build():
        html = http_get(_URL, headers={"User-Agent":
                        "ValueScope research contact@example.com"},
                        timeout=30).text
        rows = parse_constituents(html)
        if len(rows) < 400:  # sanity: page layout changed?
            raise ValueError(f"S&P 500 parse found only {len(rows)} rows")
        return [t for t, sector in rows if sector not in _EXCLUDED_SECTORS]
    return get_cached("indexes:sp500", _TTL, build)
