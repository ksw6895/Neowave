from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from neowave_core.models import Monowave

logger = logging.getLogger(__name__)


class Direction(Enum):
    UP = "up"
    DOWN = "down"

    @classmethod
    def from_prices(cls, start: float, end: float) -> "Direction":
        return cls.UP if end >= start else cls.DOWN


@dataclass(slots=True)
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


def _normalize_bars(data: Iterable[dict[str, Any]] | pd.DataFrame) -> list[Bar]:
    if isinstance(data, pd.DataFrame):
        if "timestamp" not in data.columns:
            raise ValueError("DataFrame must include a 'timestamp' column")
        data = data.sort_values("timestamp").reset_index(drop=True)
        records = data.to_dict("records")
    else:
        records = list(data)
    bars: list[Bar] = []
    for item in records:
        ts = item.get("timestamp")
        if not isinstance(ts, datetime):
            ts = pd.to_datetime(ts, utc=True).to_pydatetime()
        bars.append(
            Bar(
                timestamp=ts,
                open=float(item.get("open", item.get("close", 0.0))),
                high=float(item.get("high", item.get("close", 0.0))),
                low=float(item.get("low", item.get("close", 0.0))),
                close=float(item.get("close", item.get("open", 0.0))),
                volume=float(item.get("volume", 0.0)),
            )
        )
    return bars


def detect_monowaves(
    bars: Iterable[dict[str, Any]] | pd.DataFrame,
    retrace_threshold_price: float = 0.236,
    retrace_threshold_time_ratio: float = 0.2,
) -> list[Monowave]:
    """
    Detect monowaves using NEoWave-style zigzag pivots.

    A new monowave is confirmed when an opposing move retraces at least
    retrace_threshold_price (23~38%) or lasts longer than retrace_threshold_time_ratio
    of the prior swing duration.
    """
    ordered = _normalize_bars(bars)
    if not ordered:
        return []

    swings: list[Monowave] = []
    current_dir: str | None = None
    pivot_idx = 0
    extreme_idx = 0

    for idx in range(1, len(ordered)):
        price = ordered[idx].close
        pivot_price = ordered[pivot_idx].close
        if current_dir is None:
            if price == pivot_price:
                continue
            current_dir = "up" if price > pivot_price else "down"
            extreme_idx = idx
            continue

        # Track farthest price in current direction.
        if current_dir == "up":
            if price >= ordered[extreme_idx].close:
                extreme_idx = idx
        else:
            if price <= ordered[extreme_idx].close:
                extreme_idx = idx

        move_length = abs(ordered[extreme_idx].close - ordered[pivot_idx].close)
        if move_length == 0:
            continue

        retrace_price = abs(price - ordered[extreme_idx].close)
        elapsed_bars = idx - extreme_idx
        prev_duration = max(extreme_idx - pivot_idx, 1)

        if retrace_price >= retrace_threshold_price * move_length or elapsed_bars >= retrace_threshold_time_ratio * prev_duration:
            wave_id = len(swings)
            swings.append(Monowave.from_bars(ordered, pivot_idx, extreme_idx, wave_id=wave_id))
            pivot_idx = extreme_idx
            current_dir = "down" if current_dir == "up" else "up"
            extreme_idx = idx

    # Final leg to the end.
    if not swings or swings[-1].end_idx != len(ordered) - 1:
        wave_id = len(swings)
        swings.append(Monowave.from_bars(ordered, pivot_idx, len(ordered) - 1, wave_id=wave_id))

    return swings


def merge_monowave_pair(w1: Monowave, w2: Monowave, wave_id: int) -> Monowave:
    start_idx = min(w1.start_idx, w2.start_idx)
    end_idx = max(w1.end_idx, w2.end_idx)
    start_time = min(w1.start_time, w2.start_time)
    end_time = max(w1.end_time, w2.end_time)
    start_price = w1.start_price
    end_price = w2.end_price
    direction: str = "up" if end_price >= start_price else "down"
    high_price = max(w1.high_price, w2.high_price)
    low_price = min(w1.low_price, w2.low_price)
    duration = w1.duration + w2.duration
    volume_sum = w1.volume_sum + w2.volume_sum
    return Monowave(
        id=wave_id,
        start_idx=start_idx,
        end_idx=end_idx,
        start_time=start_time,
        end_time=end_time,
        start_price=start_price,
        end_price=end_price,
        high_price=high_price,
        low_price=low_price,
        direction=direction,  # type: ignore[arg-type]
        price_change=end_price - start_price,
        abs_price_change=abs(end_price - start_price),
        duration=duration,
        volume_sum=volume_sum,
    )


