from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_SYMBOL = "BTCUSD"
DEFAULT_INTERVAL = "1hour"
DEFAULT_LOOKBACK = 500
DEFAULT_PRICE_THRESHOLD_PCT = 0.01  # 1% reversal threshold
DEFAULT_SIMILARITY_THRESHOLD = 0.33  # Rule of Similarity baseline
FMP_BASE_URL = "https://financialmodelingprep.com/api/v3/historical-chart"


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(slots=True)
class AnalysisConfig:
    """Runtime configuration for a NEoWave analysis run."""

    symbol: str = DEFAULT_SYMBOL
    interval: str = DEFAULT_INTERVAL
    lookback: int = DEFAULT_LOOKBACK
    price_threshold_pct: float = DEFAULT_PRICE_THRESHOLD_PCT
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD

    @classmethod
    def from_env(cls) -> "AnalysisConfig":
        """Build a config using environment variables (see .env.example)."""
        return cls(
            symbol=os.getenv("SYMBOL", DEFAULT_SYMBOL),
            interval=os.getenv("INTERVAL", DEFAULT_INTERVAL),
            lookback=_env_int("LOOKBACK", DEFAULT_LOOKBACK),
            price_threshold_pct=_env_float("PRICE_THRESHOLD_PCT", DEFAULT_PRICE_THRESHOLD_PCT),
            similarity_threshold=_env_float("SIMILARITY_THRESHOLD", DEFAULT_SIMILARITY_THRESHOLD),
        )
