from __future__ import annotations

from typing import Sequence

from neowave_core.patterns.common import PatternCheckResult, pattern_direction
from neowave_core.swings import Swing

B_MIN_RATIO = 0.618
C_MIN_RATIO = 0.382
C_FAILURE_RATIO = 1.38


def is_flat(swings: Sequence[Swing], rules: dict | None = None) -> PatternCheckResult:
    """Check a 3-swing flat correction."""
    violations: list[str] = []
    if len(swings) != 3:
        return PatternCheckResult("flat", False, 0.0, ["Flat requires exactly 3 swings"])
    if swings[0].direction == swings[1].direction or swings[0].direction != swings[2].direction:
        return PatternCheckResult("flat", False, 0.0, ["Flat must alternate directions (A vs B vs C)"])

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
    require(b_ratio >= B_MIN_RATIO, "Wave B too small for a flat (needs >= 0.618 of A)", 1.0, critical=True)

    c_ratio_a = lengths[2] / lengths[0] if lengths[0] else 0.0
    require(c_ratio_a >= C_MIN_RATIO, "Wave C too small relative to Wave A", 0.6, critical=True)

    # Time proportionality.
    if durations[0] > 0:
        require(durations[1] >= durations[0], "Wave B time shorter than Wave A", 0.1)
    if durations[0] > 0:
        require(durations[2] >= durations[0], "Wave C time shorter than Wave A", 0.1)

    subtype = "normal"
    if b_ratio <= 0.8:
        subtype = "weak_b"
    elif b_ratio <= 1.0:
        subtype = "normal"
    else:
        subtype = "expanded"

    # Additional C vs B sizing for subtype clarity.
    c_ratio_b = lengths[2] / lengths[1] if lengths[1] else 0.0
    if subtype == "weak_b" and c_ratio_b < 1.0:
        violations.append("Weak-B flat with short C (double failure risk)")
        penalty += 0.1
    if c_ratio_b > C_FAILURE_RATIO:
        violations.append("Wave C elongated relative to Wave B")
        penalty += 0.1

    score = max(0.0, 1.0 - penalty)
    is_valid = score >= 0.5
    details = {
        "direction": trend.value,
        "b_ratio": b_ratio,
        "c_ratio_a": c_ratio_a,
        "c_ratio_b": c_ratio_b,
        "subtype": subtype,
    }
    return PatternCheckResult("flat", is_valid, score, violations, details=details)
