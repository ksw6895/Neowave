from __future__ import annotations

from typing import Any, Iterable, Sequence

from neowave_core.models import Monowave, PatternValidation, Scenario, WaveNode
from neowave_core.wave_engine import analyze_market_structure, find_node_by_id, get_view_nodes


def _serialize_validation(validation: PatternValidation) -> dict[str, Any]:
    return {
        "hard_valid": validation.hard_valid,
        "soft_score": validation.soft_score,
        "satisfied_rules": list(validation.satisfied_rules),
        "violated_soft_rules": list(validation.violated_soft_rules),
        "violated_hard_rules": list(validation.violated_hard_rules),
    }


def serialize_wave_node(node: WaveNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "level": node.level,
        "degree_label": node.degree_label,
        "start_idx": node.start_idx,
        "end_idx": node.end_idx,
        "start_time": node.start_time,
        "end_time": node.end_time,
        "start_price": node.start_price,
        "end_price": node.end_price,
        "high_price": node.high_price,
        "low_price": node.low_price,
        "direction": node.direction,
        "pattern_type": node.pattern_type,
        "pattern_subtype": node.pattern_subtype,
        "metrics": node.metrics,
        "validation": _serialize_validation(node.validation),
        "score": node.score,
        "label": node.label,
        "children": [serialize_wave_node(child) for child in node.children],
    }


def serialize_scenario(scenario: Scenario, target_wave_count: int = 40) -> dict[str, Any]:
    view_nodes = get_view_nodes(scenario.root_nodes, target_wave_count=target_wave_count)
    return {
        "id": scenario.id,
        "global_score": scenario.global_score,
        "status": scenario.status,
        "invalidation_reasons": list(scenario.invalidation_reasons),
        "probability": scenario.probability,
        "invalidation_levels": scenario.invalidation_levels,
        "roots": [serialize_wave_node(root) for root in scenario.root_nodes],
        "view_nodes": [serialize_wave_node(node) for node in view_nodes],
        "view_level": view_nodes[0].level if view_nodes else 0,
    }


def generate_scenarios(
    monowaves: Sequence[Monowave],
    rule_db: dict[str, Any] | None = None,
    beam_width: int = 6,
    target_wave_count: int = 40,
) -> list[dict[str, Any]]:
    scenarios = analyze_market_structure(monowaves, rule_db=rule_db, beam_width=beam_width)
    
    # Post-process scenarios to add probability and invalidation levels
    for sc in scenarios:
        # Simple heuristic for probability: map score (0-100) to 0.0-1.0
        # This is a placeholder for a more sophisticated model
        sc.probability = min(max(sc.global_score / 100.0, 0.01), 0.99)
        
        # Invalidation levels
        # For now, we add the start and end of the pattern as critical levels
        if sc.root_nodes:
            start_node = sc.root_nodes[0]
            end_node = sc.root_nodes[-1]
            
            sc.invalidation_levels = [
                {
                    "price": start_node.start_price,
                    "reason": "Pattern Start",
                    "type": "hard"
                },
                {
                    "price": end_node.end_price,
                    "reason": "Pattern End",
                    "type": "soft"
                }
            ]
            
    return [serialize_scenario(sc, target_wave_count=target_wave_count) for sc in scenarios]


def find_wave_node(
    monowaves: Sequence[Monowave],
    wave_id: int,
    rule_db: dict[str, Any] | None = None,
    beam_width: int = 6,
) -> WaveNode | None:
    scenarios = analyze_market_structure(monowaves, rule_db=rule_db, beam_width=beam_width)
    if not scenarios:
        return None
    best = scenarios[0]
    return find_node_by_id(best.root_nodes, wave_id)
