from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from neowave_core.models import Monowave, PatternValidation, Scenario, WaveNode
from neowave_core.pattern_evaluator import PatternEvaluator
from neowave_core.patterns.metrics import compute_metrics_for_pattern, infer_net_direction, is_alternating_directions
from neowave_core.rules_db import RULE_DB, load_rule_db

# Global id generators to keep wave/scenario ids stable during a run.
_wave_id_counter = itertools.count(10_000)
_scenario_id_counter = itertools.count(1)


@dataclass(slots=True)
class PatternMatch:
    pattern_type: str
    subtype: str | None
    start_index: int
    end_index: int
    wave_nodes: list[WaveNode]
    validation: PatternValidation
    metrics: dict[str, float]
    score: float


def _new_wave_id() -> int:
    return next(_wave_id_counter)


def _new_scenario_id() -> int:
    return next(_scenario_id_counter)


def wrap_monowaves(monowaves: Iterable[Monowave]) -> list[WaveNode]:
    return [WaveNode.from_monowave(mw) for mw in monowaves]


def _pattern_score(validation: PatternValidation, pattern_type: str) -> float:
    """Lower is better; soft_score plus small complexity premium."""
    complexity_penalty = 0.1 if pattern_type in {"DoubleThree", "TripleThree"} else 0.0
    base_bias = {
        "Impulse": 0.02,
        "Zigzag": 0.05,
        "Flat": 0.06,
        "Triangle": 0.08,
    }.get(pattern_type, 0.05)
    return base_bias + validation.soft_score + complexity_penalty + 0.01 * len(validation.violated_soft_rules)


def try_impulse(window: list[WaveNode], evaluator: PatternEvaluator) -> PatternMatch | None:
    if len(window) != 5 or not is_alternating_directions(window):
        return None
    validation, metrics = evaluator.evaluate("Impulse", "TrendingImpulse", window, context=compute_metrics_for_pattern("Impulse", "TrendingImpulse", window))
    if validation.hard_valid:
        score = _pattern_score(validation, "Impulse")
        return PatternMatch("Impulse", "TrendingImpulse", window[0].start_idx, window[-1].end_idx, window, validation, metrics, score)
    term_validation, term_metrics = evaluator.evaluate("Impulse", "TerminalImpulse", window, context=compute_metrics_for_pattern("Impulse", "TerminalImpulse", window))
    if term_validation.hard_valid:
        score = _pattern_score(term_validation, "Impulse") + 0.05
        return PatternMatch("Impulse", "TerminalImpulse", window[0].start_idx, window[-1].end_idx, window, term_validation, term_metrics, score)
    return None


def try_zigzag(window: list[WaveNode], evaluator: PatternEvaluator) -> PatternMatch | None:
    if len(window) != 3 or not is_alternating_directions(window):
        return None
    validation, metrics = evaluator.evaluate("Zigzag", "Standard", window, context=compute_metrics_for_pattern("Zigzag", "Standard", window))
    if validation.hard_valid:
        score = _pattern_score(validation, "Zigzag")
        return PatternMatch("Zigzag", "Standard", window[0].start_idx, window[-1].end_idx, window, validation, metrics, score)
    return None


def try_flat(window: list[WaveNode], evaluator: PatternEvaluator) -> PatternMatch | None:
    if len(window) != 3 or not is_alternating_directions(window):
        return None
    candidates: list[PatternMatch] = []
    for subtype in ["Normal", "Expanded", "Running"]:
        validation, metrics = evaluator.evaluate("Flat", subtype, window, context=compute_metrics_for_pattern("Flat", subtype, window))
        if validation.hard_valid:
            score = _pattern_score(validation, "Flat")
            candidates.append(PatternMatch("Flat", subtype, window[0].start_idx, window[-1].end_idx, window, validation, metrics, score))
    if not candidates:
        return None
    return min(candidates, key=lambda c: c.score)


def try_triangle(window: list[WaveNode], evaluator: PatternEvaluator) -> PatternMatch | None:
    if len(window) < 5:
        return None
    total_move = sum(abs(w.abs_price_change) for w in window) or 1.0
    net_move = abs(window[-1].end_price - window[0].start_price)
    # Triangles should be relatively sideways; strong net move biases toward impulse/correction.
    if net_move / total_move > 0.35:
        return None
    candidates: list[PatternMatch] = []
    for subtype in ["Contracting", "Expanding", "Neutral"]:
        validation, metrics = evaluator.evaluate("Triangle", subtype, window, context=compute_metrics_for_pattern("Triangle", subtype, window))
        if validation.hard_valid:
            score = _pattern_score(validation, "Triangle")
            candidates.append(PatternMatch("Triangle", subtype, window[0].start_idx, window[-1].end_idx, window, validation, metrics, score))
    if not candidates:
        return None
    return min(candidates, key=lambda c: c.score)


