from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from neowave_core.parser import ParseSettings, parse_wave_tree
from neowave_core.wave_tree import build_wave_tree_from_parsed, serialize_wave_tree

import numpy as np

from neowave_core.models import WaveNode, WaveTree
from neowave_core.rule_checks import RuleCheck
from neowave_core.swings import Swing


@dataclass(slots=True)
class ScenarioRuleScore:
    score: float
    violations: list[str]
    evidence: list[RuleCheck]


def _typical_scale(swings: Sequence[Swing]) -> float:
    ratios = []
    for swing in swings:
        if swing.duration <= 0:
            continue
        ratios.append(swing.price_range / swing.duration)
    if not ratios:
        return 1.0
    return float(np.median(ratios))


def _node_window(swings: Sequence[Swing], node: WaveNode) -> list[Swing]:
    if not swings:
        return []
    start = max(0, min(node.start_idx, node.end_idx))
    end = min(len(swings) - 1, max(node.start_idx, node.end_idx))
    return list(swings[start : end + 1])


def _annotate_metrics(node: WaveNode, swings: Sequence[Swing], typical_scale: float) -> None:
    window = _node_window(swings, node)
    if not window:
        node.box_ratio = None
        node.energy_metric = None
        return
    time_range = (window[-1].end_time - window[0].start_time).total_seconds()
    price_range = max(sw.high for sw in window) - min(sw.low for sw in window)
    avg_volume = sum(sw.volume for sw in window) / len(window)
    scale = typical_scale if typical_scale > 0 else 1.0
    node.box_ratio = price_range / (max(time_range, 1.0) * scale)
    node.energy_metric = price_range * max(time_range, 1.0) * max(avg_volume, 1.0)


def _annotate_tree(node: WaveNode, swings: Sequence[Swing], typical_scale: float) -> None:
    _annotate_metrics(node, swings, typical_scale)
    for child in node.sub_waves:
        _annotate_tree(child, swings, typical_scale)


def _rule_check(key: str, description: str, value: float | bool, expected: str, passed: bool, penalty: float) -> RuleCheck:
    return RuleCheck(
        key=key,
        description=description,
        value=value,
        expected=expected,
        passed=passed,
        penalty=penalty if not passed else 0.0,
    )


def _adjacent_similarity(children: Sequence[WaveNode], threshold: float) -> tuple[float, list[RuleCheck]]:
    evidence: list[RuleCheck] = []
    penalty = 0.0
    for left, right in zip(children, children[1:]):
        price_ratio = min(left.length, right.length) / max(left.length, right.length) if max(left.length, right.length) else 1.0
        time_ratio = min(left.duration, right.duration) / max(left.duration, right.duration) if max(left.duration, right.duration) else 1.0
        passed = price_ratio >= threshold or time_ratio >= threshold
        evidence.append(_rule_check("similarity", "Adjacency price/time similarity", min(price_ratio, time_ratio), f">= {threshold:.2f}", passed, 0.05))
        if not passed:
            penalty += 0.05
    return penalty, evidence


def _impulse_rules(node: WaveNode, threshold: float) -> tuple[float, list[str], list[RuleCheck]]:
    if len(node.sub_waves) != 5:
        return 0.0, [], []
    evidence: list[RuleCheck] = []
    hard: list[str] = []
    penalty = 0.0
    lengths = [child.length for child in node.sub_waves]
    durations = [child.duration for child in node.sub_waves]

    w2_ratio = lengths[1] / lengths[0] if lengths[0] else 0.0
    passed_w2 = w2_ratio < 1.0
    evidence.append(_rule_check("impulse_w2_lt_100", "Wave 2 retrace < 100% of Wave 1", w2_ratio, "< 1.0", passed_w2, 0.4))
    if not passed_w2:
        hard.append("Impulse invalid: Wave 2 retraced 100%+ of Wave 1")
    w3_shortest = lengths[2] < min(lengths[0], lengths[4])
    evidence.append(_rule_check("impulse_w3_shortest", "Wave 3 not shortest motive wave", lengths[2], f">= min(w1,w5) {min(lengths[0], lengths[4]):.2f}", not w3_shortest, 0.6))
    if w3_shortest:
        hard.append("Impulse invalid: Wave 3 shortest motive wave")
    sorted_lengths = sorted(lengths)
    extension_ratio = sorted_lengths[-1] / sorted_lengths[-2] if sorted_lengths[-2] else 0.0
    passed_extension = extension_ratio >= 1.4  # lenient vs 1.618
    evidence.append(_rule_check("impulse_extension", "Impulse extension present", extension_ratio, ">= 1.40", passed_extension, 0.15))
    if not passed_extension:
        penalty += 0.1

    # Alternation time heuristic.
    alt_ratio = (durations[3] / durations[1]) if durations[1] else 0.0
    alt_pass = alt_ratio >= 0.5 and alt_ratio <= 2.5
    evidence.append(_rule_check("impulse_alternation", "Wave 2/4 time alternation", alt_ratio, "0.5~2.5x", alt_pass, 0.1))
    if not alt_pass:
        penalty += 0.05

    return penalty, hard, evidence


