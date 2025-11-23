from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterable, List, Sequence

import numpy as np
import pandas as pd

from neowave_core.config import (
    DEFAULT_MIN_PRICE_RETRACE_RATIO,
    DEFAULT_MIN_TIME_RATIO,
    DEFAULT_PRICE_THRESHOLD_PCT,
    DEFAULT_SIMILARITY_THRESHOLD,
    DEFAULT_SWING_COUNT_RANGE,
    SWING_SCALES,
)

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
    def delta_price(self) -> float:
        return self.end_price - self.start_price

    @property
    def price_range(self) -> float:
        return self.high - self.low

    @property
    def time_seconds(self) -> float:
        return self.duration

    @property
    def energy(self) -> float:
        """Rough thermodynamic balance proxy using price, time, and volume."""
        return abs(self.delta_price) * max(self.duration, 1.0) * max(self.volume, 1.0)


@dataclass(slots=True)
class SwingSet:
    scale_id: str
    swings: Sequence["Swing"]


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
            neighbor_time_max = max(prev_swing.duration, next_swing.duration, 1e-9)
            price_ratio = tiny_len / neighbor_max if neighbor_max else 0.0
            time_ratio = tiny.duration / neighbor_time_max if neighbor_time_max else 0.0
            # Only merge when both price/time similarity fall below threshold (noise-like swing).
            if price_ratio >= similarity_threshold or time_ratio >= similarity_threshold:
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


def _compute_box_ratio(swing: Swing, typical_scale: float) -> float:
    time_range = max(swing.duration, 1.0)
    price_range = max(swing.price_range, 1e-9)
    scale = typical_scale if typical_scale > 0 else 1.0
    return price_range / (scale * time_range)


def _shape_penalty(ratio: float) -> float:
    """Penalize extreme aspect ratios; keep 0 around the 0.5~2 comfort band."""
    if ratio <= 0:
        return 0.0
    if 0.5 <= ratio <= 2.0:
        return 0.0
    if ratio < 0.5:
        return min(1.0, (0.5 - ratio) * 2.0)
    return min(1.0, (ratio - 2.0) / 2.0)


def _typical_scale(swings: Sequence[Swing]) -> float:
    ratios = []
    for swing in swings:
        if swing.duration <= 0:
            continue
        ratios.append(swing.price_range / swing.duration)
    if not ratios:
        return 1.0
    return float(np.median(ratios))


def _detect_swings_once(
    ordered: pd.DataFrame,
    price_threshold_pct: float,
    min_price_retrace_ratio: float,
    min_time_ratio: float,
) -> list[Swing]:
    closes = ordered["close"].to_numpy(dtype=float)
    timestamps = ordered["timestamp"].to_numpy()
    direction: Direction | None = None
    last_pivot_idx = 0
    extreme_idx = 0
    swings: list[Swing] = []

    for idx in range(1, len(ordered)):
        price = closes[idx]
        if direction is None:
            move = (price - closes[last_pivot_idx]) / closes[last_pivot_idx] if closes[last_pivot_idx] else 0.0
            if abs(move) >= price_threshold_pct:
                direction = Direction.UP if price >= closes[last_pivot_idx] else Direction.DOWN
                extreme_idx = idx
            continue

        # Track the farthest price in the current trend direction.
        if direction == Direction.UP:
            if price >= closes[extreme_idx]:
                extreme_idx = idx
        else:
            if price <= closes[extreme_idx]:
                extreme_idx = idx

        swing_length = abs(closes[extreme_idx] - closes[last_pivot_idx])
        if swing_length == 0:
            continue

        start_time = pd.to_datetime(timestamps[last_pivot_idx], utc=True)
        extreme_time = pd.to_datetime(timestamps[extreme_idx], utc=True)
        current_time = pd.to_datetime(timestamps[idx], utc=True)
        swing_duration = (extreme_time - start_time).total_seconds()
        elapsed = (current_time - extreme_time).total_seconds()

        retrace_ratio = abs(price - closes[extreme_idx]) / swing_length
        time_ratio = (elapsed / swing_duration) if swing_duration > 0 else 0.0

        if retrace_ratio >= min_price_retrace_ratio or time_ratio >= min_time_ratio:
            swings.append(_build_swing(ordered, last_pivot_idx, extreme_idx, direction))
            last_pivot_idx = extreme_idx
            direction = Direction.DOWN if direction == Direction.UP else Direction.UP
            extreme_idx = idx

    if direction is None:
        trend_dir = Direction.from_prices(closes[0], closes[-1])
        swings.append(_build_swing(ordered, 0, len(ordered) - 1, trend_dir))
    else:
        swings.append(_build_swing(ordered, last_pivot_idx, len(ordered) - 1, direction))

    return swings


