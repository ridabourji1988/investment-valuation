"""Runtime configuration from environment variables."""
from __future__ import annotations

import os


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class Config:
    # Data
    LIVE_DATA: bool = _bool("VALUESCOPE_LIVE_DATA", False)  # try EDGAR/Yahoo/FRED live
    SEC_UA: str = os.getenv("VALUESCOPE_SEC_UA", "ValueScope research contact@example.com")

    # AI (OpenRouter)
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "z-ai/glm-5.2")
    # OpenRouter provider routing slug (see /api/v1/providers): StreamLake = "streamlake".
    OPENROUTER_PROVIDER: str = os.getenv("OPENROUTER_PROVIDER", "streamlake")
    OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    AI_ENABLED: bool = _bool("VALUESCOPE_AI_ENABLED", True)

    # Monte Carlo
    MC_RUNS: int = int(os.getenv("VALUESCOPE_MC_RUNS", "10000"))

    # Server
    PORT: int = int(os.getenv("PORT", "8000"))

    @classmethod
    def ai_ready(cls) -> bool:
        return cls.AI_ENABLED and bool(cls.OPENROUTER_API_KEY)


config = Config()
