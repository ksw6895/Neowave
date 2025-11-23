from __future__ import annotations

from typing import Sequence

from neowave_core.patterns.common_types import (
    PatternCheckResult,
    is_alternating,
    length_ratio,
    pattern_direction,
    similarity_ratio,
    swing_lengths,
)
from neowave_core.rules_loader import TriangleRuleSet, extract_triangle_rules
from neowave_core.swings import Swing


def _evaluate_contracting(lengths: list[float], params: TriangleRuleSet) -> tuple[float, list[str]]:
    violations: list[str] = []
    penalty = 0.0

    def require(condition: bool, message: str, weight: float) -> None:
        nonlocal penalty
        if condition:
            return
        penalty += weight
        violations.append(message)

    c_ratio = length_ratio(lengths[2], lengths[0])
    e_ratio = length_ratio(lengths[4], lengths[2])
    require(
        c_ratio <= max(params.contracting_c_to_a * 1.1, 0.9),
        "Wave C should contract relative to Wave A",
        0.25,
    )
    require(
        params.contracting_e_min <= e_ratio <= params.contracting_e_max,
        "Wave E not proportionate to Wave C",
        0.2,
    )
    require(lengths[1] < lengths[0], "Wave B should be smaller than Wave A", 0.1)
    require(lengths[3] <= lengths[2], "Wave D should be smaller than Wave C", 0.1)
    require(lengths[4] <= lengths[2], "Wave E should be smaller than Wave C", 0.1)
    require(lengths[0] >= lengths[2], "Wave A should be larger than Wave C in contracting triangle", 0.2)

    score = max(0.0, 1.0 - penalty)
    return score, violations


def _evaluate_expanding(lengths: list[float], params: TriangleRuleSet) -> tuple[float, list[str]]:
    violations: list[str] = []
    penalty = 0.0

    def require(condition: bool, message: str, weight: float) -> None:
        nonlocal penalty
        if condition:
            return
        penalty += weight
        violations.append(message)

    require(length_ratio(lengths[2], lengths[0]) >= params.expanding_c_min, "Wave C must expand beyond Wave A", 0.3)
    require(length_ratio(lengths[4], lengths[2]) >= params.expanding_e_min, "Wave E must expand beyond Wave C", 0.3)
    require(lengths[1] >= lengths[0], "Wave B should be at least as large as Wave A", 0.1)
    require(lengths[3] >= lengths[1], "Wave D should expand beyond Wave B", 0.1)
    require(
        length_ratio(lengths[4], lengths[2]) <= params.expanding_e_max,
        "Wave E blow-off exceeds expanding triangle bounds",
        0.2,
    )

    score = max(0.0, 1.0 - penalty)
    return score, violations


def _evaluate_neutral(lengths: list[float], params: TriangleRuleSet) -> tuple[float, list[str]]:
    violations: list[str] = []
    penalty = 0.0

    def require(condition: bool, message: str, weight: float) -> None:
        nonlocal penalty
        if condition:
            return
        penalty += weight
        violations.append(message)

    require(lengths[2] >= max(lengths), "Wave C should be the largest swing in neutral triangle", 0.25)
    a_c_ratio = length_ratio(lengths[0], lengths[2])
    e_c_ratio = length_ratio(lengths[4], lengths[2])
    require(
        params.neutral_a_min <= a_c_ratio <= params.neutral_a_max,
        "Wave A size not aligned with neutral triangle proportions",
        0.2,
    )
    require(
        params.neutral_e_min <= e_c_ratio <= params.neutral_e_max,
        "Wave E size not aligned with neutral triangle proportions",
        0.2,
    )
    require(
        similarity_ratio(lengths[0], lengths[4]) >= params.similarity_tolerance,
        "Wave A and E should be similar in size",
        0.15,
    )
    score = max(0.0, 1.0 - penalty)
    return score, violations


def is_triangle(swings: Sequence[Swing], rules: dict | TriangleRuleSet | None = None) -> PatternCheckResult:
    """Check a 5-swing triangle and classify the subtype."""
    if len(swings) != 5:
        return PatternCheckResult("triangle", False, 0.0, ["Triangle requires exactly 5 swings"])
    if not is_alternating(swings):
        return PatternCheckResult("triangle", False, 0.0, ["Triangle swings must alternate direction"])

    params = rules if isinstance(rules, TriangleRuleSet) else extract_triangle_rules(rules if isinstance(rules, dict) else None)
    lengths = swing_lengths(swings)
    candidates = []
    for subtype, evaluator in (
        ("contracting", _evaluate_contracting),
        ("expanding", _evaluate_expanding),
        ("neutral", _evaluate_neutral),
    ):
        score, violations = evaluator(lengths, params)
        candidates.append((score, subtype, violations))

    best_score, best_subtype, best_violations = max(candidates, key=lambda item: item[0])
    direction = pattern_direction(swings)
    is_valid = best_score >= 0.45
    details = {"direction": direction.value, "subtype": best_subtype, "wave_lengths": lengths}
    return PatternCheckResult("triangle", is_valid, best_score, best_violations, details=details)
