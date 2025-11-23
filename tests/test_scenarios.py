from __future__ import annotations

from datetime import datetime, timedelta

from neowave_core.patterns.impulse import is_impulse
from neowave_core.rules_loader import load_rules
from neowave_core.scenarios import generate_scenarios
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


def test_generate_scenarios_returns_impulse():
    base = datetime(2024, 1, 5, 0, 0)
    swings = [
        make_swing(100, 110, base, 2),
        make_swing(110, 104, base + timedelta(hours=2), 2),
        make_swing(104, 128, base + timedelta(hours=4), 3),
        make_swing(128, 120, base + timedelta(hours=7), 2),
        make_swing(120, 133, base + timedelta(hours=9), 2),
    ]

    rules = load_rules("rules/neowave_rules.json")
    scenarios = generate_scenarios(swings, rules, max_scenarios=3)
    assert any(s["pattern_type"].startswith("impulse") for s in scenarios)
    assert scenarios[0]["score"] <= 1.0
