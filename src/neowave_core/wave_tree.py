from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Iterable, List, Sequence

from neowave_core.models import WaveNode as ParsedWaveNode


@dataclass(slots=True)
class WaveNode:
    """Lightweight, JSON-friendly wave node for API/UI consumption."""

    id: str
    label: str
    pattern_type: str
    direction: str | None
    degree: int
    swing_start: int
    swing_end: int
    start_price: float | None = None
    end_price: float | None = None
    start_time: Any | None = None
    end_time: Any | None = None
    high: float | None = None
    low: float | None = None
    box_ratio: float | None = None
    energy_metric: float | None = None
    sub_scale_analysis: dict[str, Any] | None = None
    children: list["WaveNode"] = field(default_factory=list)


def infer_wave_labels(pattern_type: str, swing_indices: Sequence[int]) -> list[str]:
    """Infer human-friendly labels (1-5, A-C, W-X-Y...) for a swing window."""
    if len(swing_indices) != 2:
        return []
    start_idx, end_idx = swing_indices
    count = max(0, end_idx - start_idx + 1)
    pattern = pattern_type.lower()
    if pattern in {"impulse", "terminal_impulse", "terminalimpulse"} and count == 5:
        return ["1", "2", "3", "4", "5"]
    if pattern in {"zigzag", "flat"} and count == 3:
        return ["A", "B", "C"]
    if pattern == "triangle" and count == 5:
        return ["A", "B", "C", "D", "E"]
    if pattern == "double_three" and count == 7:
        return ["W1", "W2", "W3", "X", "Y1", "Y2", "Y3"]
    if pattern == "triple_three" and count == 11:
        return ["W1", "W2", "W3", "X1", "Y1", "Y2", "Y3", "X2", "Z1", "Z2", "Z3"]
    return [f"S{idx + 1}" for idx in range(count)]


def _convert_node(node: ParsedWaveNode | None) -> WaveNode | None:
    if node is None:
        return None
    children: List[WaveNode] = []
    for child in node.sub_waves:
        converted = _convert_node(child)
        if converted:
            children.append(converted)
    return WaveNode(
        id=str(node.label),
        label=str(node.label),
        pattern_type=node.pattern_type,
        direction=node.direction.value if node.direction else None,
        degree=int(node.degree_level),
        swing_start=node.start_idx,
        swing_end=node.end_idx,
        start_price=node.start_price,
        end_price=node.end_price,
        start_time=node.start_time,
        end_time=node.end_time,
        high=node.high,
        low=node.low,
        box_ratio=node.box_ratio,
        energy_metric=node.energy_metric,
        sub_scale_analysis=node.sub_scale_analysis,
        children=children,
    )


def build_wave_tree_from_parsed(node: ParsedWaveNode | None) -> WaveNode | None:
    """Convert the internal WaveNode to a lightweight WaveNode for UI."""
    return _convert_node(node)


def serialize_wave_tree(node: WaveNode | None) -> dict[str, Any] | None:
    if node is None:
        return None
    def _serialize(current: WaveNode) -> dict[str, Any]:
        data = asdict(current)
        data["children"] = [_serialize(child) for child in current.children]
        return data

    return _serialize(node)
