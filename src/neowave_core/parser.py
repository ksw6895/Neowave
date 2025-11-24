from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Sequence

from neowave_core.models import WaveNode
from neowave_core.patterns import (
    is_double_three,
    is_flat,
    is_impulse,
    is_terminal_impulse,
    is_triangle,
    is_triple_three,
    is_zigzag,
)
from neowave_core.rules_loader import (
    FlatRuleSet,
    ImpulseRuleSet,
    TerminalImpulseRuleSet,
    TriangleRuleSet,
    ZigzagRuleSet,
    extract_flat_rules,
    extract_impulse_rules,
    extract_terminal_impulse_rules,
    extract_triangle_rules,
    extract_zigzag_rules,
)
from neowave_core.swings import Swing

DEGREE_SCALE = ["Micro", "Subminuette", "Minuette", "Minute", "Minor", "Intermediate", "Primary"]


@dataclass(slots=True)
class ParseSettings:
    similarity_threshold: float = 0.33
    complexity_cap: int = 3


@dataclass(slots=True)
class RuleContext:
    impulse: ImpulseRuleSet
    terminal: TerminalImpulseRuleSet
    zigzag: ZigzagRuleSet
    flat: FlatRuleSet
    triangle: TriangleRuleSet
    combination: dict[str, Any]
    similarity_threshold: float = 0.33


def _degree_for_level(level: int) -> str:
    if level < len(DEGREE_SCALE):
        return DEGREE_SCALE[level]
    return f"Degree{level}"


def _anchor_label(swings: Sequence[Swing]) -> str | None:
    if not swings:
        return None
    min_idx = min(range(len(swings)), key=lambda idx: swings[idx].low)
    max_idx = max(range(len(swings)), key=lambda idx: swings[idx].high)
    anchor_idx = min_idx if swings[min_idx].start_time <= swings[max_idx].start_time else max_idx
    anchor_type = "GlobalMin" if anchor_idx == min_idx else "GlobalMax"
    anchor_price = swings[anchor_idx].low if anchor_idx == min_idx else swings[anchor_idx].high
    return f"{anchor_type}@{anchor_price:.2f}"


def _uniform_degree(nodes: Sequence[WaveNode]) -> bool:
    return len({node.degree_level for node in nodes}) == 1


def _similarity_ok(nodes: Sequence[WaveNode], threshold: float) -> bool:
    if len(nodes) < 2:
        return True
    for left, right in zip(nodes, nodes[1:]):
        price_ratio = min(left.length, right.length) / max(left.length, right.length) if max(left.length, right.length) else 1.0
        time_ratio = min(left.duration, right.duration) / max(left.duration, right.duration) if max(left.duration, right.duration) else 1.0
        if price_ratio < threshold and time_ratio < threshold:
            return False
    return True


def _role_labels(pattern_type: str, count: int) -> list[str]:
    if pattern_type.lower() in {"impulse", "terminalimpulse", "terminal_impulse"} and count == 5:
        return ["1", "2", "3", "4", "5"]
    if pattern_type.lower() in {"zigzag", "flat"} and count == 3:
        return ["A", "B", "C"]
    if pattern_type.lower() == "triangle" and count == 5:
        return ["a", "b", "c", "d", "e"]
    if pattern_type.lower() == "doublethree" and count == 3:
        return ["W", "X", "Y"]
    if pattern_type.lower() == "triplethree" and count == 5:
        return ["W", "X", "Y", "X2", "Z"]
    return [f"S{i+1}" for i in range(count)]


def _relabel_children(children: list[WaveNode], pattern_type: str) -> list[WaveNode]:
    labels = _role_labels(pattern_type, len(children))
    for child, label in zip(children, labels):
        child.label = label
        child.metadata = {**child.metadata, "wave_label": label, "parent_pattern": pattern_type}
    return children


def _make_node(
    label: str,
    pattern_type: str,
    degree_level: int,
    children: list[WaveNode],
    score: float,
    is_complete: bool,
    details: dict[str, Any] | None,
    invalidation_point: float | None,
) -> WaveNode:
    relabeled = _relabel_children(children, pattern_type)
    start_time = relabeled[0].start_time
    end_time = relabeled[-1].end_time
    start_price = relabeled[0].start_price
    end_price = relabeled[-1].end_price
    return WaveNode(
        label=label,
        pattern_type=pattern_type,
        degree=_degree_for_level(degree_level),
        start_idx=relabeled[0].start_idx,
        end_idx=relabeled[-1].end_idx,
        start_price=start_price,
        end_price=end_price,
        start_time=start_time,
        end_time=end_time,
        high=max(child.high for child in relabeled),
        low=min(child.low for child in relabeled),
        sub_waves=relabeled,
        degree_level=degree_level,
        score=score,
        is_complete=is_complete,
        rules_passed=[pattern_type],
        invalidation_point=invalidation_point,
        metadata={"details": details or {}, "role_labels": [child.label for child in relabeled]},
    )


def _pattern_invalidation(pattern_type: str, children: Sequence[WaveNode]) -> float | None:
    if not children:
        return None
    if pattern_type.lower() in {"impulse", "terminalimpulse", "terminal_impulse"}:
        return children[0].start_price
    if pattern_type.lower() in {"zigzag", "flat", "triangle"}:
        return children[0].start_price
    return None


def _try_merge_five(
    nodes: Sequence[WaveNode],
    ctx: RuleContext,
    degree_level: int,
    tail_end_idx: int,
) -> WaveNode | None:
    if len(nodes) != 5 or not _uniform_degree(nodes):
        return None
    if not _similarity_ok(nodes, ctx.similarity_threshold):
        return None

    impulse_res = is_impulse(nodes, ctx.impulse)
    terminal_res = is_terminal_impulse(nodes, ctx.terminal)
    triangle_res = is_triangle(nodes, ctx.triangle)
    candidates = [
        ("Impulse", impulse_res),
        ("TerminalImpulse", terminal_res),
        ("Triangle", triangle_res),
    ]
    best_label, best_res = max(candidates, key=lambda item: item[1].score)
    if best_res.score < 0.45:
        return None
    is_complete = nodes[-1].end_idx < tail_end_idx
    invalidation = _pattern_invalidation(best_label, nodes)
    return _make_node(
        label=best_label,
        pattern_type=best_label,
        degree_level=degree_level,
        children=list(nodes),
        score=best_res.score,
        is_complete=is_complete,
        details=best_res.details,
        invalidation_point=invalidation,
    )


def _try_merge_three(
    nodes: Sequence[WaveNode],
    ctx: RuleContext,
    degree_level: int,
    tail_end_idx: int,
) -> WaveNode | None:
    if len(nodes) != 3 or not _uniform_degree(nodes):
        return None
    if not _similarity_ok(nodes, ctx.similarity_threshold):
        return None

    zigzag_res = is_zigzag(nodes, ctx.zigzag)
    flat_res = is_flat(nodes, ctx.flat)
    candidates = [("Zigzag", zigzag_res), ("Flat", flat_res)]
    best_label, best_res = max(candidates, key=lambda item: item[1].score)
    if best_res.score < 0.45:
        return None
    is_complete = nodes[-1].end_idx < tail_end_idx
    invalidation = _pattern_invalidation(best_label, nodes)
    return _make_node(
        label=best_label,
        pattern_type=best_label,
        degree_level=degree_level,
        children=list(nodes),
        score=best_res.score,
        is_complete=is_complete,
        details=best_res.details,
        invalidation_point=invalidation,
    )


def _build_combo_children(
    window: Sequence[WaveNode],
    pattern_type: str,
    degree_level: int,
    details: dict[str, Any],
) -> list[WaveNode]:
    if pattern_type == "DoubleThree":
        w_seg = list(window[:3])
        x_seg = [window[3]]
        y_seg = list(window[4:])
        w_node = _make_node("W", details.get("w_pattern", "Correction"), degree_level, w_seg, 1.0, True, {}, None)
        x_node = _make_node("X", "Connector", degree_level, x_seg, 1.0, True, {}, None)
        y_node = _make_node("Y", details.get("y_pattern", "Correction"), degree_level, y_seg, 1.0, True, {}, None)
        return [w_node, x_node, y_node]
    if pattern_type == "TripleThree":
        w_seg = list(window[:3])
        x1_seg = [window[3]]
        y_seg = list(window[4:7])
        x2_seg = [window[7]]
        z_seg = list(window[8:])
        w_node = _make_node("W", details.get("w_pattern", "Correction"), degree_level, w_seg, 1.0, True, {}, None)
        x1_node = _make_node("X", "Connector", degree_level, x1_seg, 1.0, True, {}, None)
        y_node = _make_node("Y", details.get("y_pattern", "Correction"), degree_level, y_seg, 1.0, True, {}, None)
        x2_node = _make_node("X2", "Connector", degree_level, x2_seg, 1.0, True, {}, None)
        z_node = _make_node("Z", details.get("z_pattern", "Correction"), degree_level, z_seg, 1.0, True, {}, None)
        return [w_node, x1_node, y_node, x2_node, z_node]
    return list(window)


def _try_merge_combinations(
    nodes: Sequence[WaveNode],
    ctx: RuleContext,
    degree_level: int,
    tail_end_idx: int,
) -> WaveNode | None:
    result: WaveNode | None = None
    if len(nodes) == 7 and ctx.combination.get("allow_double", True):
        combo_res = is_double_three(nodes, ctx.combination.get("DoubleThree", {}))
        if combo_res.score >= 0.4:
            children = _build_combo_children(nodes, "DoubleThree", degree_level, combo_res.details or {})
            result = _make_node(
                label="DoubleThree",
                pattern_type="DoubleThree",
                degree_level=degree_level + 1,
                children=children,
                score=combo_res.score,
                is_complete=nodes[-1].end_idx < tail_end_idx,
                details=combo_res.details,
                invalidation_point=_pattern_invalidation("DoubleThree", nodes),
            )
    if len(nodes) == 11 and ctx.combination.get("allow_triple", True):
        combo_res = is_triple_three(nodes, ctx.combination.get("TripleThree", {}))
        if combo_res.score >= 0.4:
            children = _build_combo_children(nodes, "TripleThree", degree_level, combo_res.details or {})
            result = _make_node(
                label="TripleThree",
                pattern_type="TripleThree",
                degree_level=degree_level + 1,
                children=children,
                score=combo_res.score,
                is_complete=nodes[-1].end_idx < tail_end_idx,
                details=combo_res.details,
                invalidation_point=_pattern_invalidation("TripleThree", nodes),
            )
    return result