def _zigzag_rules(node: WaveNode) -> tuple[float, list[str], list[RuleCheck]]:
    if len(node.sub_waves) != 3:
        return 0.0, [], []
    lengths = [child.length for child in node.sub_waves]
    evidence: list[RuleCheck] = []
    hard: list[str] = []
    penalty = 0.0

    b_ratio = lengths[1] / lengths[0] if lengths[0] else 0.0
    passed_b = b_ratio < 0.7
    evidence.append(_rule_check("zigzag_b_ratio", "Zigzag: B retrace < 61.8%", b_ratio, "< 0.618~0.70", passed_b, 0.4))
    if not passed_b:
        hard.append("Zigzag invalid: B too deep")
    c_ratio = lengths[2] / lengths[0] if lengths[0] else 0.0
    passed_c = c_ratio >= 0.382
    evidence.append(_rule_check("zigzag_c_ratio", "Zigzag: C length >= 0.382 A", c_ratio, ">= 0.382", passed_c, 0.2))
    if not passed_c:
        penalty += 0.1
    return penalty, hard, evidence


def _flat_rules(node: WaveNode) -> tuple[float, list[str], list[RuleCheck]]:
    if len(node.sub_waves) != 3:
        return 0.0, [], []
    lengths = [child.length for child in node.sub_waves]
    evidence: list[RuleCheck] = []
    hard: list[str] = []
    penalty = 0.0

    b_ratio = lengths[1] / lengths[0] if lengths[0] else 0.0
    passed_b = b_ratio >= 0.6
    evidence.append(_rule_check("flat_b_ratio", "Flat: B retrace >= 61.8%", b_ratio, ">= 0.618", passed_b, 0.5))
    if not passed_b:
        hard.append("Flat invalid: B too shallow")
    c_ratio = lengths[2] / lengths[1] if lengths[1] else 0.0
    passed_c = c_ratio >= 0.382
    evidence.append(_rule_check("flat_c_ratio", "Flat: C length >= 38.2% of B", c_ratio, ">= 0.382", passed_c, 0.1))
    if not passed_c:
        penalty += 0.05
    return penalty, hard, evidence


def _triangle_rules(node: WaveNode, threshold: float) -> tuple[float, list[str], list[RuleCheck]]:
    if len(node.sub_waves) != 5:
        return 0.0, [], []
    evidence: list[RuleCheck] = []
    penalty, sim_evidence = _adjacent_similarity(node.sub_waves, threshold)
    evidence.extend(sim_evidence)
    lengths = [child.length for child in node.sub_waves]
    c_vs_a = lengths[2] / lengths[0] if lengths[0] else 0.0
    passed_c = c_vs_a <= 1.618
    evidence.append(_rule_check("triangle_c_vs_a", "Triangle: C not dramatically larger than A", c_vs_a, "<= 1.618", passed_c, 0.2))
    hard: list[str] = []
    if not passed_c:
        hard.append("Triangle invalid: C too large relative to A")
    return penalty, hard, evidence


