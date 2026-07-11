"""Runtime configuration from environment variables.

Everything has a working default — the system is fully autonomous with zero
configuration. Env vars only *override*.
"""
from __future__ import annotations

import os


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# Default scan universe: US megacaps + European and emerging-market leaders
# via their US listings (ADRs file 20-F/40-F with the SEC, so the same XBRL
# pipeline covers them; IFRS statements are converted to US$ at spot).
# Banks are excluded (no operating-income line; an FCFF model doesn't apply).
# Any other SEC filer is analyzable on demand through search.
# Override with VALUESCOPE_UNIVERSE="AAPL,MSFT,...".
DEFAULT_UNIVERSE = [
    # US
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "JNJ", "PG", "WMT", "KO", "HD", "CVX",
    # Europe (ADRs)
    "SAP", "ASML", "SHEL", "NVO",
    # Emerging markets / Asia (ADRs)
    "TSM", "BABA", "VALE", "INFY",
]


class Config:
    # Data
    SEC_UA: str = os.getenv("VALUESCOPE_SEC_UA", "ValueScope research contact@example.com")
    UNIVERSE: list = [t.strip().upper() for t in
                      os.getenv("VALUESCOPE_UNIVERSE", ",".join(DEFAULT_UNIVERSE)).split(",")
                      if t.strip()]

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