def try_complex_patterns(_nodes: list[WaveNode], _evaluator: PatternEvaluator) -> list[PatternMatch]:
    # Placeholder for DoubleThree / Diametric / Symmetrical per the guideline's phased rollout.
    return []


def find_all_local_patterns(nodes: list[WaveNode], evaluator: PatternEvaluator) -> list[PatternMatch]:
    matches: list[PatternMatch] = []
    n = len(nodes)
    for i in range(n - 4):
        window = nodes[i : i + 5]
        impulse = try_impulse(window, evaluator)
        if impulse:
            matches.append(impulse)
        tri = try_triangle(window, evaluator)
        if tri:
            matches.append(tri)
    for i in range(n - 2):
        window = nodes[i : i + 3]
        zz = try_zigzag(window, evaluator)
        if zz:
            matches.append(zz)
        fl = try_flat(window, evaluator)
        if fl:
            matches.append(fl)
    matches.extend(try_complex_patterns(nodes, evaluator))
    return matches


def enumerate_non_overlapping_sets(candidates: list[PatternMatch], beam_width: int = 6) -> list[list[PatternMatch]]:
    """Beam-search combinations of non-overlapping patterns ordered by score."""
    sorted_cands = sorted(candidates, key=lambda c: (c.end_index, c.start_index))
    beams: list[tuple[list[PatternMatch], int, float, int]] = [([], -1, 0.0, 0)]
    for cand in sorted_cands:
        next_beams: list[tuple[list[PatternMatch], int, float]] = []
        for combo, last_end, score, covered in beams:
            next_beams.append((combo, last_end, score, covered))
            if cand.start_index > last_end:
                new_combo = combo + [cand]
                new_score = score + cand.score
                new_covered = covered + (cand.end_index - cand.start_index + 1)
                next_beams.append((new_combo, cand.end_index, new_score, new_covered))
        beams = sorted(next_beams, key=lambda item: (item[2], -item[3]))[:beam_width]
    return [combo for combo, _, _, _ in beams if combo]


def build_wavenode_from_match(pm: PatternMatch) -> WaveNode:
    children = pm.wave_nodes
    return WaveNode(
        id=_new_wave_id(),
        level=max(c.level for c in children) + 1 if children else 1,
        degree_label=None,
        start_idx=children[0].start_idx,
        end_idx=children[-1].end_idx,
        start_time=children[0].start_time,
        end_time=children[-1].end_time,
        high_price=max(c.high_price for c in children),
        low_price=min(c.low_price for c in children),
        start_price=children[0].start_price,
        end_price=children[-1].end_price,
        direction=infer_net_direction(children),
        children=list(children),
        pattern_type=pm.pattern_type,
        pattern_subtype=pm.subtype,
        metrics=pm.metrics,
        validation=pm.validation,
        score=pm.score,
        label=pm.pattern_type,
    )


def collapse_nodes(nodes: list[WaveNode], pattern_matches: list[PatternMatch]) -> list[WaveNode]:
    result: list[WaveNode] = []
    i = 0
    while i < len(nodes):
        start_idx = nodes[i].start_idx
        candidates = [pm for pm in pattern_matches if pm.start_index == start_idx]
        if not candidates:
            result.append(nodes[i])
            i += 1
            continue
        match = max(candidates, key=lambda pm: pm.end_index)
        result.append(build_wavenode_from_match(match))
        # Skip nodes covered by this match.
        while i < len(nodes) and nodes[i].end_idx <= match.end_index:
            i += 1
    return result


def expand_one_level(scenario: Scenario, evaluator: PatternEvaluator, beam_width: int = 6) -> tuple[bool, list[Scenario]]:
    nodes = scenario.root_nodes
    candidates = find_all_local_patterns(nodes, evaluator)
    if not candidates:
        return False, [scenario]
    new_scenarios: list[Scenario] = []
    for combo in enumerate_non_overlapping_sets(candidates, beam_width=beam_width):
        new_nodes = collapse_nodes(nodes, combo)
        new_score = scenario.global_score + sum(pm.score for pm in combo)
        new_scenario = Scenario(
            id=_new_scenario_id(),
            root_nodes=new_nodes,
            global_score=new_score,
            status="active",
            invalidation_reasons=list(scenario.invalidation_reasons),
        )
        new_scenarios.append(new_scenario)
    return True, new_scenarios