def _complexity_penalty(node: WaveNode) -> float:
    if node.pattern_type.lower() == "triplethree":
        return 0.2
    if node.pattern_type.lower() == "doublethree":
        return 0.1
    return 0.0


def _micro_analysis(
    node: WaveNode,
    micro_swings: Sequence[Swing],
    similarity_threshold: float,
    rules: dict[str, Any] | None,
) -> dict[str, object] | None:
    window = [sw for sw in micro_swings if node.start_time <= sw.start_time and sw.end_time <= node.end_time]
    if not window:
        return {"scale": "micro", "score": 0.0, "violations": ["No micro swings in node window"], "swing_count": 0}

    swing_count = len(window)
    alternating = all(window[i].direction != window[i - 1].direction for i in range(1, len(window)))
    score = 1.0
    violations: list[str] = []

    micro_pattern: dict[str, Any] | None = None
    if rules is not None and swing_count >= 3:
        try:
            micro_tree = parse_wave_tree(window, rules, settings=ParseSettings(similarity_threshold=similarity_threshold))
            if micro_tree.roots:
                micro_root = micro_tree.roots[0]
                micro_ui_tree = build_wave_tree_from_parsed(micro_root)
                micro_pattern = {
                    "pattern_type": micro_root.pattern_type,
                    "score": micro_root.score,
                    "wave_count": len(micro_root.sub_waves),
                    "swing_indices": (micro_root.start_idx, micro_root.end_idx),
                    "wave_tree": serialize_wave_tree(micro_ui_tree),
                }
        except Exception:
            micro_pattern = None

    parent_type = node.pattern_type.lower()
    if parent_type in {"impulse", "terminalimpulse", "terminal_impulse"}:
        if swing_count < 5:
            score -= 0.4
            violations.append("Micro structure lacks 5 legs for impulse")
        if not alternating:
            score -= 0.2
            violations.append("Micro swings do not alternate for impulse")
        if micro_pattern and micro_pattern.get("pattern_type", "").lower() not in {"impulse", "terminalimpulse", "terminal_impulse"}:
            score -= 0.25
            violations.append("Micro pattern not motive while parent is impulse")
        if micro_pattern and micro_pattern.get("wave_count", 0) < 5:
            score -= 0.1
            violations.append("Micro impulse subdivision incomplete")
    elif parent_type == "triangle":
        if swing_count < 5:
            score -= 0.25
            violations.append("Triangle leg lacks 5 micro swings")
        if not alternating:
            score -= 0.1
            violations.append("Triangle micro swings not alternating")
        if micro_pattern and micro_pattern.get("pattern_type", "").lower() != "triangle":
            score -= 0.1
            violations.append("Micro pattern not triangular")
    else:
        if swing_count < 3:
            score -= 0.2
            violations.append("Micro structure too small for correction")
        if not alternating:
            score -= 0.1
            violations.append("Micro swings do not alternate for correction")

    similarity_penalty, _ = _adjacent_similarity([WaveNode.from_swing(idx, sw) for idx, sw in enumerate(window)], similarity_threshold)
    score -= similarity_penalty

    avg_len = float(np.mean([sw.length for sw in window])) if window else 0.0
    avg_time = float(np.mean([sw.duration for sw in window])) if window else 0.0
    ratios: dict[str, float] = {}
    if avg_len > 0:
        ratios["price_ratio"] = node.length / avg_len
    if avg_time > 0:
        ratios["time_ratio"] = node.duration / avg_time
    if ratios and (ratios.get("price_ratio", 0.0) < 3.0 or ratios.get("time_ratio", 0.0) < 3.0):
        score -= 0.05
        violations.append("Macro/micro separation < 3x on price/time")

    score = max(0.0, min(1.0, score))
    result = {
        "scale": "micro",
        "score": round(score, 3),
        "violations": violations,
        "swing_count": swing_count,
        "alternating": alternating,
    }
    if micro_pattern:
        result["pattern"] = micro_pattern
    if ratios:
        result["scale_ratio"] = ratios
    return result


