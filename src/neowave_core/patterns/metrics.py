from __future__ import annotations

from typing import Iterable, Sequence

from neowave_core.models import WaveNode


def _length(node: WaveNode) -> float:
    return float(node.abs_price_change)


def _duration(node: WaveNode) -> float:
    return float(node.duration)


def is_alternating_directions(nodes: Sequence[WaveNode]) -> bool:
    if len(nodes) < 2:
        return True
    last_dir = nodes[0].direction
    for node in nodes[1:]:
        if node.direction == last_dir:
            return False
        last_dir = node.direction
    return True


def infer_net_direction(nodes: Sequence[WaveNode]) -> str | None:
    if not nodes:
        return None
    start = nodes[0].start_price
    end = nodes[-1].end_price
    if end == start:
        return None
    return "up" if end > start else "down"


def compute_impulse_metrics(waves: Sequence[WaveNode]) -> dict[str, float]:
    lengths = [_length(w) for w in waves]
    durations = [_duration(w) for w in waves]
    wave2_ratio = lengths[1] / lengths[0] if lengths[0] else 0.0
    extension_present = False
    if len(lengths) >= 5:
        sorted_lengths = sorted([lengths[0], lengths[2], lengths[4]])
        extension_present = sorted_lengths[-1] >= 1.4 * sorted_lengths[-2] if sorted_lengths[-2] else False
    return {
        "wave1_length": lengths[0],
        "wave2_length": lengths[1],
        "wave3_length": lengths[2],
        "wave4_length": lengths[3],
        "wave5_length": lengths[4],
        "wave1_time": durations[0],
        "wave2_time": durations[1],
        "wave3_time": durations[2],
        "wave4_time": durations[3],
        "wave2_ratio": wave2_ratio,
        "wave3_not_shortest": lengths[2] >= min(lengths[0], lengths[4]),
        "extension_present": extension_present,
        "wave5_over_wave4": lengths[4] / lengths[3] if lengths[3] else 0.0,
        "price_balance": min(lengths) / max(lengths) if max(lengths) else 1.0,
    }


def compute_zigzag_metrics(waves: Sequence[WaveNode]) -> dict[str, float]:
    lengths = [_length(w) for w in waves]
    return {
        "A_length": lengths[0],
        "B_length": lengths[1],
        "C_length": lengths[2],
        "B_over_A": lengths[1] / lengths[0] if lengths[0] else 0.0,
        "C_over_A": lengths[2] / lengths[0] if lengths[0] else 0.0,
        "C_over_B": lengths[2] / lengths[1] if lengths[1] else 0.0,
    }


def compute_flat_metrics(waves: Sequence[WaveNode]) -> dict[str, float]:
    base = compute_zigzag_metrics(waves)
    base["B_stronger_than_A"] = base["B_over_A"] >= 1.0
    return base


def compute_triangle_metrics(waves: Sequence[WaveNode]) -> dict[str, float]:
    lengths = [_length(w) for w in waves]
    durations = [_duration(w) for w in waves]
    price_ratios = []
    time_ratios = []
    for left, right in zip(waves, waves[1:]):
        price_ratios.append(min(_length(left), _length(right)) / max(_length(left), _length(right)) if max(_length(left), _length(right)) else 1.0)
        time_ratios.append(min(_duration(left), _duration(right)) / max(_duration(left), _duration(right)) if max(_duration(left), _duration(right)) else 1.0)
    return {
        "legs": lengths,
        "durations": durations,
        "price_balance": min(lengths) / max(lengths) if max(lengths) else 1.0,
        "time_balance": min(time_ratios) if time_ratios else 1.0,
        "price_contraction": lengths[-1] / lengths[0] if lengths and lengths[0] else 1.0,
        "alternating": is_alternating_directions(waves),
    }


def compute_metrics_for_pattern(pattern_name: str, subtype: str, waves: Sequence[WaveNode]) -> dict[str, float]:
    if pattern_name == "Impulse":
        return compute_impulse_metrics(waves)
    if pattern_name == "Zigzag":
        return compute_zigzag_metrics(waves)
    if pattern_name == "Flat":
        return compute_flat_metrics(waves)
    if pattern_name == "Triangle":
        return compute_triangle_metrics(waves)
    return {}
