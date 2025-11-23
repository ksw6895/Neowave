from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterable, List, Sequence

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class Direction(Enum):
    UP = "up"
    DOWN = "down"

    @classmethod
    def from_prices(cls, start: float, end: float) -> "Direction":
        return cls.UP if end >= start else cls.DOWN


@dataclass(slots=True)
class Swing:
    start_time: datetime
    end_time: datetime
    start_price: float
    end_price: float
    direction: Direction
    high: float
    low: float
    duration: float  # seconds
    volume: float = 0.0

    @property
    def length(self) -> float:
        return abs(self.end_price - self.start_price)

    @property
    def time_seconds(self) -> float:
        return self.duration


def _build_swing(df: pd.DataFrame, start_idx: int, end_idx: int, direction: Direction) -> Swing:
    segment = df.iloc[start_idx : end_idx + 1]
    start_time = pd.to_datetime(segment.iloc[0]["timestamp"], utc=True).to_pydatetime()
    end_time = pd.to_datetime(segment.iloc[-1]["timestamp"], utc=True).to_pydatetime()
    start_price = float(segment.iloc[0]["close"])
    end_price = float(segment.iloc[-1]["close"])
    high = float(segment["high"].max())
    low = float(segment["low"].min())
    duration = (end_time - start_time).total_seconds()
    volume = float(segment["volume"].sum()) if "volume" in segment else 0.0
    return Swing(
        start_time=start_time,
        end_time=end_time,
        start_price=start_price,
        end_price=end_price,
        direction=direction,
        high=high,
        low=low,
        duration=duration,
        volume=volume,
    )


def _ratio(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return abs(a) / abs(b)


def normalize_swings(swings: Sequence[Swing], similarity_threshold: float = 0.33) -> list[Swing]:
    """Merge very small swings using the Rule of Similarity (~33%)."""
    merged: List[Swing] = list(swings)
    changed = True
    while changed and len(merged) >= 3:
        changed = False
        for idx in range(1, len(merged) - 1):
            prev_swing = merged[idx - 1]
            tiny = merged[idx]
            next_swing = merged[idx + 1]
            if prev_swing.direction != next_swing.direction:
                continue
            tiny_len = tiny.length
            neighbor_max = max(prev_swing.length, next_swing.length)
            neighbor_min = min(prev_swing.length, next_swing.length)
            if tiny_len >= similarity_threshold * neighbor_max or tiny_len >= similarity_threshold * neighbor_min:
                continue
            start_time = prev_swing.start_time
            end_time = next_swing.end_time
            duration = (end_time - start_time).total_seconds()
            new_swing = Swing(
                start_time=start_time,
                end_time=end_time,
                start_price=prev_swing.start_price,
                end_price=next_swing.end_price,
                direction=prev_swing.direction,
                high=max(prev_swing.high, tiny.high, next_swing.high),
                low=min(prev_swing.low, tiny.low, next_swing.low),
                duration=duration,
                volume=prev_swing.volume + tiny.volume + next_swing.volume,
            )
            merged = merged[: idx - 1] + [new_swing] + merged[idx + 2 :]
            changed = True
            break
    return merged


def detect_swings(
    df: pd.DataFrame,
    price_threshold_pct: float = 0.01,
    similarity_threshold: float = 0.33,
) -> list[Swing]:
    """Detect swings using a simple reversal threshold on closing prices."""
    if df.empty:
        return []
    if "timestamp" not in df.columns:
        raise ValueError("DataFrame must include a 'timestamp' column")

    ordered = df.sort_values("timestamp").reset_index(drop=True)
    closes = ordered["close"].to_numpy(dtype=float)
    timestamps = ordered["timestamp"].to_numpy()
    direction: Direction | None = None
    last_pivot_idx = 0
    extreme_idx = 0
    extreme_price = closes[0]
    swings: list[Swing] = []

    for idx in range(1, len(ordered)):
        price = closes[idx]
        if direction is None:
            move = (price - closes[last_pivot_idx]) / closes[last_pivot_idx]
            if abs(move) >= price_threshold_pct:
                direction = Direction.UP if price > closes[last_pivot_idx] else Direction.DOWN
                extreme_idx = idx
                extreme_price = price
            continue

        if direction == Direction.UP:
            if price > extreme_price:
                extreme_price = price
                extreme_idx = idx
            drawdown = (extreme_price - price) / extreme_price if extreme_price else 0.0
            if drawdown >= price_threshold_pct:
                swings.append(_build_swing(ordered, last_pivot_idx, extreme_idx, direction))
                last_pivot_idx = extreme_idx
                direction = Direction.DOWN
                extreme_idx = idx
                extreme_price = price
        else:
            if price < extreme_price:
                extreme_price = price
                extreme_idx = idx
            rally = (price - extreme_price) / abs(extreme_price) if extreme_price else 0.0
            if rally >= price_threshold_pct:
                swings.append(_build_swing(ordered, last_pivot_idx, extreme_idx, direction))
                last_pivot_idx = extreme_idx
                direction = Direction.UP
                extreme_idx = idx
                extreme_price = price

    if direction is None:
        trend_dir = Direction.from_prices(closes[0], closes[-1])
        swings.append(_build_swing(ordered, 0, len(ordered) - 1, trend_dir))
    else:
        swings.append(_build_swing(ordered, last_pivot_idx, len(ordered) - 1, direction))

    normalized = normalize_swings(swings, similarity_threshold=similarity_threshold)
    logger.info("Detected %s swings (normalized from %s)", len(normalized), len(swings))
    return normalized


def swings_to_array(swings: Iterable[Swing]) -> np.ndarray:
    """Convert swing lengths to an array for quick calculations."""
    return np.array([s.length for s in swings], dtype=float)
