from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Iterable, List

from neowave_core.rule_checks import RuleCheck
from neowave_core.swings import Direction, Swing


@dataclass(slots=True)
class WaveNode:
    """Hierarchical wave representation with optional sub-wave children."""

    label: str
    pattern_type: str
    degree: str | None

    start_idx: int
    end_idx: int
    start_price: float
    end_price: float
    start_time: datetime
    end_time: datetime
    high: float
    low: float

    sub_waves: List["WaveNode"] = field(default_factory=list)
    degree_level: int = 0
    score: float = 0.0
    is_complete: bool = True
    rules_passed: list[str] = field(default_factory=list)
    invalidation_point: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    sub_scale_analysis: dict[str, Any] | None = None
    box_ratio: float | None = None
    energy_metric: float | None = None

    @property
    def direction(self) -> Direction:
        return Direction.from_prices(self.start_price, self.end_price)

    @property
    def length(self) -> float:
        return abs(self.end_price - self.start_price)

    @property
    def duration(self) -> float:
        return (self.end_time - self.start_time).total_seconds()

    @property
    def is_leaf(self) -> bool:
        return len(self.sub_waves) == 0

    def add_sub_wave(self, node: "WaveNode") -> None:
        self.sub_waves.append(node)
        self.start_idx = min(self.start_idx, node.start_idx)
        self.end_idx = max(self.end_idx, node.end_idx)
        self.start_price = self.sub_waves[0].start_price
        self.end_price = self.sub_waves[-1].end_price
        self.start_time = self.sub_waves[0].start_time
        self.end_time = self.sub_waves[-1].end_time
        self.high = max((w.high for w in self.sub_waves), default=self.high)
        self.low = min((w.low for w in self.sub_waves), default=self.low)

    def to_dict(self) -> dict[str, Any]:
        def _clean(value: Any) -> Any:
            if isinstance(value, RuleCheck):
                return asdict(value)
            if isinstance(value, list):
                return [_clean(item) for item in value]
            if isinstance(value, dict):
                return {k: _clean(v) for k, v in value.items()}
            return value

        return {
            "label": self.label,
            "pattern_type": self.pattern_type,
            "degree": self.degree,
            "degree_level": self.degree_level,
            "start_idx": self.start_idx,
            "end_idx": self.end_idx,
            "start_price": self.start_price,
            "end_price": self.end_price,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "high": self.high,
            "low": self.low,
            "score": self.score,
            "is_complete": self.is_complete,
            "rules_passed": list(self.rules_passed),
            "invalidation_point": self.invalidation_point,
            "metadata": _clean(self.metadata),
            "sub_waves": [child.to_dict() for child in self.sub_waves],
            "sub_scale_analysis": _clean(self.sub_scale_analysis),
            "box_ratio": self.box_ratio,
            "energy_metric": self.energy_metric,
        }

    @classmethod
    def from_swing(cls, swing_idx: int, swing: Swing, degree: str | None = None) -> "WaveNode":
        """Build a WaveNode leaf from a detected Swing."""
        return cls(
            label=str(swing_idx + 1),
            pattern_type="Monowave",
            degree=degree,
            start_idx=swing_idx,
            end_idx=swing_idx,
            start_price=swing.start_price,
            end_price=swing.end_price,
            start_time=swing.start_time,
            end_time=swing.end_time,
            high=swing.high,
            low=swing.low,
            sub_waves=[],
            degree_level=0,
            score=1.0,
            is_complete=True,
            rules_passed=["monowave"],
            invalidation_point=None,
            metadata={"direction": swing.direction.value, "duration": swing.duration, "volume": swing.volume},
        )


@dataclass(slots=True)
class WaveTree:
    """Container for one or more root-level waves built from hierarchical parsing."""

    roots: list[WaveNode] = field(default_factory=list)
    anchor_label: str | None = None

    def add_root(self, node: WaveNode) -> None:
        self.roots.append(node)

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor_label": self.anchor_label,
            "roots": [root.to_dict() for root in self.roots],
        }

    def flatten(self) -> list[WaveNode]:
        collected: list[WaveNode] = []

        def _walk(node: WaveNode) -> None:
            collected.append(node)
            for child in node.sub_waves:
                _walk(child)

        for root in self.roots:
            _walk(root)
        return collected


def build_wave_leaves(swings: Iterable[Swing], degree: str | None = None) -> list[WaveNode]:
    """Helper to convert swings to monowave leaves."""
    return [WaveNode.from_swing(idx, swing, degree=degree) for idx, swing in enumerate(swings)]