def identify_major_pivots(
    swings: Sequence[Swing],
    max_pivots: int = 5,
    weights: dict[str, float] | None = None,
) -> list[int]:
    """Score swings by price/time/energy balance to pick anchor candidates."""
    if not swings or max_pivots <= 0:
        return []
    weight = {
        "price": 0.35,
        "time": 0.2,
        "volume": 0.1,
        "energy": 0.3,
        "shape": 0.2,
    }
    if weights:
        weight.update(weights)

    avg_abs_delta = float(np.mean([abs(sw.delta_price) for sw in swings])) or 1.0
    avg_duration = float(np.mean([sw.duration for sw in swings])) or 1.0
    avg_volume = float(np.mean([sw.volume for sw in swings])) or 1.0
    typical_scale = _typical_scale(swings)

    scored: list[tuple[int, float]] = []
    for idx, sw in enumerate(swings):
        price_score = abs(sw.delta_price) / avg_abs_delta
        time_score = sw.duration / avg_duration
        volume_score = sw.volume / avg_volume
        energy_score = price_score * max(time_score, 1.0)
        ratio = _compute_box_ratio(sw, typical_scale)
        shape_penalty = _shape_penalty(ratio)
        pivot_score = (
            weight["price"] * price_score
            + weight["time"] * time_score
            + weight["volume"] * volume_score
            + weight["energy"] * energy_score
            - weight["shape"] * shape_penalty
        )
        scored.append((idx, pivot_score))

    scored.sort(key=lambda item: item[1], reverse=True)
    return [idx for idx, score in scored[:max_pivots] if score > 0]


def detect_swings(
    df: pd.DataFrame,
    price_threshold_pct: float = DEFAULT_PRICE_THRESHOLD_PCT,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    min_price_retrace_ratio: float = DEFAULT_MIN_PRICE_RETRACE_RATIO,
    min_time_ratio: float = DEFAULT_MIN_TIME_RATIO,
    target_count_range: tuple[int, int] = DEFAULT_SWING_COUNT_RANGE,
    max_refinements: int = 2,
) -> list[Swing]:
    """Detect swings using a simple reversal threshold on closing prices."""
    if df.empty:
        return []
    if "timestamp" not in df.columns:
        raise ValueError("DataFrame must include a 'timestamp' column")

    ordered = df.sort_values("timestamp").reset_index(drop=True)
    target_min, target_max = target_count_range

    swings = _detect_swings_once(
        ordered,
        price_threshold_pct=price_threshold_pct,
        min_price_retrace_ratio=min_price_retrace_ratio,
        min_time_ratio=min_time_ratio,
    )
    normalized = normalize_swings(swings, similarity_threshold=similarity_threshold)

    # Auto-tune thresholds to stay within the desired monowave count window.
    tuned_price_ratio = min_price_retrace_ratio
    tuned_time_ratio = min_time_ratio
    tuned_price_threshold = price_threshold_pct
    attempts = 0
    while attempts < max_refinements:
        count = len(normalized)
        if target_min <= count <= target_max:
            break
        attempts += 1
        if count < target_min:
            tuned_price_ratio = max(0.15, tuned_price_ratio - 0.05)
            tuned_time_ratio = max(0.25, tuned_time_ratio - 0.05)
            tuned_price_threshold = max(0.5 * price_threshold_pct, tuned_price_threshold * 0.8)
        else:
            tuned_price_ratio = min(0.5, tuned_price_ratio + 0.05)
            tuned_time_ratio = min(0.5, tuned_time_ratio + 0.05)
            tuned_price_threshold = min(price_threshold_pct * 1.5, tuned_price_threshold * 1.2)
        swings = _detect_swings_once(
            ordered,
            price_threshold_pct=tuned_price_threshold,
            min_price_retrace_ratio=tuned_price_ratio,
            min_time_ratio=tuned_time_ratio,
        )
        normalized = normalize_swings(swings, similarity_threshold=similarity_threshold)

    logger.info(
        "Detected %s swings (normalized from %s) with price_ratio=%.3f time_ratio=%.3f threshold=%.4f",
        len(normalized),
        len(swings),
        tuned_price_ratio,
        tuned_time_ratio,
        tuned_price_threshold,
    )
    return normalized


def swings_to_array(swings: Iterable[Swing]) -> np.ndarray:
    """Convert swing lengths to an array for quick calculations."""
    return np.array([s.length for s in swings], dtype=float)


def detect_swings_multi_scale(
    df: pd.DataFrame,
    scales: list[dict] | None = None,
) -> list[SwingSet]:
    """Run swing detection across multiple predefined scales (macro/base/micro)."""
    config_scales = scales or SWING_SCALES
    results: list[SwingSet] = []
    for scale in config_scales:
        scale_id = scale.get("id", "base")
        price_threshold_pct = float(scale.get("price_threshold_pct", DEFAULT_PRICE_THRESHOLD_PCT))
        similarity_threshold = float(scale.get("similarity_threshold", DEFAULT_SIMILARITY_THRESHOLD))
        min_price_retrace_ratio = float(scale.get("min_price_retrace_ratio", DEFAULT_MIN_PRICE_RETRACE_RATIO))
        min_time_ratio = float(scale.get("min_time_ratio", DEFAULT_MIN_TIME_RATIO))
        target_min = int(scale.get("target_min_swings", DEFAULT_SWING_COUNT_RANGE[0]))
        target_max = int(scale.get("target_max_swings", DEFAULT_SWING_COUNT_RANGE[1]))
        swings = detect_swings(
            df,
            price_threshold_pct=price_threshold_pct,
            similarity_threshold=similarity_threshold,
            min_price_retrace_ratio=min_price_retrace_ratio,
            min_time_ratio=min_time_ratio,
            target_count_range=(target_min, target_max),
        )
        results.append(SwingSet(scale_id=scale_id, swings=swings))
    return results
