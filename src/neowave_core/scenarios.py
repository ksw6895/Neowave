from __future__ import annotations

from typing import Any, Iterable, Sequence

from neowave_core.models import WaveNode, WaveTree
from neowave_core.parser import ParseSettings, parse_wave_tree
from neowave_core.rule_checks import serialize_rule_checks
from neowave_core.swings import Direction, Swing
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
    max_scenarios: int = 5,
    current_price: float | None = None,
    settings: ParseSettings | None = None,
    scale_id: str | None = None,
) -> list[dict[str, Any]]:
    """Generate hierarchical scenarios using the parsed WaveTree."""
    swing_list = list(swings)
    tree = parse_wave_tree(swing_list, rules, settings=settings)
    scenarios: list[dict[str, Any]] = []
    for root in tree.roots:
        summary = _summary_for_node(root, tree)
        projection = _projection(root)
        invalidation_levels = _invalidation(root)
        weighted_score = root.score * (1.1 if not root.is_complete else 1.0)
        pattern_details = dict(root.metadata.get("details") or {})
        pattern_details["rule_checks"] = serialize_rule_checks(pattern_details.get("rule_checks"))
        rule_evidence = serialize_rule_checks(pattern_details.get("rule_checks"))
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
                "score": root.score,
                "weighted_score": weighted_score,
                "swing_indices": (root.start_idx, root.end_idx),
                "textual_summary": summary,
                "invalidation_levels": invalidation_levels,
                "details": {
                    "wave_tree": root.to_dict(),
                    "projection": projection,
                    "active_path": [node.label for node in _active_path(root)],
                    "anchor": tree.anchor_label,
                    "pattern_details": pattern_details,
                },
                "in_progress": not root.is_complete,
                "scale_id": scale_id,
                "wave_box": box_serialized,
                "wave_labels": wave_labels,
                "wave_tree": serialize_wave_tree(wave_tree),
                "rule_evidence": rule_evidence,
            }
        )

    scenarios = _filter_invalidated(scenarios, current_price)
    scenarios.sort(key=lambda item: item["weighted_score"], reverse=True)
    return scenarios[:max_scenarios]
