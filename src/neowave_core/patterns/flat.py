from __future__ import annotations

from typing import Sequence

from neowave_core.patterns.common_types import PatternCheckResult, pattern_direction
from neowave_core.rules_loader import FlatRuleSet, extract_flat_rules
from neowave_core.swings import Swing


def is_flat(swings: Sequence[Swing], rules: dict | FlatRuleSet | None = None) -> PatternCheckResult:
    """Check a 3-swing flat correction."""
    violations: list[str] = []
    if len(swings) != 3:
        return PatternCheckResult("flat", False, 0.0, ["Flat requires exactly 3 swings"])
    if swings[0].direction == swings[1].direction or swings[0].direction != swings[2].direction:
        return PatternCheckResult("flat", False, 0.0, ["Flat must alternate directions (A vs B vs C)"])

    params = rules if isinstance(rules, FlatRuleSet) else extract_flat_rules(rules if isinstance(rules, dict) else None)
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
    require(
        b_ratio >= params.b_min,
        f"Wave B too small for a flat (needs >= {params.b_min:.3f} of A)",
        1.0,
        critical=True,
    )

    c_ratio_a = lengths[2] / lengths[0] if lengths[0] else 0.0
    require(c_ratio_a >= params.c_min, "Wave C too small relative to Wave A", 0.6, critical=True)

    # Time proportionality.
    if durations[0] > 0:
        require(durations[1] >= durations[0], "Wave B time shorter than Wave A", 0.1)
    if durations[0] > 0:
        require(durations[2] >= durations[0], "Wave C time shorter than Wave A", 0.1)

    subtype = "normal"
    if b_ratio <= params.weak_b_threshold:
        subtype = "weak_b"
    elif b_ratio <= params.expanded_b_threshold:
        subtype = "normal"
    else:
        subtype = "expanded"
        if b_ratio > params.running_flat_b_threshold:
            subtype = "running_flat"

    # Additional C vs B sizing for subtype clarity.
    c_ratio_b = lengths[2] / lengths[1] if lengths[1] else 0.0
    if subtype == "weak_b" and c_ratio_b < 1.0:
        violations.append("Weak-B flat with short C (double failure risk)")
        penalty += 0.1
    if c_ratio_b > params.c_elongated:
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
