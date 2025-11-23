from __future__ import annotations

from typing import Sequence

from neowave_core.patterns.common import PatternCheckResult, pattern_direction
from neowave_core.swings import Swing

B_MAX_RETRACE = 0.618
C_MIN_RATIO = 0.382
C_TYPIICAL_RATIO = 0.618
C_ELONGATED_RATIO = 1.618


def is_zigzag(swings: Sequence[Swing], rules: dict | None = None) -> PatternCheckResult:
    """Check a 3-swing zigzag correction."""
    violations: list[str] = []
    if len(swings) != 3:
        return PatternCheckResult("zigzag", False, 0.0, ["Zigzag requires exactly 3 swings"])

    if swings[0].direction == swings[1].direction or swings[0].direction != swings[2].direction:
        return PatternCheckResult("zigzag", False, 0.0, ["Zigzag must be a 5-3-5 alternating structure"])

    lengths = [s.length for s in swings]
    durations = [s.duration for s in swings]
    trend = pattern_direction(swings)
    penalty = 0.0

    def require(condition: bool, message: str, weight: float, critical: bool = False) -> None:
        nonlocal penalty
        if condition:
            return
        violations.append(message)
        penalty += weight
        if critical:
            penalty = max(penalty, 1.0)

    b_ratio = lengths[1] / lengths[0] if lengths[0] else 0.0
    require(b_ratio <= B_MAX_RETRACE, "Wave B retraces too much for a zigzag", 1.0, critical=True)

    c_ratio = lengths[2] / lengths[0] if lengths[0] else 0.0
    require(c_ratio >= C_MIN_RATIO, "Wave C too small relative to Wave A", 0.5, critical=True)

    # Time rules: B should take at least as long as A; C at least as long as A.
    if durations[0] > 0:
        require(durations[1] >= durations[0], "Wave B time shorter than Wave A", 0.1)
    if durations[0] > 0:
        require(durations[2] >= durations[0], "Wave C time shorter than Wave A", 0.1)

    subtype = "normal"
    if c_ratio < C_TYPIICAL_RATIO:
        subtype = "truncated"
        penalty += 0.1
    elif c_ratio > C_ELONGATED_RATIO:
        subtype = "elongated"
        penalty += 0.1

    score = max(0.0, 1.0 - penalty)
    is_valid = score >= 0.5
    details = {
        "direction": trend.value,
        "b_ratio": b_ratio,
        "c_ratio": c_ratio,
        "subtype": subtype,
    }
    return PatternCheckResult("zigzag", is_valid, score, violations, details=details)
