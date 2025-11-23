from __future__ import annotations

from dataclasses import dataclass


DEFAULT_SYMBOL = "BTCUSD"
DEFAULT_INTERVAL = "1hour"
DEFAULT_LOOKBACK = 500
DEFAULT_PRICE_THRESHOLD_PCT = 0.01  # 1% reversal threshold
DEFAULT_SIMILARITY_THRESHOLD = 0.33  # Rule of Similarity baseline
FMP_BASE_URL = "https://financialmodelingprep.com/api/v3/historical-chart"


@dataclass(slots=True)
class AnalysisConfig:
    """Runtime configuration for a NEoWave analysis run."""

    symbol: str = DEFAULT_SYMBOL
    interval: str = DEFAULT_INTERVAL
    lookback: int = DEFAULT_LOOKBACK
    price_threshold_pct: float = DEFAULT_PRICE_THRESHOLD_PCT
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD
