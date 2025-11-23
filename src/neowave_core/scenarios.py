from __future__ import annotations

from typing import Any, Iterable, Sequence

from neowave_core.config import DEFAULT_SIMILARITY_THRESHOLD
from neowave_core.models import WaveNode, WaveTree
from neowave_core.parser import ParseSettings, parse_wave_tree
from neowave_core.rule_checks import serialize_rule_checks
from neowave_core.rule_engine import score_scenario_with_neowave_rules
from neowave_core.swings import Direction, Swing, SwingSet, identify_major_pivots
from neowave_core.wave_box import compute_wave_box, serialize_wave_box
from neowave_core.wave_tree import build_wave_tree_from_parsed, infer_wave_labels, serialize_wave_tree


def _active_path(node: WaveNode) -> list[WaveNode]:
    """Follow the last child chain to represent the in-progress leg."""
    path = [node]
    if node.sub_waves:
        path.extend(_active_path(node.sub_waves[-1]))
    return path


def _summary_for_node(node: WaveNode, tree: WaveTree) -> str:
    path = _active_path(node)
    pieces = []
    for segment in path:
        child_label = segment.sub_waves[-1].label if segment.sub_waves else segment.label
        status = "진행 중" if not segment.is_complete else "완료"
        pieces.append(f"{segment.degree} {segment.pattern_type} ({child_label} {status})")
    anchor = f" · Anchor: {tree.anchor_label}" if tree.anchor_label else ""
    return " / ".join(pieces) + anchor


def _invalidation(node: WaveNode) -> dict[str, float]:
    point = node.invalidation_point or node.start_price
    if node.direction == Direction.UP:
        return {"price_below": point}
    return {"price_above": point}


def _projection(node: WaveNode) -> dict[str, float]:
    """Rough next target using last sub-wave length and fib ratios."""
    tail = node.sub_waves[-1] if node.sub_waves else node
    ref_length = tail.length or 0.0
    fib_ratio = 0.618 if node.pattern_type.lower() in {"impulse", "zigzag", "flat"} else 1.0
    move = ref_length * fib_ratio
    direction = 1.0 if tail.direction == Direction.UP else -1.0
    target_price = tail.end_price + direction * move
    return {
        "basis_length": ref_length,
        "fib_ratio": fib_ratio,
        "target_price": target_price,
        "target_time": tail.end_time.isoformat(),
    }


def _offset_node_indices(node: WaveNode, offset: int) -> None:
    node.start_idx += offset
    node.end_idx += offset
    for child in node.sub_waves:
        _offset_node_indices(child, offset)


def _apply_offset(tree: WaveTree, offset: int) -> None:
    for root in tree.roots:
        _offset_node_indices(root, offset)


def _anchor_label(swings: Sequence[Swing], idx: int) -> str:
    if not swings or idx < 0 or idx >= len(swings):
        return f"Anchor@{idx}"
    sw = swings[idx]
    pivot_price = sw.start_price if sw.direction == Direction.UP else sw.end_price
    return f"Pivot#{idx}@{pivot_price:.2f}"


def _filter_invalidated(scenarios: list[dict[str, Any]], current_price: float | None) -> list[dict[str, Any]]:
    if current_price is None:
        return scenarios
    filtered: list[dict[str, Any]] = []
    for scenario in scenarios:
        invalidation = scenario.get("invalidation_levels") or {}
        above = invalidation.get("price_above")
        below = invalidation.get("price_below")
        if above is not None and current_price >= above:
            continue
        if below is not None and current_price <= below:
            continue
        filtered.append(scenario)
    return filtered


def generate_scenarios(
    swings: Sequence[Swing] | Iterable[Swing],
    rules: dict[str, Any],
    max_pivots: int = 5,
    max_scenarios: int = 5,
    current_price: float | None = None,
    settings: ParseSettings | None = None,
    scale_id: str | None = None,
    anchor_indices: list[int] | None = None,
    swing_sets: Sequence[SwingSet] | None = None,
) -> list[dict[str, Any]]:
    """Generate hierarchical scenarios using the parsed WaveTree."""
    swing_list = list(swings)
    if not swing_list:
        return []
    parse_settings = settings or ParseSettings(similarity_threshold=DEFAULT_SIMILARITY_THRESHOLD)
    micro_swings: Sequence[Swing] | None = None
    if swing_sets:
        micro_set = next((s for s in swing_sets if s.scale_id == "micro"), None)
        if micro_set:
            micro_swings = micro_set.swings

    def _anchor_candidates() -> list[int]:
        provided = [idx for idx in (anchor_indices or []) if 0 <= idx < len(swing_list)]
        auto = identify_major_pivots(swing_list, max_pivots=max_pivots)
        anchors: list[int] = []
        for idx in provided + auto:
            if idx not in anchors:
                anchors.append(idx)
            if len(anchors) >= max_pivots:
                break
        if not anchors:
            anchors.append(0)
        return anchors

    scenarios: list[dict[str, Any]] = []
    for anchor_idx in _anchor_candidates():
        local_swings = swing_list[anchor_idx:]
        tree = parse_wave_tree(local_swings, rules, settings=parse_settings)
        if anchor_idx:
            _apply_offset(tree, anchor_idx)
        tree.anchor_label = _anchor_label(swing_list, anchor_idx)
        rule_score = score_scenario_with_neowave_rules(
            tree,
            swing_list,
            micro_swings=micro_swings,
            similarity_threshold=parse_settings.similarity_threshold,
        )

        anchor_info = {
            "anchor_idx": anchor_idx,
            "anchor_time": swing_list[anchor_idx].start_time,
            "anchor_price": swing_list[anchor_idx].start_price,
        }

        for root in tree.roots:
            summary = _summary_for_node(root, tree)
            projection = _projection(root)
            invalidation_levels = _invalidation(root)
            combined_score = max(0.0, min(1.0, 0.6 * rule_score.score + 0.4 * root.score))
            weighted_score = combined_score * (1.1 if not root.is_complete else 1.0)
            pattern_details = dict(root.metadata.get("details") or {})
            pattern_details["rule_checks"] = serialize_rule_checks(rule_score.evidence)
            rule_evidence = serialize_rule_checks(rule_score.evidence)
            try:
                box = compute_wave_box(swing_list, root.start_idx, root.end_idx)
                box_serialized = serialize_wave_box(box)
            except Exception:
                box_serialized = None
            wave_labels = infer_wave_labels(root.pattern_type, (root.start_idx, root.end_idx))
            wave_tree = build_wave_tree_from_parsed(root)
            scenarios.append(
                {
                    "pattern_type": root.pattern_type,
                    "score": combined_score,
                    "weighted_score": weighted_score,
                    "swing_indices": (root.start_idx, root.end_idx),
                    "textual_summary": summary,
                    "invalidation_levels": invalidation_levels,
                    "violations": rule_score.violations,
                    "details": {
                        "wave_tree": root.to_dict(),
                        "projection": projection,
                        "active_path": [node.label for node in _active_path(root)],
                        "anchor": tree.anchor_label,
                        "pattern_details": pattern_details,
                        "anchor_info": anchor_info,
                    },
                    "in_progress": not root.is_complete,
                    "scale_id": scale_id,
                    "anchor_idx": anchor_idx,
                    "wave_box": box_serialized,
                    "wave_labels": wave_labels,
                    "wave_tree": serialize_wave_tree(wave_tree),
                    "rule_evidence": rule_evidence,
                }
            )

    scenarios = _filter_invalidated(scenarios, current_price)
    scenarios.sort(key=lambda item: item["weighted_score"], reverse=True)
    return scenarios[:max_scenarios]


def generate_scenarios_multi_scale(
    swing_sets: Sequence[SwingSet],
    rules: dict[str, Any],
    max_pivots: int = 5,
    max_scenarios: int = 5,
    current_price: float | None = None,
    settings: ParseSettings | None = None,
    scale_id: str = "base",
) -> list[dict[str, Any]]:
    """Helper to run scenario generation with macro/base/micro context."""
    if not swing_sets:
        return []
    base_set = next((s for s in swing_sets if s.scale_id == scale_id), swing_sets[0])
    return generate_scenarios(
        base_set.swings,
        rules,
        max_pivots=max_pivots,
        max_scenarios=max_scenarios,
        current_price=current_price,
        settings=settings,
        scale_id=base_set.scale_id,
        swing_sets=swing_sets,
    )
