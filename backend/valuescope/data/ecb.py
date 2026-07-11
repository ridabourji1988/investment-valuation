"""ECB Data Portal — euro-area risk-free rate, keyless.

EUR-denominated cash flows must be discounted with a EUR risk-free rate
(Damodaran: currency consistency — inflation expectations differ per
currency, and the US 10y embeds dollar inflation). The ECB publishes a
daily AAA-rated euro-area government yield curve; the 10y spot rate is the
EUR analogue of the US Treasury 10y used everywhere else in the app.
"""
from __future__ import annotations

from .cache import get_cached, http_get

# Daily AAA euro-area government bond spot curve, 10-year maturity.
_URL = ("https://data-api.ecb.europa.eu/service/data/YC/"
        "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y"
        "?lastNObservations=1&format=jsondata")
_TTL = 12 * 3600


def yield_10y() -> float:
    """Euro-area AAA 10y government yield as a decimal (e.g. 0.0313)."""
    def build():
        d = http_get(_URL, headers={"Accept": "application/json"}, timeout=30).json()
        series = d["dataSets"][0]["series"]
        obs = next(iter(series.values()))["observations"]
        value = next(iter(obs.values()))[0]
        return float(value) / 100.0
    return get_cached("ecb:yield10y", _TTL, build)
