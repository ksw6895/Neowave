from __future__ import annotations

from datetime import datetime, timedelta

from neowave_core.patterns.flat import is_flat
from neowave_core.patterns.impulse import is_impulse
from neowave_core.patterns.zigzag import is_zigzag
from neowave_core.swings import Direction, Swing


def make_swing(start_price: float, end_price: float, start_time: datetime, hours: float) -> Swing:
    end_time = start_time + timedelta(hours=hours)
    direction = Direction.from_prices(start_price, end_price)
    return Swing(
        start_time=start_time,
        end_time=end_time,
        start_price=start_price,
        end_price=end_price,
        direction=direction,
        high=max(start_price, end_price),
        low=min(start_price, end_price),
        duration=hours * 3600,
        volume=0.0,
    )


def test_impulse_pattern_valid():
    base = datetime(2024, 1, 1, 0, 0)
    swings = [
        make_swing(100, 110, base, 2),
        make_swing(110, 104, base + timedelta(hours=2), 2),
        make_swing(104, 128, base + timedelta(hours=4), 3),
        make_swing(128, 120, base + timedelta(hours=7), 2),
        make_swing(120, 133, base + timedelta(hours=9), 2),
    ]
    result = is_impulse(swings, {})
    assert result.is_valid
    assert result.score > 0.55


def test_zigzag_pattern_valid():
    base = datetime(2024, 1, 2, 0, 0)
    swings = [
        make_swing(100, 90, base, 2),
        make_swing(90, 95, base + timedelta(hours=2), 2),
        make_swing(95, 82, base + timedelta(hours=4), 3),
    ]
    result = is_zigzag(swings, {})
    assert result.is_valid
    assert result.details["subtype"] in {"normal", "elongated", "truncated"}


def test_zigzag_truncated_classification():
    base = datetime(2024, 1, 2, 12, 0)
    swings = [
        make_swing(100, 90, base, 2),
        make_swing(90, 95, base + timedelta(hours=2), 2),
        make_swing(95, 90, base + timedelta(hours=4), 2),
    ]
    result = is_zigzag(swings, {})
    assert result.is_valid
    assert result.details["subtype"] == "truncated"


def test_flat_pattern_valid():
    base = datetime(2024, 1, 3, 0, 0)
    swings = [
        make_swing(100, 90, base, 2),
        make_swing(90, 100, base + timedelta(hours=2), 2),
        make_swing(100, 92, base + timedelta(hours=4), 3),
    ]
    result = is_flat(swings, {})
    assert result.is_valid
    assert result.details["subtype"] in {"weak_b", "normal", "expanded"}
