from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Sequence, Any

from neowave_core.swings import Swing


@dataclass(slots=True)
class WaveBox:
    swing_start: int
    swing_end: int

    time_start: datetime
    time_end: datetime

    price_low: float
    price_high: float


def compute_wave_box(swings: Sequence[Swing], start_idx: int, end_idx: int) -> WaveBox:
    """Aggregate a contiguous swing window into a price/time box."""
    if not swings or start_idx < 0 or end_idx >= len(swings) or start_idx > end_idx:
        raise ValueError("Invalid swing range for wave box computation")
    window = swings[start_idx : end_idx + 1]
    time_start = window[0].start_time
    time_end = window[-1].end_time
    price_low = min(s.low for s in window)
    price_high = max(s.high for s in window)
    return WaveBox(
        swing_start=start_idx,
        swing_end=end_idx,
        time_start=time_start,
        time_end=time_end,
        price_low=price_low,
        price_high=price_high,
    )


def serialize_wave_box(box: WaveBox | None) -> dict[str, Any] | None:
    if box is None:
        return None
    return asdict(box)
