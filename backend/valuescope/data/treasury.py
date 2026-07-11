"""Official US Treasury daily yield curve — keyless, authoritative.

home.treasury.gov publishes the daily par yield curve as an Atom/XML feed with
no API key. It sits between FRED (same numbers, richer history) and Yahoo's
^TNX/^IRX tickers in the rate fallback chain: when FRED is unreachable this is
the primary source, not a proxy.
"""
from __future__ import annotations

import datetime as _dt
import re

from .cache import get_cached, http_get

_URL = ("https://home.treasury.gov/resource-center/data-chart-center/"
        "interest-rates/pages/xml")
_TTL = 3600


def _latest_curve() -> dict:
    """{"date": iso, "y10": decimal, "m3": decimal} from the newest entry."""
    def build():
        year = _dt.date.today().year
        r = http_get(_URL, params={"data": "daily_treasury_yield_curve",
                                   "field_tdr_date_value": str(year)},
                     timeout=20, retries=1)
        text = r.text
        # Entries are chronological; the last NEW_DATE block is the newest day.
        dates = re.findall(r"<d:NEW_DATE[^>]*>([\d-]+)T", text)
        y10s = re.findall(r"<d:BC_10YEAR[^>]*>([\d.]+)<", text)
        m3s = re.findall(r"<d:BC_3MONTH[^>]*>([\d.]+)<", text)
        if not (dates and y10s and m3s):
            raise ValueError("Treasury yield-curve feed returned no entries")
        return {"date": dates[-1], "y10": float(y10s[-1]) / 100.0,
                "m3": float(m3s[-1]) / 100.0}
    return get_cached("treasury:daily_curve", _TTL, build)


def yield_10y() -> float:
    return _latest_curve()["y10"]


def yield_3m() -> float:
    return _latest_curve()["m3"]