def merge_by_similarity(monowaves: Sequence[Monowave], min_ratio: float = 0.33) -> list[Monowave]:
    """Merge adjacent monowaves that violate the Rule of Similarity (both price/time < threshold)."""
    merged = list(monowaves)
    changed = True
    while changed and len(merged) >= 2:
        changed = False
        new_list: list[Monowave] = []
        i = 0
        while i < len(merged):
            if i == len(merged) - 1:
                new_list.append(merged[i])
                break
            w1 = merged[i]
            w2 = merged[i + 1]
            price_ratio = min(w1.abs_price_change, w2.abs_price_change) / max(w1.abs_price_change, w2.abs_price_change)
            time_ratio = min(w1.duration, w2.duration) / max(w1.duration, w2.duration)
            if price_ratio < min_ratio and time_ratio < min_ratio:
                merged_wave = merge_monowave_pair(w1, w2, wave_id=len(new_list))
                new_list.append(merged_wave)
                i += 2
                changed = True
            else:
                new_list.append(w1)
                i += 1
        merged = new_list
    return merged


def detect_monowaves_from_df(
    df: pd.DataFrame,
    retrace_threshold_price: float = 0.236,
    retrace_threshold_time_ratio: float = 0.2,
    similarity_threshold: float = 0.33,
) -> list[Monowave]:
    raw = detect_monowaves(df, retrace_threshold_price=retrace_threshold_price, retrace_threshold_time_ratio=retrace_threshold_time_ratio)
    merged = merge_by_similarity(raw, min_ratio=similarity_threshold)
    logger.info("Detected %s monowaves (merged from %s)", len(merged), len(raw))
    return merged


def identify_major_pivots(monowaves: Sequence[Monowave], max_pivots: int = 5) -> list[int]:
    """Score monowaves by price/time/volume to pick anchor candidates (compat helper)."""
    if not monowaves or max_pivots <= 0:
        return []
    avg_abs_delta = float(np.mean([mw.abs_price_change for mw in monowaves])) or 1.0
    avg_duration = float(np.mean([mw.duration for mw in monowaves])) or 1.0
    avg_volume = float(np.mean([mw.volume_sum for mw in monowaves])) or 1.0
    scored: list[tuple[int, float]] = []
    for idx, mw in enumerate(monowaves):
        price_score = mw.abs_price_change / avg_abs_delta
        time_score = mw.duration / avg_duration
        volume_score = mw.volume_sum / avg_volume if avg_volume else 0.0
        energy_score = price_score * max(time_score, 1.0)
        pivot_score = 0.4 * price_score + 0.2 * time_score + 0.1 * volume_score + 0.3 * energy_score
        scored.append((idx, pivot_score))
    scored.sort(key=lambda item: item[1], reverse=True)
    return [idx for idx, _ in scored[:max_pivots] if idx < len(monowaves)]


def auto_select_timeframe(candidates: dict[str, pd.DataFrame], target_monowaves: int = 40) -> tuple[str, list[Monowave]]:
    """
    Pick the timeframe that yields a monowave count closest to target_monowaves.

    candidates: mapping {timeframe: ohlcv_dataframe}
    """
    best_tf = None
    best_distance = float("inf")
    best_monowaves: list[Monowave] = []
    for tf, df in candidates.items():
        monowaves = detect_monowaves_from_df(df)
        distance = abs(len(monowaves) - target_monowaves)
        if distance < best_distance:
            best_distance = distance
            best_tf = tf
            best_monowaves = monowaves
    if best_tf is None:
        raise ValueError("No timeframe candidates provided")
    return best_tf, best_monowaves


def normalize_monowaves(monowaves: Sequence[Monowave]) -> list[Monowave]:
    """Alias kept for compatibility."""
    return merge_by_similarity(monowaves)


# Backward compatibility aliases
Swing = Monowave
