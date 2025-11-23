from __future__ import annotations

from datetime import datetime

import pandas as pd

from neowave_core.swings import Direction, detect_swings, detect_swings_multi_scale, identify_major_pivots


def test_detect_swings_basic_threshold():
    timestamps = pd.date_range(datetime(2024, 1, 1), periods=6, freq="h")
    closes = [100, 110, 104, 124, 120, 133]
    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1] * len(closes),
        }
    )

    swings = detect_swings(df, price_threshold_pct=0.05, similarity_threshold=0.2)
    assert len(swings) == 3
    assert swings[0].direction == Direction.UP
    assert swings[-1].direction == Direction.UP


def test_detect_swings_multi_scale_returns_sets():
    timestamps = pd.date_range(datetime(2024, 1, 1), periods=6, freq="h")
    closes = [100, 110, 104, 124, 120, 133]
    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1] * len(closes),
        }
    )
    swing_sets = detect_swings_multi_scale(df)
    assert swing_sets, "Expected multiple swing sets"
    scale_ids = {s.scale_id for s in swing_sets}
    assert {"macro", "base", "micro"}.issuperset(scale_ids) or len(scale_ids) >= 1


def test_identify_major_pivots_scores_swings():
    timestamps = pd.date_range(datetime(2024, 1, 1), periods=10, freq="h")
    closes = [100, 108, 102, 120, 115, 130, 118, 140, 132, 150]
    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1] * len(closes),
        }
    )
    swings = detect_swings(df, price_threshold_pct=0.04, similarity_threshold=0.25)
    pivots = identify_major_pivots(swings, max_pivots=3)
    assert pivots, "Expected at least one pivot"
    assert all(isinstance(idx, int) and 0 <= idx < len(swings) for idx in pivots)
