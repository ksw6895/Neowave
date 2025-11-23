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
from neowave_core.rule_checks import RuleCheck
from neowave_core.rules_loader import TriangleRuleSet, extract_triangle_rules
from neowave_core.swings import Swing


def _evaluate_contracting(lengths: list[float], params: TriangleRuleSet) -> tuple[float, list[str], list[RuleCheck]]:
    violations: list[str] = []
    checks: list[RuleCheck] = []
    penalty = 0.0

    def record(key: str, description: str, value: float | bool, expected: str, condition: bool, weight: float) -> None:
        nonlocal penalty
        checks.append(RuleCheck(key=key, description=description, value=value, expected=expected, passed=condition, penalty=0.0 if condition else weight))
        if condition:
            return
        penalty += weight
        violations.append(description)

    c_ratio = length_ratio(lengths[2], lengths[0])
    e_ratio = length_ratio(lengths[4], lengths[2])
    record(
        "contracting_c_vs_a",
        "Wave C should contract relative to Wave A",
        c_ratio,
        f"<= {max(params.contracting_c_to_a * 1.1, 0.9):.2f}",
        c_ratio <= max(params.contracting_c_to_a * 1.1, 0.9),
        0.25,
    )
    record(
        "contracting_e_vs_c",
        "Wave E not proportionate to Wave C",
        e_ratio,
        f"{params.contracting_e_min:.2f} - {params.contracting_e_max:.2f}",
        params.contracting_e_min <= e_ratio <= params.contracting_e_max,
        0.2,
    )
    record(
        "contracting_b_vs_a",
        "Wave B should be smaller than Wave A",
        lengths[1] - lengths[0],
        "< 0",
        lengths[1] < lengths[0],
        0.1,
    )
    record(
        "contracting_d_vs_c",
        "Wave D should be smaller than Wave C",
        lengths[3] - lengths[2],
        "<= 0",
        lengths[3] <= lengths[2],
        0.1,
    )
    record(
        "contracting_e_vs_c",
        "Wave E should be smaller than Wave C",
        lengths[4] - lengths[2],
        "<= 0",
        lengths[4] <= lengths[2],
        0.1,
    )
    record(
        "contracting_a_gt_c",
        "Wave A should be larger than Wave C in contracting triangle",
        lengths[0] - lengths[2],
        ">= 0",
        lengths[0] >= lengths[2],
        0.2,
    )

    score = max(0.0, 1.0 - penalty)
    return score, violations, checks


def _evaluate_expanding(lengths: list[float], params: TriangleRuleSet) -> tuple[float, list[str], list[RuleCheck]]:
    violations: list[str] = []
    checks: list[RuleCheck] = []
    penalty = 0.0

    def record(key: str, description: str, value: float | bool, expected: str, condition: bool, weight: float) -> None:
        nonlocal penalty
        checks.append(RuleCheck(key=key, description=description, value=value, expected=expected, passed=condition, penalty=0.0 if condition else weight))
        if condition:
            return
        penalty += weight
        violations.append(description)

    record(
        "expanding_c_vs_a",
        "Wave C must expand beyond Wave A",
        length_ratio(lengths[2], lengths[0]),
        f">= {params.expanding_c_min:.2f}",
        length_ratio(lengths[2], lengths[0]) >= params.expanding_c_min,
        0.3,
    )
    record(
        "expanding_e_vs_c",
        "Wave E must expand beyond Wave C",
        length_ratio(lengths[4], lengths[2]),
        f">= {params.expanding_e_min:.2f}",
        length_ratio(lengths[4], lengths[2]) >= params.expanding_e_min,
        0.3,
    )
    record(
        "expanding_b_vs_a",
        "Wave B should be at least as large as Wave A",
        lengths[1] / lengths[0] if lengths[0] else 0.0,
        ">= 1.0",
        lengths[1] >= lengths[0],
        0.1,
    )
    record(
        "expanding_d_vs_b",
        "Wave D should expand beyond Wave B",
        lengths[3] / lengths[1] if lengths[1] else 0.0,
        ">= 1.0",
        lengths[3] >= lengths[1],
        0.1,
    )
    record(
        "expanding_e_blowoff",
        "Wave E blow-off exceeds expanding triangle bounds",
        length_ratio(lengths[4], lengths[2]),
        f"<= {params.expanding_e_max:.2f}",
        length_ratio(lengths[4], lengths[2]) <= params.expanding_e_max,
        0.2,
    )

    score = max(0.0, 1.0 - penalty)
    return score, violations, checks


def _evaluate_neutral(lengths: list[float], params: TriangleRuleSet) -> tuple[float, list[str], list[RuleCheck]]:
    violations: list[str] = []
    checks: list[RuleCheck] = []
    penalty = 0.0

    def record(key: str, description: str, value: float | bool, expected: str, condition: bool, weight: float) -> None:
        nonlocal penalty
        checks.append(RuleCheck(key=key, description=description, value=value, expected=expected, passed=condition, penalty=0.0 if condition else weight))
        if condition:
            return
        penalty += weight
        violations.append(description)

    record(
        "neutral_c_largest",
        "Wave C should be the largest swing in neutral triangle",
        lengths[2],
        "== max(A-E)",
        lengths[2] >= max(lengths),
        0.25,
    )
    a_c_ratio = length_ratio(lengths[0], lengths[2])
    e_c_ratio = length_ratio(lengths[4], lengths[2])
    record(
        "neutral_a_vs_c",
        "Wave A size not aligned with neutral triangle proportions",
        a_c_ratio,
        f"{params.neutral_a_min:.2f} - {params.neutral_a_max:.2f}",
        params.neutral_a_min <= a_c_ratio <= params.neutral_a_max,
        0.2,
    )
    record(
        "neutral_e_vs_c",
        "Wave E size not aligned with neutral triangle proportions",
        e_c_ratio,
        f"{params.neutral_e_min:.2f} - {params.neutral_e_max:.2f}",
        params.neutral_e_min <= e_c_ratio <= params.neutral_e_max,
        0.2,
    )
    record(
        "neutral_similarity",
        "Wave A and E should be similar in size",
        similarity_ratio(lengths[0], lengths[4]),
        f">= {params.similarity_tolerance:.2f}",
        similarity_ratio(lengths[0], lengths[4]) >= params.similarity_tolerance,
        0.15,
    )
    score = max(0.0, 1.0 - penalty)
    return score, violations, checks


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
        score, violations, checks = evaluator(lengths, params)
        candidates.append((score, subtype, violations, checks))

    best_score, best_subtype, best_violations, best_checks = max(candidates, key=lambda item: item[0])
    direction = pattern_direction(swings)
    is_valid = best_score >= 0.45
    details = {"direction": direction.value, "subtype": best_subtype, "wave_lengths": lengths, "rule_checks": best_checks}
    return PatternCheckResult("triangle", is_valid, best_score, best_violations, details=details, rule_checks=best_checks)
