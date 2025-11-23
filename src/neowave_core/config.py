from __future__ import annotations

import os
from dataclasses import dataclass, field


DEFAULT_SYMBOL = "BTCUSD"
DEFAULT_INTERVAL = "1hour"
DEFAULT_LOOKBACK = 500
DEFAULT_PRICE_THRESHOLD_PCT = 0.01  # 1% reversal threshold
DEFAULT_SIMILARITY_THRESHOLD = 0.33  # Rule of Similarity baseline
DEFAULT_MIN_PRICE_RETRACE_RATIO = 0.23  # NEoWave monowave retrace (price)
DEFAULT_MIN_TIME_RATIO = 0.33  # NEoWave monowave retrace (time)
DEFAULT_SWING_COUNT_RANGE = (15, 80)  # target count window for automatic tuning
FMP_BASE_URL = "https://financialmodelingprep.com/api/v3/historical-chart"
SWING_SCALES = [
    {
        "id": "macro",
        "price_threshold_pct": 0.025,
        "similarity_threshold": 0.4,
        "min_price_retrace_ratio": DEFAULT_MIN_PRICE_RETRACE_RATIO,
        "min_time_ratio": DEFAULT_MIN_TIME_RATIO,
    },
    {
        "id": "base",
        "price_threshold_pct": DEFAULT_PRICE_THRESHOLD_PCT,
        "similarity_threshold": DEFAULT_SIMILARITY_THRESHOLD,
        "min_price_retrace_ratio": DEFAULT_MIN_PRICE_RETRACE_RATIO,
        "min_time_ratio": DEFAULT_MIN_TIME_RATIO,
    },
    {
        "id": "micro",
        "price_threshold_pct": 0.005,
        "similarity_threshold": 0.3,
        "min_price_retrace_ratio": DEFAULT_MIN_PRICE_RETRACE_RATIO,
        "min_time_ratio": DEFAULT_MIN_TIME_RATIO,
    },
]


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
    min_price_retrace_ratio: float = DEFAULT_MIN_PRICE_RETRACE_RATIO
    min_time_ratio: float = DEFAULT_MIN_TIME_RATIO
    swing_count_range: tuple[int, int] = DEFAULT_SWING_COUNT_RANGE
    swing_scales: list[dict[str, float]] = field(default_factory=lambda: [dict(scale) for scale in SWING_SCALES])

    @classmethod
    def from_env(cls) -> "AnalysisConfig":
        """Build a config using environment variables (see .env.example)."""
        return cls(
            symbol=os.getenv("SYMBOL", DEFAULT_SYMBOL),
            interval=os.getenv("INTERVAL", DEFAULT_INTERVAL),
            lookback=_env_int("LOOKBACK", DEFAULT_LOOKBACK),
            price_threshold_pct=_env_float("PRICE_THRESHOLD_PCT", DEFAULT_PRICE_THRESHOLD_PCT),
            similarity_threshold=_env_float("SIMILARITY_THRESHOLD", DEFAULT_SIMILARITY_THRESHOLD),
            min_price_retrace_ratio=_env_float("MIN_PRICE_RETRACE_RATIO", DEFAULT_MIN_PRICE_RETRACE_RATIO),
            min_time_ratio=_env_float("MIN_TIME_RATIO", DEFAULT_MIN_TIME_RATIO),
            swing_scales=[dict(scale) for scale in SWING_SCALES],
        )

    def find_scale(self, scale_id: str | None) -> dict[str, float] | None:
        if not scale_id:
            return None
        for scale in self.swing_scales:
            if scale.get("id") == scale_id:
                return scale
        return None