def _merge_pass(nodes: list[WaveNode], ctx: RuleContext, tail_end_idx: int) -> tuple[list[WaveNode], bool]:
    merged_any = False
    degree_level = nodes[0].degree_level + 1 if nodes else 1
    idx = 0
    new_nodes: list[WaveNode] = []
    while idx < len(nodes):
        merged = False
        window5 = nodes[idx : idx + 5]
        if len(window5) == 5:
            candidate = _try_merge_five(window5, ctx, degree_level, tail_end_idx)
            if candidate:
                new_nodes.append(candidate)
                idx += 5
                merged_any = True
                merged = True
        if not merged:
            window3 = nodes[idx : idx + 3]
            if len(window3) == 3:
                candidate3 = _try_merge_three(window3, ctx, degree_level, tail_end_idx)
                if candidate3:
                    new_nodes.append(candidate3)
                    idx += 3
                    merged_any = True
                    merged = True
        if not merged:
            new_nodes.append(nodes[idx])
            idx += 1
    return new_nodes, merged_any


def _merge_combinations(nodes: list[WaveNode], ctx: RuleContext, tail_end_idx: int) -> tuple[list[WaveNode], bool]:
    merged_any = False
    idx = 0
    new_nodes: list[WaveNode] = []
    while idx < len(nodes):
        merged = False
        window7 = nodes[idx : idx + 7]
        if len(window7) == 7:
            candidate = _try_merge_combinations(window7, ctx, nodes[idx].degree_level, tail_end_idx)
            if candidate:
                new_nodes.append(candidate)
                idx += 7
                merged = True
                merged_any = True
        if not merged:
            window11 = nodes[idx : idx + 11]
            if len(window11) == 11:
                candidate = _try_merge_combinations(window11, ctx, nodes[idx].degree_level, tail_end_idx)
                if candidate:
                    new_nodes.append(candidate)
                    idx += 11
                    merged = True
                    merged_any = True
        if not merged:
            new_nodes.append(nodes[idx])
            idx += 1
    return new_nodes, merged_any


def parse_wave_tree(
    swings: Iterable[Swing],
    rules: dict[str, Any],
    settings: ParseSettings | None = None,
) -> WaveTree:
    """Build a hierarchical WaveTree using bottom-up pattern collapsing."""
    config = settings or ParseSettings()
    swing_list = list(swings)
    leaves: List[WaveNode] = build_wave_leaves(swing_list, degree=_degree_for_level(0))
    tail_end_idx = leaves[-1].end_idx if leaves else -1
    combination_rules = rules.get("Corrections", {}).get("Combination", {})
    combo_allow_double = combination_rules.get("allow_double", True) and config.complexity_cap >= 2
    combo_allow_triple = combination_rules.get("allow_triple", True) and config.complexity_cap >= 3
    combination_config = {
        **combination_rules,
        "allow_double": combo_allow_double,
        "allow_triple": combo_allow_triple,
    }
    ctx = RuleContext(
        impulse=extract_impulse_rules(rules.get("Impulse", {}).get("TrendingImpulse", {})),
        terminal=extract_terminal_impulse_rules(rules.get("Impulse", {}).get("TerminalImpulse", {})),
        zigzag=extract_zigzag_rules(rules.get("Corrections", {}).get("Zigzag", {})),
        flat=extract_flat_rules(rules.get("Corrections", {}).get("Flat", {})),
        triangle=extract_triangle_rules(rules.get("Corrections", {}).get("Triangle", {})),
        combination=combination_config,
        similarity_threshold=config.similarity_threshold,
    )

    current_nodes = leaves
    merged = True
    while merged and len(current_nodes) >= 3:
        current_nodes, merged = _merge_pass(current_nodes, ctx, tail_end_idx)

    # Apply complexity cap: allow up to triple three, else leave as undefined.
    current_nodes, combos_merged = _merge_combinations(current_nodes, ctx, tail_end_idx)
    if not combos_merged and len(current_nodes) > 1 and len(current_nodes) <= 5 and _uniform_degree(current_nodes):
        # Attempt one final merge as a generic composite if similar enough.
        if _similarity_ok(current_nodes, ctx.similarity_threshold):
            composite = _make_node(
                label="Composite",
                pattern_type="Composite",
                degree_level=current_nodes[0].degree_level + 1,
                children=list(current_nodes),
                score=0.4,
                is_complete=current_nodes[-1].end_idx < tail_end_idx,
                details={"note": "Collapsed as composite due to similarity"},
                invalidation_point=None,
            )
            current_nodes = [composite]

    tree = WaveTree(roots=current_nodes, anchor_label=_anchor_label(swing_list))
    return tree
