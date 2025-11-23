from __future__ import annotations

from typing import Sequence

from neowave_core.patterns.common_types import PatternCheckResult, is_alternating, length_ratio, pattern_direction
from neowave_core.patterns.flat import is_flat
from neowave_core.patterns.triangle import is_triangle
from neowave_core.patterns.zigzag import is_zigzag
from neowave_core.rule_checks import RuleCheck
from neowave_core.swings import Swing


def _select_correction(swings: Sequence[Swing]) -> PatternCheckResult:
    """Pick the best-fitting basic correction for a segment."""
    candidates: list[PatternCheckResult] = []
    if len(swings) == 3:
        candidates.append(is_zigzag(swings, {}))
        candidates.append(is_flat(swings, {}))
    if len(swings) == 5:
        candidates.append(is_triangle(swings, {}))
    if not candidates:
        return PatternCheckResult("correction", False, 0.0, ["Unsupported correction segment length"])
    best = max(candidates, key=lambda res: res.score)
    return best


def is_double_three(swings: Sequence[Swing], rules: dict | None = None) -> PatternCheckResult:
    """Detect a simple W-X-Y double three using 7 swings (W:3, X:1, Y:3)."""
    if len(swings) != 7:
        return PatternCheckResult("double_three", False, 0.0, ["Double three requires exactly 7 swings"])
    if not is_alternating(swings):
        return PatternCheckResult("double_three", False, 0.0, ["Double three requires alternating swings"])

    w_segment = swings[:3]
    x_wave = swings[3]
    y_segment = swings[4:]

    w_result = _select_correction(w_segment)
    y_result = _select_correction(y_segment)
    violations: list[str] = []
    rule_checks: list[RuleCheck] = []
    penalty = 0.0

    def require(key: str, description: str, value: float | bool, expected: str, condition: bool, weight: float) -> None:
        nonlocal penalty
        rule_checks.append(RuleCheck(key=key, description=description, value=value, expected=expected, passed=condition, penalty=0.0 if condition else weight))
        if condition:
            return
        penalty += weight
        violations.append(description)

    rule_checks.extend(w_result.rule_checks)
    rule_checks.extend(y_result.rule_checks)

    w_y_same = w_segment[0].direction == y_segment[0].direction
    require("w_y_same_trend", "W and Y should trend the same direction", w_y_same, "same direction", w_y_same, 0.3)
    w_span = sum(s.length for s in w_segment)
    y_span = sum(s.length for s in y_segment)
    if max(w_span, y_span) > 0:
        x_ratio = length_ratio(x_wave.length, max(w_span, y_span))
        connector_ok = x_ratio <= 0.8
        require("connector_size", "Connector X too large relative to W/Y", x_ratio, "<= 0.8", connector_ok, 0.2)

    base_score = (w_result.score + y_result.score) / 2
    # Penalize invalid subpatterns.
    if not w_result.is_valid:
        penalty += 0.4
        rule_checks.append(
            RuleCheck(
                key="w_valid",
                description="W segment correction invalid/weak",
                value=w_result.score,
                expected=">= 0.4",
                passed=False,
                penalty=0.4,
            )
        )
    if not y_result.is_valid:
        penalty += 0.4
        rule_checks.append(
            RuleCheck(
                key="y_valid",
                description="Y segment correction invalid/weak",
                value=y_result.score,
                expected=">= 0.4",
                passed=False,
                penalty=0.4,
            )
        )

    score = max(0.0, base_score - penalty)
    is_valid = score >= 0.4
    direction = pattern_direction(swings)
    details = {
        "direction": direction.value,
        "w_pattern": w_result.pattern,
        "y_pattern": y_result.pattern,
        "w_valid": w_result.is_valid,
        "y_valid": y_result.is_valid,
        "rule_checks": rule_checks,
    }
    return PatternCheckResult("double_three", is_valid, score, violations, details=details, rule_checks=rule_checks)


def is_triple_three(swings: Sequence[Swing], rules: dict | None = None) -> PatternCheckResult:
    """Detect a W-X-Y-X-Z triple three using 11 swings (3-1-3-1-3 structure)."""
    if len(swings) != 11:
        return PatternCheckResult("triple_three", False, 0.0, ["Triple three requires exactly 11 swings"])
    if not is_alternating(swings):
        return PatternCheckResult("triple_three", False, 0.0, ["Triple three requires alternating swings"])

    w_segment = swings[:3]
    x1_wave = swings[3]
    y_segment = swings[4:7]
    x2_wave = swings[7]
    z_segment = swings[8:]

    w_result = _select_correction(w_segment)
    y_result = _select_correction(y_segment)
    z_result = _select_correction(z_segment)
    violations: list[str] = []
    rule_checks: list[RuleCheck] = []
    penalty = 0.0

    def require(key: str, description: str, value: float | bool, expected: str, condition: bool, weight: float) -> None:
        nonlocal penalty
        rule_checks.append(RuleCheck(key=key, description=description, value=value, expected=expected, passed=condition, penalty=0.0 if condition else weight))
        if condition:
            return
        penalty += weight
        violations.append(description)

    w_y_z_same = w_segment[0].direction == y_segment[0].direction == z_segment[0].direction
    require("w_y_z_same_trend", "W, Y, Z should share the same trend direction", w_y_z_same, "same direction", w_y_z_same, 0.4)
    max_span = max(
        sum(s.length for s in w_segment),
        sum(s.length for s in y_segment),
        sum(s.length for s in z_segment),
        0.0,
    )
    if max_span > 0:
        first_connector = length_ratio(x1_wave.length, max_span)
        second_connector = length_ratio(x2_wave.length, max_span)
        require("connector_x1", "First connector X too large", first_connector, "<= 0.8", first_connector <= 0.8, 0.15)
        require("connector_x2", "Second connector X too large", second_connector, "<= 0.8", second_connector <= 0.8, 0.15)

    base_score = (w_result.score + y_result.score + z_result.score) / 3
    for sub_result, label in ((w_result, "W"), (y_result, "Y"), (z_result, "Z")):
        if not sub_result.is_valid:
            violations.append(f"{label} pattern weak/invalid")
            penalty += 0.25
            rule_checks.append(
                RuleCheck(
                    key=f"{label.lower()}_valid",
                    description=f"{label} segment correction invalid/weak",
                    value=sub_result.score,
                    expected=">= 0.4",
                    passed=False,
                    penalty=0.25,
                )
            )
        rule_checks.extend(sub_result.rule_checks)

    score = max(0.0, base_score - penalty)
    is_valid = score >= 0.4
    direction = pattern_direction(swings)
    details = {
        "direction": direction.value,
        "w_pattern": w_result.pattern,
        "y_pattern": y_result.pattern,
        "z_pattern": z_result.pattern,
        "rule_checks": rule_checks,
    }
    return PatternCheckResult("triple_three", is_valid, score, violations, details=details, rule_checks=rule_checks)
