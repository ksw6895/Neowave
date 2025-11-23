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
from neowave_core.rule_checks import RuleCheck
from neowave_core.rules_loader import TerminalImpulseRuleSet, extract_terminal_impulse_rules
from neowave_core.swings import Direction, Swing


def _has_overlap(trend: Direction, wave1: Swing, wave4: Swing) -> bool:
    if trend == Direction.UP:
        return wave4.low <= wave1.high
    return wave4.high >= wave1.low


def is_terminal_impulse(swings: Sequence[Swing], rules: dict | TerminalImpulseRuleSet | None = None) -> PatternCheckResult:
    """Validate a 5-swing terminal/ending diagonal."""
    if len(swings) != 5:
        return PatternCheckResult("terminal_impulse", False, 0.0, ["Terminal impulse requires 5 swings"])
    if not is_alternating(swings):
        return PatternCheckResult("terminal_impulse", False, 0.0, ["Swings must alternate for a terminal impulse"])

    params = (
        rules
        if isinstance(rules, TerminalImpulseRuleSet)
        else extract_terminal_impulse_rules(rules if isinstance(rules, dict) else None)
    )
    lengths = swing_lengths(swings)
    durations = swing_durations(swings)
    trend = pattern_direction(swings)
    violations: list[str] = []
    rule_checks: list[RuleCheck] = []
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

    record(
        "wave3_not_shortest",
        "Wave 3 cannot be the shortest motive wave",
        lengths[2],
        f">= min(w1,w5) ({min(lengths[0], lengths[4]):.2f})",
        lengths[2] >= min(lengths[0], lengths[4]),
        0.5,
        critical=True,
    )

    contracting = lengths[0] > lengths[2] > lengths[4]
    expanding = lengths[0] < lengths[2] < lengths[4]
    record(
        "progression",
        "Terminal impulse should contract or expand progressively",
        {"w1": lengths[0], "w3": lengths[2], "w5": lengths[4]},
        "contracting or expanding",
        contracting or expanding,
        0.25,
    )

    record(
        "wave2_depth",
        "Wave 2 should be a deep correction",
        length_ratio(lengths[1], lengths[0]),
        f">= {params.correction_depth_min:.2f}",
        length_ratio(lengths[1], lengths[0]) >= params.correction_depth_min,
        0.1,
    )
    record(
        "wave4_depth",
        "Wave 4 should be a deep correction",
        length_ratio(lengths[3], lengths[2]),
        f">= {params.correction_depth_min:.2f}",
        length_ratio(lengths[3], lengths[2]) >= params.correction_depth_min,
        0.1,
    )

    record(
        "w1_w3_similarity",
        "Waves 1 and 3 out of proportion",
        similarity_ratio(lengths[0], lengths[2]),
        f">= {params.proportion_similarity:.2f}",
        similarity_ratio(lengths[0], lengths[2]) >= params.proportion_similarity,
        0.1,
    )
    record(
        "w3_w5_similarity",
        "Waves 3 and 5 out of proportion",
        similarity_ratio(lengths[2], lengths[4]),
        f">= {params.proportion_similarity:.2f}",
        similarity_ratio(lengths[2], lengths[4]) >= params.proportion_similarity,
        0.1,
    )

    if durations[0] > 0 and durations[1] > 0:
        record(
            "wave2_time_depth",
            "Wave 2 duration too small relative to Wave 1",
            length_ratio(durations[1], durations[0]),
            f">= {params.correction_depth_min:.2f}",
            length_ratio(durations[1], durations[0]) >= params.correction_depth_min,
            0.05,
        )
    if durations[2] > 0 and durations[3] > 0:
        record(
            "wave4_time_depth",
            "Wave 4 duration too small relative to Wave 3",
            length_ratio(durations[3], durations[2]),
            f">= {params.correction_depth_min:.2f}",
            length_ratio(durations[3], durations[2]) >= params.correction_depth_min,
            0.05,
        )

    overlap = _has_overlap(trend, swings[0], swings[3])
    record(
        "wave4_overlap",
        "Terminal impulse expects wave 4 overlap with wave 1 territory",
        overlap,
        "True",
        overlap,
        0.2,
    )

    score = max(0.0, 1.0 - penalty)
    is_valid = score >= 0.5
    details = {
        "direction": trend.value,
        "mode": "contracting" if contracting else "expanding",
        "wave_lengths": lengths,
        "overlap": overlap,
        "rule_checks": rule_checks,
    }
    return PatternCheckResult("terminal_impulse", is_valid, score, violations, details=details, rule_checks=rule_checks)
