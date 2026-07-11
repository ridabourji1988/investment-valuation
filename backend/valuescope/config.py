"""Runtime configuration from environment variables.

Everything has a working default — the system is fully autonomous with zero
configuration. Env vars only *override*.
"""
from __future__ import annotations

import os


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _universe() -> list:
    """Parse VALUESCOPE_UNIVERSE, dropping tokens that cannot be tickers.

    A misplaced value (e.g. "10000" intended for VALUESCOPE_MC_RUNS) must not
    blank the whole app — anything with no letters is discarded, and an empty
    result falls back to the curated default.
    """
    raw = os.getenv("VALUESCOPE_UNIVERSE", "")
    tickers = [t.strip().upper() for t in raw.split(",") if t.strip()]
    valid = [t for t in tickers
             if any(c.isalpha() for c in t)
             and all(c.isalnum() or c in ".-" for c in t) and len(t) <= 8]
    dropped = [t for t in tickers if t not in valid]
    if dropped:
        print(f"WARNING: ignoring invalid VALUESCOPE_UNIVERSE entries {dropped} "
              f"(not ticker symbols){' — using default universe' if not valid else ''}")
    return valid or list(DEFAULT_UNIVERSE)


# Default scan universe: US megacaps + European and emerging-market leaders
# via their US listings (ADRs file 20-F/40-F with the SEC, so the same XBRL
# pipeline covers them; IFRS statements are converted to US$ at spot).
# Banks are excluded (no operating-income line; an FCFF model doesn't apply).
# Any other SEC filer is analyzable on demand through search.
# Curated default scan universe (~90 names). Every entry is an SEC filer with
# usable XBRL and a US$ listing. Banks/insurers are deliberately excluded: an
# FCFF DCF misvalues financials (debt is their raw material — Damodaran); they
# need a dedicated equity model before they can be shown honestly.
# Override with VALUESCOPE_UNIVERSE=comma,separated,tickers.
DEFAULT_UNIVERSE = [
    # US — technology & communication
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "ORCL",
    "CRM", "ADBE", "AMD", "INTC", "QCOM", "TXN", "CSCO", "IBM", "NOW",
    "INTU", "NFLX", "DIS", "UBER", "BKNG", "PYPL",
    # US — health care
    "JNJ", "LLY", "ABBV", "MRK", "PFE", "TMO", "ABT", "AMGN", "GILD", "BMY",
    # US — consumer & staples
    "PG", "KO", "PEP", "COST", "WMT", "HD", "MCD", "NKE", "SBUX", "LOW",
    "TGT", "PM", "MO", "CL",
    # US — industrials, energy, materials, utilities
    "CAT", "DE", "HON", "GE", "UNP", "UPS", "LMT", "RTX", "CVX", "COP",
    "SLB", "LIN", "FCX", "NEM", "NEE",
    # Europe (ADRs, 20-F filers)
    "SAP", "ASML", "SHEL", "NVO", "AZN", "NVS", "GSK", "SNY", "TTE", "BP",
    "RIO", "DEO", "BTI", "ERIC", "NOK", "UL",
    # Asia (ADRs / 20-F). Toyota (TM) is excluded like the banks: its captive
    # finance arm carries so much debt that an FCFF DCF misvalues the equity.
    "TSM", "BABA", "INFY", "SONY", "SE", "BIDU", "JD", "PDD", "NTES",
    "TCOM",
    # Latin America / Australia
    "VALE", "PBR", "MELI", "BHP",
]


class Config:
    # Data
    SEC_UA: str = os.getenv("VALUESCOPE_SEC_UA", "ValueScope research contact@example.com")
    UNIVERSE: list = _universe()
    # Optional last-resort market-data key (free tier ~25 req/day). The
    # keyless chain (Yahoo -> Cboe, er-api/ECB) carries everything without it.
    ALPHAVANTAGE_API_KEY: str = os.getenv("ALPHAVANTAGE_API_KEY", "")

    # AI (OpenRouter)
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "z-ai/glm-5.2")
    # OpenRouter provider routing slug (see /api/v1/providers): StreamLake = "streamlake".
    OPENROUTER_PROVIDER: str = os.getenv("OPENROUTER_PROVIDER", "streamlake")
    OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    OPENROUTER_MAX_TOKENS: int = int(os.getenv("OPENROUTER_MAX_TOKENS", "20000"))
    # 0 = greedy decoding — narration must restate engine numbers verbatim.
    OPENROUTER_TEMPERATURE: float = float(os.getenv("OPENROUTER_TEMPERATURE", "0"))
    AI_ENABLED: bool = _bool("VALUESCOPE_AI_ENABLED", True)

    # Monte Carlo
    MC_RUNS: int = int(os.getenv("VALUESCOPE_MC_RUNS", "10000"))

    # Server
    PORT: int = int(os.getenv("PORT", "8000"))

    @classmethod
    def ai_ready(cls) -> bool:
        return cls.AI_ENABLED and bool(cls.OPENROUTER_API_KEY)


config = Config()
