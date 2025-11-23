from __future__ import annotations

import math
from typing import Sequence

from neowave_core.patterns.common_types import PatternCheckResult, is_alternating, pattern_direction
from neowave_core.swings import Direction, Swing

EXTENSION_RATIO = 1.618  # From neowave_rules.json Impulse extension requirement
RETRACE_MIN = 0.236
SIMILARITY_THRESHOLD = 0.33


def _has_extension(w1: float, w3: float, w5: float) -> bool:
    legs = sorted([w1, w3, w5])
    if len(legs) < 2 or legs[-2] == 0:
        return False
    return legs[-1] >= EXTENSION_RATIO * legs[-2]


def _extension_allowed_without_ratio(w1: float, w3: float, w5: float) -> bool:
    """Allow rare cases described in rules when no 1.618x extension exists."""
    # TODO: refine with wave-end price context (docs/05_neowave_validation_and_limitations.md).
    if w3 >= w1 and w3 >= w5 and w5 < w3 and w3 < EXTENSION_RATIO * w1:
        return True
    if w1 >= w3 and w1 >= w5 and w1 < EXTENSION_RATIO * w3:
        return True
    return False


def _similar_enough(a: Swing, b: Swing, threshold: float = SIMILARITY_THRESHOLD) -> bool:
    price_ratio = min(a.length, b.length) / max(a.length, b.length) if max(a.length, b.length) else 1.0
    time_ratio = min(a.duration, b.duration) / max(a.duration, b.duration) if max(a.duration, b.duration) else 1.0
    return price_ratio >= threshold or time_ratio >= threshold


def _no_overlap(trend: Direction, wave1: Swing, wave4: Swing) -> bool:
    if trend == Direction.UP:
        return wave4.low > wave1.high
    return wave4.high < wave1.low


def is_impulse(swings: Sequence[Swing], rules: dict | None = None) -> PatternCheckResult:
    """Validate a 5-swing impulse using NEoWave rules."""
    violations: list[str] = []
    if len(swings) != 5:
        return PatternCheckResult("impulse", False, 0.0, ["Impulse requires exactly 5 swings"])
    if not is_alternating(swings):
        return PatternCheckResult("impulse", False, 0.0, ["Swings must alternate direction for an impulse"])

    trend = pattern_direction(swings)
    lengths = [s.length for s in swings]
    durations = [s.duration for s in swings]

    penalty = 0.0

    def require(condition: bool, message: str, weight: float, critical: bool = False) -> None:
        nonlocal penalty
        if condition:
            return
        penalty += weight
        violations.append(message)
        if critical:
            penalty = max(penalty, 1.0)

    # Wave 2 retracement bounds (>=0.236 and <1.0 of wave1) per rules JSON.
    w2_ratio = lengths[1] / lengths[0] if lengths[0] else 0.0
    require(w2_ratio >= RETRACE_MIN, "Wave 2 retracement too shallow", 0.1)
    require(w2_ratio < 1.0, "Wave 2 retraced 100%+ of Wave 1", 1.0, critical=True)

    # Wave 3 strength.
    require(lengths[2] > lengths[1], "Wave 3 must exceed Wave 2 length", 0.2)
    require(lengths[2] >= lengths[0], "Wave 3 should not be smaller than Wave 1", 0.2)
    require(lengths[2] >= min(lengths[0], lengths[4]), "Wave 3 cannot be shortest motive wave", 1.0, critical=True)

    # Extension requirement.
    extension_present = _has_extension(lengths[0], lengths[2], lengths[4])
    if not extension_present:
        extension_present = _extension_allowed_without_ratio(lengths[0], lengths[2], lengths[4])
        require(extension_present, "No extension or allowed exception present", 0.6)

    # Wave 5 minimum reach.
    require(lengths[4] >= 0.382 * lengths[3] if lengths[3] else False, "Wave 5 too short relative to Wave 4", 0.3)

    # Overlap rule for trending impulse.
    overlap = not _no_overlap(trend, swings[0], swings[3])
    if overlap:
        violations.append("Wave 4 overlaps Wave 1 price territory")
        penalty += 0.4

    # Time proportionality heuristics (>=33%).
    if durations[0] > 0:
        require(durations[1] / durations[0] >= SIMILARITY_THRESHOLD, "Wave 2 time too small vs Wave 1", 0.1)
    if durations[2] > 0:
        require(durations[3] / durations[2] >= SIMILARITY_THRESHOLD, "Wave 4 time too small vs Wave 3", 0.1)

    # Rule of similarity across adjacent waves.
    for left, right in zip(swings, swings[1:]):
        require(_similar_enough(left, right), "Adjacent waves violate similarity rule", 0.05)

    score = max(0.0, 1.0 - penalty)
    subtype = "terminal" if overlap else "trending"
    is_valid = score >= 0.55
    details = {
        "direction": trend.value,
        "extension_present": extension_present,
        "subtype": subtype,
        "wave_lengths": lengths,
    }
    return PatternCheckResult("impulse", is_valid, score, violations, details=details)