def _attach_micro_to_tree(node: WaveNode, micro_swings: Sequence[Swing], similarity_threshold: float, rules: dict[str, Any] | None) -> None:
    node.sub_scale_analysis = _micro_analysis(node, micro_swings, similarity_threshold, rules) if micro_swings else None
    for child in node.sub_waves:
        _attach_micro_to_tree(child, micro_swings, similarity_threshold, rules)


def _score_node(node: WaveNode, similarity_threshold: float) -> tuple[float, list[str], list[RuleCheck]]:
    penalty = 0.0
    hard: list[str] = []
    evidence: list[RuleCheck] = []

    pattern = node.pattern_type.lower()
    if pattern in {"impulse", "terminalimpulse", "terminal_impulse"}:
        p, h, ev = _impulse_rules(node, similarity_threshold)
        penalty += p
        hard.extend(h)
        evidence.extend(ev)
    elif pattern == "zigzag":
        p, h, ev = _zigzag_rules(node)
        penalty += p
        hard.extend(h)
        evidence.extend(ev)
    elif pattern == "flat":
        p, h, ev = _flat_rules(node)
        penalty += p
        hard.extend(h)
        evidence.extend(ev)
    elif pattern == "triangle":
        p, h, ev = _triangle_rules(node, similarity_threshold)
        penalty += p
        hard.extend(h)
        evidence.extend(ev)

    sim_penalty, sim_evidence = _adjacent_similarity(node.sub_waves, similarity_threshold)
    penalty += sim_penalty
    evidence.extend(sim_evidence)

    if node.box_ratio is not None:
        balanced = 0.5 <= node.box_ratio <= 2.0
        evidence.append(_rule_check("box_ratio", "Time-Price balance (box ratio)", node.box_ratio, "0.5~2.0", balanced, 0.1))
        if not balanced:
            penalty += 0.05

    if node.sub_scale_analysis:
        micro_score = float(node.sub_scale_analysis.get("score", 1.0) or 0.0)
        micro_violations = node.sub_scale_analysis.get("violations") or []
        evidence.append(_rule_check("micro_consistency", "Micro consistency with parent", micro_score, ">= 0.7", micro_score >= 0.7, 0.15))
        if micro_violations:
            evidence.append(
                _rule_check(
                    "micro_detail",
                    "; ".join(micro_violations[:3]),
                    len(micro_violations),
                    "0",
                    False,
                    min(0.15, 0.03 * len(micro_violations)),
                )
            )
        if micro_score < 0.7:
            penalty += 0.1 + min(0.1, 0.02 * len(micro_violations))

    # Recurse into children to accumulate penalties (lighter weight).
    for child in node.sub_waves:
        child_penalty, child_hard, child_ev = _score_node(child, similarity_threshold)
        penalty += 0.5 * child_penalty
        hard.extend(child_hard)
        evidence.extend(child_ev)

    penalty += _complexity_penalty(node)
    return penalty, hard, evidence


def score_scenario_with_neowave_rules(
    tree: WaveTree,
    swings: Sequence[Swing],
    rules: dict[str, Any] | None = None,
    micro_swings: Sequence[Swing] | None = None,
    similarity_threshold: float = 0.33,
) -> ScenarioRuleScore:
    swing_list = list(swings)
    typical_scale = _typical_scale(swing_list)

    if micro_swings:
        micro_list = list(micro_swings)
    else:
        micro_list = []

    evidence: list[RuleCheck] = []
    hard: list[str] = []
    penalty = 0.0
    base_scores = []

    for root in tree.roots:
        _annotate_tree(root, swing_list, typical_scale)
        if micro_list:
            _attach_micro_to_tree(root, micro_list, similarity_threshold, rules)
        node_penalty, node_hard, node_evidence = _score_node(root, similarity_threshold)
        penalty += node_penalty
        hard.extend(node_hard)
        evidence.extend(node_evidence)
        base_scores.append(max(root.score, 0.2))

    if hard:
        return ScenarioRuleScore(score=0.0, violations=hard, evidence=evidence)

    structural_score = float(np.mean(base_scores)) if base_scores else 0.0
    final_score = max(0.0, min(1.0, structural_score - penalty))
    return ScenarioRuleScore(score=final_score, violations=hard, evidence=evidence)
