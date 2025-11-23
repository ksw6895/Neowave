from __future__ import annotations

from datetime import datetime, timedelta

from neowave_core.patterns.complex_corrections import is_double_three, is_triple_three
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


def test_double_three_detection():
    base = datetime(2024, 2, 1, 0, 0)
    swings = [
        make_swing(100, 90, base, 2),
        make_swing(90, 95, base + timedelta(hours=2), 2),
        make_swing(95, 85, base + timedelta(hours=4), 2),
        make_swing(85, 88, base + timedelta(hours=6), 1),
        make_swing(88, 80, base + timedelta(hours=7), 2),
        make_swing(80, 86, base + timedelta(hours=9), 2),
        make_swing(86, 78, base + timedelta(hours=11), 2),
    ]
    result = is_double_three(swings, {})
    assert result.is_valid
    assert result.details["w_pattern"] in {"zigzag", "flat"}
    assert result.details["y_pattern"] in {"zigzag", "flat"}


def test_triple_three_detection():
    base = datetime(2024, 3, 1, 0, 0)
    swings = [
        make_swing(100, 90, base, 2),
        make_swing(90, 95, base + timedelta(hours=2), 2),
        make_swing(95, 85, base + timedelta(hours=4), 2),
        make_swing(85, 88, base + timedelta(hours=6), 1),
        make_swing(88, 80, base + timedelta(hours=7), 2),
        make_swing(80, 86, base + timedelta(hours=9), 2),
        make_swing(86, 78, base + timedelta(hours=11), 2),
        make_swing(78, 82, base + timedelta(hours=13), 1),
        make_swing(82, 74, base + timedelta(hours=14), 2),
        make_swing(74, 79, base + timedelta(hours=16), 2),
        make_swing(79, 70, base + timedelta(hours=18), 2),
    ]
    result = is_triple_three(swings, {})
    assert result.is_valid
    assert result.details["w_pattern"] in {"zigzag", "flat"}
    assert result.details["y_pattern"] in {"zigzag", "flat", "triangle"}
    assert result.details["z_pattern"] in {"zigzag", "flat", "triangle"}
