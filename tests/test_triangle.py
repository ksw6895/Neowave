from __future__ import annotations

from datetime import datetime, timedelta

from neowave_core.patterns.triangle import is_triangle
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


def test_contracting_triangle_detected():
    base = datetime(2024, 1, 10, 0, 0)
    swings = [
        make_swing(100, 90, base, 2),
        make_swing(90, 95, base + timedelta(hours=2), 2),
        make_swing(95, 88, base + timedelta(hours=4), 2),
        make_swing(88, 93, base + timedelta(hours=6), 2),
        make_swing(93, 89, base + timedelta(hours=8), 2),
    ]
    result = is_triangle(swings, {})
    assert result.is_valid
    assert result.details["subtype"] == "contracting"