def _traverse(nodes: Iterable[WaveNode]) -> Iterable[WaveNode]:
    for node in nodes:
        yield node
        if node.children:
            yield from _traverse(node.children)


def _group_by_level(nodes: Iterable[WaveNode]) -> dict[int, list[WaveNode]]:
    grouped: dict[int, list[WaveNode]] = {}
    for node in _traverse(nodes):
        grouped.setdefault(node.level, []).append(node)
    return grouped


def _check_similarity_balance(level_nodes: list[WaveNode]) -> float:
    penalty = 0.0
    for left, right in zip(level_nodes, level_nodes[1:]):
        price_ratio = min(left.abs_price_change, right.abs_price_change) / max(left.abs_price_change, right.abs_price_change) if max(left.abs_price_change, right.abs_price_change) else 1.0
        time_ratio = min(left.duration, right.duration) / max(left.duration, right.duration) if max(left.duration, right.duration) else 1.0
        if price_ratio < 0.33 and time_ratio < 0.33:
            penalty += 0.3
    return penalty


def _validate_node_internal_structure(node: WaveNode, scenario: Scenario) -> float:
    penalty = 0.0
    ptype = (node.pattern_type or "").lower()
    if ptype == "impulse":
        if len(node.children) != 5:
            scenario.status = "invalidated"
            scenario.invalidation_reasons.append("Impulse must have 5 subwaves")
            return penalty
        motive_ok = {"impulse", "terminalimpulse", "monowave"}
        corrective_ok = {"zigzag", "flat", "triangle", "monowave"}
        for idx in (0, 2, 4):
            if (node.children[idx].pattern_type or "").lower() not in motive_ok:
                penalty += 0.4
        for idx in (1, 3):
            if (node.children[idx].pattern_type or "").lower() not in corrective_ok:
                penalty += 0.2
    if ptype == "zigzag":
        if len(node.children) != 3:
            scenario.status = "invalidated"
            scenario.invalidation_reasons.append("Zigzag must have 3 subwaves")
            return penalty
        if (node.children[0].pattern_type or "").lower() not in {"impulse", "terminalimpulse", "monowave"}:
            penalty += 0.25
        if (node.children[2].pattern_type or "").lower() not in {"impulse", "terminalimpulse", "monowave"}:
            penalty += 0.25
    if ptype == "flat":
        if len(node.children) != 3:
            scenario.status = "invalidated"
            scenario.invalidation_reasons.append("Flat must have 3 subwaves")
            return penalty
    if ptype == "triangle":
        if len(node.children) < 5:
            scenario.status = "invalidated"
            scenario.invalidation_reasons.append("Triangle must have 5+ legs")
            return penalty
    return penalty


def _check_thermodynamic_balance(node: WaveNode) -> float:
    if not node.children:
        return 0.0
    parent_energy = node.abs_price_change * max(node.duration, 1.0)
    child_energy = sum(child.abs_price_change * max(child.duration, 1.0) for child in node.children)
    if child_energy <= 0:
        return 0.0
    ratio = parent_energy / child_energy
    if ratio < 0.5 or ratio > 2.5:
        return 0.1
    return 0.0


def validate_and_score_scenario(scenario: Scenario) -> Scenario:
    penalty = 0.0
    penalty += 0.05 * len(scenario.root_nodes)
    grouped = _group_by_level(scenario.root_nodes)
    for level_nodes in grouped.values():
        penalty += _check_similarity_balance(sorted(level_nodes, key=lambda n: n.start_idx))

    for node in _traverse(scenario.root_nodes):
        penalty += _validate_node_internal_structure(node, scenario)
        penalty += _check_thermodynamic_balance(node)

    base_score = sum(max(node.score, 0.0) for node in _traverse(scenario.root_nodes))
    scenario.global_score = base_score + penalty
    if scenario.status != "active":
        scenario.global_score += 10.0
    return scenario


def prune_scenarios(scenarios: list[Scenario], beam_width: int = 6) -> list[Scenario]:
    return sorted(scenarios, key=lambda sc: sc.global_score)[:beam_width]


def analyze_market_structure(
    monowaves: Sequence[Monowave],
    rule_db: dict[str, Any] | None = None,
    beam_width: int = 6,
) -> list[Scenario]:
    if not monowaves:
        return []
    nodes = wrap_monowaves(monowaves)
    evaluator = PatternEvaluator(load_rule_db(rule_db) if rule_db is not None else RULE_DB)
    scenarios: list[Scenario] = [Scenario(id=_new_scenario_id(), root_nodes=nodes, global_score=0.0, status="active", invalidation_reasons=[])]

    while True:
        any_changed = False
        new_scenarios: list[Scenario] = []
        for sc in scenarios:
            changed, expanded = expand_one_level(sc, evaluator, beam_width=beam_width)
            if changed:
                any_changed = True
                new_scenarios.extend(expanded)
            else:
                new_scenarios.append(sc)
        scenarios = prune_scenarios(new_scenarios, beam_width=beam_width)
        if not any_changed:
            break

    validated = [validate_and_score_scenario(sc) for sc in scenarios]
    return sorted(validated, key=lambda sc: sc.global_score)


