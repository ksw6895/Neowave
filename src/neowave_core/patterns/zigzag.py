from __future__ import annotations

from typing import Sequence

from neowave_core.patterns.common_types import PatternCheckResult, pattern_direction
from neowave_core.rule_checks import RuleCheck
from neowave_core.rules_loader import ZigzagRuleSet, extract_zigzag_rules
from neowave_core.swings import Swing


def is_zigzag(swings: Sequence[Swing], rules: dict | ZigzagRuleSet | None = None) -> PatternCheckResult:
    """Check a 3-swing zigzag correction."""
    violations: list[str] = []
    rule_checks: list[RuleCheck] = []
    if len(swings) != 3:
        return PatternCheckResult("zigzag", False, 0.0, ["Zigzag requires exactly 3 swings"])

    if swings[0].direction == swings[1].direction or swings[0].direction != swings[2].direction:
        return PatternCheckResult("zigzag", False, 0.0, ["Zigzag must be a 5-3-5 alternating structure"])

    params = rules if isinstance(rules, ZigzagRuleSet) else extract_zigzag_rules(rules if isinstance(rules, dict) else None)
    lengths = [s.length for s in swings]
    durations = [s.duration for s in swings]
    trend = pattern_direction(swings)
    penalty = 0.0

    def record(
        key: str,
        description: str,
        value: float | bool,
        expected: str,
        condition: bool,
        weight: float,
        critical: bool = False,
    ) -> None:
        nonlocal penalty
        rule_checks.append(RuleCheck(key=key, description=description, value=value, expected=expected, passed=condition, penalty=0.0 if condition else weight))
        if condition:
            return
        violations.append(description)
        penalty += weight
        if critical:
            penalty = max(penalty, 1.0)

    b_ratio = lengths[1] / lengths[0] if lengths[0] else 0.0
    record(
        "waveb_retrace",
        "Wave B retraces too much for a zigzag",
        b_ratio,
        f"<= {params.b_max:.3f}",
        b_ratio <= params.b_max,
        1.0,
        critical=True,
    )

    c_ratio = lengths[2] / lengths[0] if lengths[0] else 0.0
    record(
        "wavec_vs_wavea",
        "Wave C too small relative to Wave A",
        c_ratio,
        f">= {params.c_min_valid:.3f}",
        c_ratio >= params.c_min_valid,
        0.5,
        critical=True,
    )

    # Time rules: B should take at least as long as A; C at least as long as A.
    if durations[0] > 0:
        record(
            "waveb_time",
            "Wave B time shorter than Wave A",
            durations[1] / durations[0] if durations[0] else 0.0,
            ">= 1.0",
            durations[1] >= durations[0],
            0.1,
        )
    if durations[0] > 0:
        record(
            "wavec_time",
            "Wave C time shorter than Wave A",
            durations[2] / durations[0] if durations[0] else 0.0,
            ">= 1.0",
            durations[2] >= durations[0],
            0.1,
        )

    subtype = "normal"
    if c_ratio < params.c_typical:
        subtype = "truncated"
        penalty += 0.15
    elif c_ratio > params.c_elongated:
        subtype = "elongated"
        penalty += 0.1

    score = max(0.0, 1.0 - penalty)
    is_valid = score >= 0.5
    details = {
        "direction": trend.value,
        "b_ratio": b_ratio,
        "c_ratio": c_ratio,
        "subtype": subtype,
        "rule_checks": rule_checks,
    }
    return PatternCheckResult("zigzag", is_valid, score, violations, details=details, rule_checks=rule_checks)
