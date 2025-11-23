from __future__ import annotations

from datetime import datetime

import pandas as pd

from neowave_core.swings import Direction, detect_swings


def test_detect_swings_basic_threshold():
    timestamps = pd.date_range(datetime(2024, 1, 1), periods=6, freq="H")
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
