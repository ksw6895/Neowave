from __future__ import annotations

from typing import Sequence

from neowave_core.patterns.common_types import PatternCheckResult, is_alternating, pattern_direction
from neowave_core.rule_checks import RuleCheck
from neowave_core.rules_loader import ImpulseRuleSet, extract_impulse_rules
from neowave_core.swings import Direction, Swing


def _has_extension(w1: float, w3: float, w5: float, ratio: float) -> bool:
    legs = sorted([w1, w3, w5])
    if len(legs) < 2 or legs[-2] == 0:
        return False
    return legs[-1] >= ratio * legs[-2]


def _extension_allowed_without_ratio(w1: float, w3: float, w5: float, ratio: float) -> bool:
    """Allow rare cases described in rules when no 1.618x extension exists."""
    if w3 >= w1 and w3 >= w5 and w5 < w3 and w3 < ratio * w1:
        return True
    if w1 >= w3 and w1 >= w5 and w1 < ratio * w3:
        return True
    return False


def _similar_enough(a: Swing, b: Swing, threshold: float) -> bool:
    price_ratio = min(a.length, b.length) / max(a.length, b.length) if max(a.length, b.length) else 1.0
    time_ratio = min(a.duration, b.duration) / max(a.duration, b.duration) if max(a.duration, b.duration) else 1.0
    return price_ratio >= threshold or time_ratio >= threshold


def _no_overlap(trend: Direction, wave1: Swing, wave4: Swing) -> bool:
    if trend == Direction.UP:
        return wave4.low > wave1.high
    return wave4.high < wave1.low


def is_impulse(swings: Sequence[Swing], rules: dict | ImpulseRuleSet | None = None) -> PatternCheckResult:
    """Validate a 5-swing impulse using NEoWave rules."""
    violations: list[str] = []
    rule_checks: list[RuleCheck] = []
    if len(swings) != 5:
        return PatternCheckResult("impulse", False, 0.0, ["Impulse requires exactly 5 swings"])
    if not is_alternating(swings):
        return PatternCheckResult("impulse", False, 0.0, ["Swings must alternate direction for an impulse"])

    params = rules if isinstance(rules, ImpulseRuleSet) else extract_impulse_rules(rules if isinstance(rules, dict) else None)
    trend = pattern_direction(swings)
    lengths = [s.length for s in swings]
    durations = [s.duration for s in swings]

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
        penalty += weight
        violations.append(description)
        if critical:
            penalty = max(penalty, 1.0)

    w2_ratio = lengths[1] / lengths[0] if lengths[0] else 0.0
    record(
        "wave2_retrace_min",
        "Wave 2 retracement too shallow",
        w2_ratio,
        f">= {params.wave2_min:.3f}",
        w2_ratio >= params.wave2_min,
        0.1,
    )
    record(
        "wave2_retrace_max",
        "Wave 2 retraced 100%+ of Wave 1",
        w2_ratio,
        f"< {params.wave2_max:.3f}",
        w2_ratio < params.wave2_max,
        1.0,
        critical=True,
    )

    # Wave 3 strength.
    record(
        "wave3_gt_wave2",
        "Wave 3 must exceed Wave 2 length",
        lengths[2] - lengths[1],
        "> 0",
        lengths[2] > lengths[1],
        0.2,
    )
    record(
        "wave3_vs_wave1",
        "Wave 3 should not be smaller than Wave 1",
        lengths[2] / lengths[0] if lengths[0] else 0.0,
        ">= 1.0",
        lengths[2] >= lengths[0],
        0.2,
    )
    record(
        "wave3_not_shortest",
        "Wave 3 cannot be shortest motive wave",
        lengths[2],
        f">= min(w1,w5) ({min(lengths[0], lengths[4]):.2f})",
        lengths[2] >= min(lengths[0], lengths[4]),
        1.0,
        critical=True,
    )

    # Extension requirement.
    extension_present = _has_extension(lengths[0], lengths[2], lengths[4], params.extension_ratio)
    if not extension_present:
        extension_present = _extension_allowed_without_ratio(lengths[0], lengths[2], lengths[4], params.extension_ratio)
        record(
            "extension_present",
            "No extension or allowed exception present",
            extension_present,
            f">= one leg {params.extension_ratio:.3f}x",
            extension_present,
            0.6,
        )
    else:
        rule_checks.append(
            RuleCheck(
                key="extension_present",
                description="Extension present across motive waves",
                value=True,
                expected=f">= one leg {params.extension_ratio:.3f}x",
                passed=True,
                penalty=0.0,
            )
        )

    # Wave 5 minimum reach.
    wave5_condition = lengths[4] >= params.wave5_vs_wave4_min * lengths[3] if lengths[3] else False
    record(
        "wave5_vs_wave4",
        "Wave 5 too short relative to Wave 4",
        lengths[4] / lengths[3] if lengths[3] else 0.0,
        f">= {params.wave5_vs_wave4_min:.3f}",
        wave5_condition,
        0.3,
    )

    # Overlap rule for trending impulse.
    overlap = not _no_overlap(trend, swings[0], swings[3])
    record(
        "wave4_overlap",
        "Wave 4 overlaps Wave 1 price territory",
        overlap,
        "False",
        not overlap,
        0.4,
    )

    # Time proportionality heuristics (>=33%).
    if durations[0] > 0:
        record(
            "wave2_time_similarity",
            "Wave 2 time too small vs Wave 1",
            durations[1] / durations[0] if durations[0] else 0.0,
            f">= {params.similarity_threshold:.2f}",
            durations[1] / durations[0] >= params.similarity_threshold if durations[0] else False,
            0.1,
        )
    if durations[2] > 0:
        record(
            "wave4_time_similarity",
            "Wave 4 time too small vs Wave 3",
            durations[3] / durations[2] if durations[2] else 0.0,
            f">= {params.similarity_threshold:.2f}",
            durations[3] / durations[2] >= params.similarity_threshold if durations[2] else False,
            0.1,
        )

    # Rule of similarity across adjacent waves.
    for left, right in zip(swings, swings[1:]):
        ratio = min(left.length, right.length) / max(left.length, right.length) if max(left.length, right.length) else 1.0
        record(
            "adjacent_similarity",
            "Adjacent waves violate similarity rule",
            ratio,
            f">= {params.similarity_threshold:.2f}",
            _similar_enough(left, right, params.similarity_threshold),
            0.05,
        )

    score = max(0.0, 1.0 - penalty)
    subtype = "terminal" if overlap else "trending"
    is_valid = score >= 0.55
    details = {
        "direction": trend.value,
        "extension_present": extension_present,
        "subtype": subtype,
        "wave_lengths": lengths,
        "similarity_threshold": params.similarity_threshold,
        "rule_checks": rule_checks,
    }
    return PatternCheckResult("impulse", is_valid, score, violations, details=details, rule_checks=rule_checks)