def collect_level_nodes(root_nodes: Sequence[WaveNode], level: int) -> list[WaveNode]:
    collected: list[WaveNode] = []

    def _walk(node: WaveNode) -> None:
        if node.level == level:
            collected.append(node)
        for child in node.children:
            _walk(child)

    for root in root_nodes:
        _walk(root)
    return sorted(collected, key=lambda n: n.start_idx)


def count_nodes_by_level(root_nodes: Sequence[WaveNode]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for node in _traverse(root_nodes):
        counts[node.level] = counts.get(node.level, 0) + 1
    return counts


def get_view_nodes(root_nodes: Sequence[WaveNode], target_wave_count: int) -> list[WaveNode]:
    counts = count_nodes_by_level(root_nodes)
    if not counts:
        return []
    best_level = min(counts.keys(), key=lambda lvl: abs(counts[lvl] - target_wave_count))
    return collect_level_nodes(root_nodes, level=best_level)


def find_node_by_id(root_nodes: Sequence[WaveNode], node_id: int) -> WaveNode | None:
    for node in _traverse(root_nodes):
        if node.id == node_id:
            return node
    return None


def verify_pattern(
    macro_node: WaveNode,
    micro_monowaves: Sequence[Monowave],
    rule_db: dict[str, Any] | None = None,
) -> PatternValidation:
    """
    Verify if the micro structure supports the macro pattern hypothesis.
    
    Args:
        macro_node: The high-level node (e.g. Impulse) to verify.
        micro_monowaves: The detailed monowaves covering the same period.
        rule_db: Rules database.
        
    Returns:
        PatternValidation result.
    """
    # 1. Slice micro waves to match macro node time range
    # We assume micro_monowaves are sorted by time
    start_time = macro_node.start_time
    end_time = macro_node.end_time
    
    # Filter waves that fall within the macro node's duration
    # We include waves that partially overlap if they are relevant?
    # Strict containment is safer for verification.
    subset = [
        mw for mw in micro_monowaves 
        if mw.start_time >= start_time and mw.end_time <= end_time
    ]
    
    if not subset:
        return PatternValidation(
            hard_valid=False, 
            soft_score=100.0, 
            violated_hard_rules=["No micro data found for verification"]
        )
        
    # 2. Analyze the subset
    # We run the standard analysis on this subset
    # Use a higher beam_width for verification as we are dealing with a smaller subset
    # and want to ensure we find the correct pattern if it exists.
    scenarios = analyze_market_structure(subset, rule_db=rule_db, beam_width=10)
    
    if not scenarios:
        return PatternValidation(
            hard_valid=False,
            soft_score=100.0,
            violated_hard_rules=["Analysis failed to find any valid structure"]
        )
        
    best_scenario = scenarios[0]
    
    # 3. Check if the dominant pattern matches the macro hypothesis
    # The best scenario might consist of multiple root nodes if it couldn't be collapsed into one.
    # If macro_node is "Impulse", we expect the best scenario to be a single "Impulse" node
    # OR a sequence that forms an Impulse (which analyze_market_structure should have collapsed).
    
    roots = best_scenario.root_nodes
    
    # If we have a single root, check its type
    if len(roots) == 1:
        root = roots[0]
        if root.pattern_type == macro_node.pattern_type:
            # Match!
            # We can also check subtype if needed, but pattern_type is the main check.
            return PatternValidation(
                hard_valid=True,
                soft_score=best_scenario.global_score,
                satisfied_rules=[f"Micro structure confirms {macro_node.pattern_type}"]
            )
        else:
            # Mismatch
            return PatternValidation(
                hard_valid=False,
                soft_score=50.0 + best_scenario.global_score,
                violated_hard_rules=[f"Expected {macro_node.pattern_type}, found {root.pattern_type}"]
            )
            
    # If we have multiple roots, it means the engine couldn't collapse them into one pattern.
    # This implies the macro hypothesis (that it IS one pattern) is likely wrong
    # OR the micro view is too noisy/complex.
    return PatternValidation(
        hard_valid=False,
        soft_score=80.0,
        violated_hard_rules=[f"Micro structure did not form a single {macro_node.pattern_type} pattern (found {len(roots)} fragments)"]
    )
