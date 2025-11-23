from __future__ import annotations

from typing import Sequence

from neowave_core.patterns.common_types import (
    PatternCheckResult,
    is_alternating,
    length_ratio,
    pattern_direction,
    similarity_ratio,
    swing_lengths,
    swing_durations,
)
from neowave_core.swings import Direction, Swing


def _has_overlap(trend: Direction, wave1: Swing, wave4: Swing) -> bool:
    if trend == Direction.UP:
        return wave4.low <= wave1.high
    return wave4.high >= wave1.low


def is_terminal_impulse(swings: Sequence[Swing], rules: dict | None = None) -> PatternCheckResult:
    """Validate a 5-swing terminal/ending diagonal."""
    if len(swings) != 5:
        return PatternCheckResult("terminal_impulse", False, 0.0, ["Terminal impulse requires 5 swings"])
    if not is_alternating(swings):
        return PatternCheckResult("terminal_impulse", False, 0.0, ["Swings must alternate for a terminal impulse"])

    lengths = swing_lengths(swings)
    durations = swing_durations(swings)
    trend = pattern_direction(swings)
    violations: list[str] = []
    penalty = 0.0

    def require(condition: bool, message: str, weight: float, critical: bool = False) -> None:
        nonlocal penalty
        if condition:
            return
        violations.append(message)
        penalty += weight
        if critical:
            penalty = max(penalty, 1.0)

    require(lengths[2] >= min(lengths[0], lengths[4]), "Wave 3 cannot be the shortest motive wave", 0.5, critical=True)

    contracting = lengths[0] > lengths[2] > lengths[4]
    expanding = lengths[0] < lengths[2] < lengths[4]
    require(contracting or expanding, "Terminal impulse should contract or expand progressively", 0.25)

    require(length_ratio(lengths[1], lengths[0]) >= 0.33, "Wave 2 should be a deep correction", 0.1)
    require(length_ratio(lengths[3], lengths[2]) >= 0.33, "Wave 4 should be a deep correction", 0.1)

    require(similarity_ratio(lengths[0], lengths[2]) >= 0.5, "Waves 1 and 3 out of proportion", 0.1)
    require(similarity_ratio(lengths[2], lengths[4]) >= 0.5, "Waves 3 and 5 out of proportion", 0.1)

    if durations[0] > 0 and durations[1] > 0:
        require(
            length_ratio(durations[1], durations[0]) >= 0.33,
            "Wave 2 duration too small relative to Wave 1",
            0.05,
        )
    if durations[2] > 0 and durations[3] > 0:
        require(
            length_ratio(durations[3], durations[2]) >= 0.33,
            "Wave 4 duration too small relative to Wave 3",
            0.05,
        )

    overlap = _has_overlap(trend, swings[0], swings[3])
    require(overlap, "Terminal impulse expects wave 4 overlap with wave 1 territory", 0.2)

    score = max(0.0, 1.0 - penalty)
    is_valid = score >= 0.5
    details = {
        "direction": trend.value,
        "mode": "contracting" if contracting else "expanding",
        "wave_lengths": lengths,
        "overlap": overlap,
    }
    return PatternCheckResult("terminal_impulse", is_valid, score, violations, details=details)
