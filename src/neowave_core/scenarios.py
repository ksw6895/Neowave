from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence

from neowave_core.patterns.flat import is_flat
from neowave_core.patterns.impulse import is_impulse
from neowave_core.patterns.zigzag import is_zigzag
from neowave_core.swings import Direction, Swing


def _fmt_time(dt: datetime) -> str:
    return dt.isoformat(timespec="minutes")


def _invalidation_for_impulse(swings: Sequence[Swing], direction: Direction) -> dict[str, float]:
    if direction == Direction.UP:
        return {"price_below": swings[0].start_price}
    return {"price_above": swings[0].start_price}


def _invalidation_for_correction(swings: Sequence[Swing], direction: Direction) -> dict[str, float]:
    if direction == Direction.UP:
        return {"price_above": swings[0].start_price}
    return {"price_below": swings[0].start_price}


def generate_scenarios(
    swings: Sequence[Swing],
    rules: dict[str, Any],
    max_scenarios: int = 5,
) -> list[dict[str, Any]]:
    """Scan swing windows and produce ranked pattern scenarios."""
    scenarios: list[dict[str, Any]] = []
    impulse_rules = rules.get("Impulse", {}).get("TrendingImpulse", {})
    zigzag_rules = rules.get("Corrections", {}).get("Zigzag", {})
    flat_rules = rules.get("Corrections", {}).get("Flat", {})

    for idx in range(len(swings) - 4):
        window = swings[idx : idx + 5]
        result = is_impulse(window, impulse_rules)
        if result.score <= 0:
            continue
        direction = Direction.UP if window[0].direction == Direction.UP else Direction.DOWN
        scenarios.append(
            {
                "pattern_type": f"impulse_{direction.value}",
                "score": result.score,
                "swing_indices": (idx, idx + 4),
                "textual_summary": f"Impulse {direction.value} from {_fmt_time(window[0].start_time)} to {_fmt_time(window[-1].end_time)} (subtype={result.details.get('subtype')})",
                "invalidation_levels": _invalidation_for_impulse(window, direction),
                "details": result.details,
            }
        )

    for idx in range(len(swings) - 2):
        window = swings[idx : idx + 3]

        zigzag_result = is_zigzag(window, zigzag_rules)
        if zigzag_result.score > 0:
            direction = Direction.UP if window[0].direction == Direction.UP else Direction.DOWN
            scenarios.append(
                {
                    "pattern_type": f"zigzag_{direction.value}",
                    "score": zigzag_result.score,
                    "swing_indices": (idx, idx + 2),
                    "textual_summary": f"Zigzag {direction.value} between {_fmt_time(window[0].start_time)} and {_fmt_time(window[-1].end_time)} (subtype={zigzag_result.details.get('subtype')})",
                    "invalidation_levels": _invalidation_for_correction(window, direction),
                    "details": zigzag_result.details,
                }
            )

        flat_result = is_flat(window, flat_rules)
        if flat_result.score > 0:
            direction = Direction.UP if window[0].direction == Direction.UP else Direction.DOWN
            scenarios.append(
                {
                    "pattern_type": f"flat_{direction.value}",
                    "score": flat_result.score,
                    "swing_indices": (idx, idx + 2),
                    "textual_summary": f"Flat {direction.value} between {_fmt_time(window[0].start_time)} and {_fmt_time(window[-1].end_time)} (subtype={flat_result.details.get('subtype')})",
                    "invalidation_levels": _invalidation_for_correction(window, direction),
                    "details": flat_result.details,
                }
            )

    scenarios.sort(key=lambda item: item["score"], reverse=True)
    return scenarios[:max_scenarios]
