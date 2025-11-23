from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence

from neowave_core.rules_loader import (
    extract_flat_rules,
    extract_impulse_rules,
    extract_terminal_impulse_rules,
    extract_triangle_rules,
    extract_zigzag_rules,
)
from neowave_core.patterns import (
    is_double_three,
    is_flat,
    is_impulse,
    is_terminal_impulse,
    is_triangle,
    is_triple_three,
    is_zigzag,
)
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
    current_price: float | None = None,
) -> list[dict[str, Any]]:
    """Scan swing windows and produce ranked pattern scenarios."""
    scenarios: list[dict[str, Any]] = []
    impulse_rules = rules.get("Impulse", {}).get("TrendingImpulse", {})
    terminal_rules = rules.get("Impulse", {}).get("TerminalImpulse", {})
    zigzag_rules = rules.get("Corrections", {}).get("Zigzag", {})
    flat_rules = rules.get("Corrections", {}).get("Flat", {})
    triangle_rules = rules.get("Corrections", {}).get("Triangle", {})
    combination_rules = rules.get("Corrections", {}).get("Combination", {})
    impulse_params = extract_impulse_rules(impulse_rules)
    terminal_params = extract_terminal_impulse_rules(terminal_rules)
    zigzag_params = extract_zigzag_rules(zigzag_rules)
    flat_params = extract_flat_rules(flat_rules)
    triangle_params = extract_triangle_rules(triangle_rules)
    weights = {
        "impulse": 1.2,
        "terminal_impulse": 0.9,
        "triangle": 0.85,
        "zigzag": 0.75,
        "flat": 0.75,
        "double_three": 0.65,
        "triple_three": 0.55,
    }

    def is_invalid_now(invalidation: dict[str, float] | None) -> bool:
        if invalidation is None or current_price is None:
            return False
        above = invalidation.get("price_above")
        below = invalidation.get("price_below")
        if above is not None and current_price >= above:
            return True
        if below is not None and current_price <= below:
            return True
        return False

    def add_scenario(
        pattern_type: str,
        score: float,
        swing_indices: tuple[int, int],
        summary: str,
        invalidation: dict[str, float],
        details: dict[str, Any] | None = None,
    ) -> None:
        if is_invalid_now(invalidation):
            return
        base = pattern_type.split("_", 1)[0]
        weight = weights.get(base, 1.0)
        weighted_score = score * weight
        in_progress = swing_indices[1] >= len(swings) - 1
        scenarios.append(
            {
                "pattern_type": pattern_type,
                "score": score,
                "weighted_score": weighted_score,
                "swing_indices": swing_indices,
                "textual_summary": summary,
                "invalidation_levels": invalidation,
                "details": details or {},
                "in_progress": in_progress,
            }
        )

    # Impulses, terminal impulses, and triangles (5-swing windows).
    for idx in range(len(swings) - 4):
        window = swings[idx : idx + 5]
        direction = Direction.UP if window[0].direction == Direction.UP else Direction.DOWN

        impulse_result = is_impulse(window, impulse_params)
        if impulse_result.score > 0:
            subtype = impulse_result.details.get("subtype")
            add_scenario(
                f"impulse_{direction.value}",
                impulse_result.score,
                (idx, idx + 4),
                f"Impulse {direction.value} from {_fmt_time(window[0].start_time)} to {_fmt_time(window[-1].end_time)} (subtype={subtype})",
                _invalidation_for_impulse(window, direction),
                impulse_result.details,
            )

        terminal_result = is_terminal_impulse(window, terminal_params)
        if terminal_result.score > 0:
            add_scenario(
                f"terminal_impulse_{direction.value}",
                terminal_result.score,
                (idx, idx + 4),
                f"Terminal impulse {direction.value} between {_fmt_time(window[0].start_time)} and {_fmt_time(window[-1].end_time)} (mode={terminal_result.details.get('mode')})",
                _invalidation_for_impulse(window, direction),
                terminal_result.details,
            )

        triangle_result = is_triangle(window, triangle_params)
        if triangle_result.score > 0:
            add_scenario(
                f"triangle_{triangle_result.details.get('subtype')}_{direction.value}",
                triangle_result.score,
                (idx, idx + 4),
                f"Triangle ({triangle_result.details.get('subtype')}) from {_fmt_time(window[0].start_time)} to {_fmt_time(window[-1].end_time)}",
                _invalidation_for_correction(window, direction),
                triangle_result.details,
            )

    # Three-swing corrections (zigzags, flats).
    for idx in range(len(swings) - 2):
        window = swings[idx : idx + 3]
        direction = Direction.UP if window[0].direction == Direction.UP else Direction.DOWN

        zigzag_result = is_zigzag(window, zigzag_params)
        if zigzag_result.score > 0:
            add_scenario(
                f"zigzag_{direction.value}",
                zigzag_result.score,
                (idx, idx + 2),
                f"Zigzag {direction.value} between {_fmt_time(window[0].start_time)} and {_fmt_time(window[-1].end_time)} (subtype={zigzag_result.details.get('subtype')})",
                _invalidation_for_correction(window, direction),
                zigzag_result.details,
            )

        flat_result = is_flat(window, flat_params)
        if flat_result.score > 0:
            add_scenario(
                f"flat_{direction.value}",
                flat_result.score,
                (idx, idx + 2),
                f"Flat {direction.value} between {_fmt_time(window[0].start_time)} and {_fmt_time(window[-1].end_time)} (subtype={flat_result.details.get('subtype')})",
                _invalidation_for_correction(window, direction),
                flat_result.details,
            )

    # Complex corrections.
    for idx in range(len(swings) - 6):
        window = swings[idx : idx + 7]
        direction = Direction.UP if window[0].direction == Direction.UP else Direction.DOWN
        double_result = is_double_three(window, combination_rules.get("DoubleThree", {}))
        if double_result.score > 0:
            add_scenario(
                f"double_three_{direction.value}",
                double_result.score,
                (idx, idx + 6),
                f"Double three ({double_result.details.get('w_pattern')} + {double_result.details.get('y_pattern')}) between {_fmt_time(window[0].start_time)} and {_fmt_time(window[-1].end_time)}",
                _invalidation_for_correction(window, direction),
                double_result.details,
            )

    for idx in range(len(swings) - 10):
        window = swings[idx : idx + 11]
        direction = Direction.UP if window[0].direction == Direction.UP else Direction.DOWN
        triple_result = is_triple_three(window, combination_rules.get("TripleThree", {}))
        if triple_result.score > 0:
            add_scenario(
                f"triple_three_{direction.value}",
                triple_result.score,
                (idx, idx + 10),
                f"Triple three ({triple_result.details.get('w_pattern')} + {triple_result.details.get('y_pattern')} + {triple_result.details.get('z_pattern')}) between {_fmt_time(window[0].start_time)} and {_fmt_time(window[-1].end_time)}",
                _invalidation_for_correction(window, direction),
                triple_result.details,
            )

    scenarios.sort(key=lambda item: item["weighted_score"], reverse=True)
    pruned: list[dict[str, Any]] = []
    for candidate in scenarios:
        c_start, c_end = candidate["swing_indices"]
        keep = True
        for existing in pruned:
            e_start, e_end = existing["swing_indices"]
            overlap = max(0, min(c_end, e_end) - max(c_start, e_start) + 1)
            min_len = min(c_end - c_start + 1, e_end - e_start + 1)
            # If overlapping heavily, keep only the higher weighted score
            if overlap >= max(2, min_len // 2):
                keep = False
                break
        if keep:
            pruned.append(candidate)
        if len(pruned) >= max_scenarios:
            break
    return pruned
