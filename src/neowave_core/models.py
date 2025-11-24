from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Literal, Sequence

Direction = Literal["up", "down"]


def _to_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    # pandas Timestamp is accepted
    try:
        return value.to_pydatetime()  # type: ignore[call-arg]
    except Exception:
        pass
    return datetime.fromisoformat(str(value))


@dataclass(slots=True)
class Monowave:
    """Minimum swing unit detected from price series."""

    id: int
    start_idx: int
    end_idx: int
    start_time: datetime
    end_time: datetime
    start_price: float
    end_price: float
    high_price: float
    low_price: float
    direction: Direction
    price_change: float
    abs_price_change: float
    duration: int  # number of bars
    volume_sum: float = 0.0
    atr_avg: float | None = None

    @classmethod
    def from_bars(cls, bars: Sequence[Any], start_idx: int, end_idx: int, wave_id: int) -> "Monowave":
        if start_idx < 0 or end_idx >= len(bars) or start_idx > end_idx:
            raise ValueError("Invalid monowave indices")
        segment = bars[start_idx : end_idx + 1]
        get = lambda obj, key: obj[key] if isinstance(obj, dict) else getattr(obj, key)
        start_bar = segment[0]
        end_bar = segment[-1]
        high_price = max(float(get(b, "high")) for b in segment)
        low_price = min(float(get(b, "low")) for b in segment)
        start_price = float(get(start_bar, "close"))
        end_price = float(get(end_bar, "close"))
        direction: Direction = "up" if end_price >= start_price else "down"
        duration = end_idx - start_idx + 1
        def _volume(obj: Any) -> float:
            if isinstance(obj, dict):
                return float(obj.get("volume", 0.0) or 0.0)
            return float(getattr(obj, "volume", 0.0) or 0.0)

        volume_sum = float(sum(_volume(b) for b in segment))
        return cls(
            id=wave_id,
            start_idx=start_idx,
            end_idx=end_idx,
            start_time=_to_datetime(get(start_bar, "timestamp")),
            end_time=_to_datetime(get(end_bar, "timestamp")),
            start_price=start_price,
            end_price=end_price,
            high_price=high_price,
            low_price=low_price,
            direction=direction,
            price_change=end_price - start_price,
            abs_price_change=abs(end_price - start_price),
            duration=duration,
            volume_sum=volume_sum,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "start_idx": self.start_idx,
            "end_idx": self.end_idx,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "start_price": self.start_price,
            "end_price": self.end_price,
            "high_price": self.high_price,
            "low_price": self.low_price,
            "direction": self.direction,
            "price_change": self.price_change,
            "abs_price_change": self.abs_price_change,
            "duration": self.duration,
            "volume_sum": self.volume_sum,
            "atr_avg": self.atr_avg,
        }


@dataclass(slots=True)
class PatternValidation:
    hard_valid: bool = True
    soft_score: float = 0.0
    satisfied_rules: list[str] = field(default_factory=list)
    violated_soft_rules: list[str] = field(default_factory=list)
    violated_hard_rules: list[str] = field(default_factory=list)


@dataclass(slots=True)
class WaveNode:
    """Fractal wave node that can wrap monowaves or higher-degree patterns."""

    id: int
    level: int  # 0 = monowave level
    degree_label: str | None
    start_idx: int
    end_idx: int
    start_time: datetime
    end_time: datetime
    high_price: float
    low_price: float
    start_price: float
    end_price: float
    direction: Direction | None
    children: list["WaveNode"] = field(default_factory=list)
    pattern_type: str | None = None
    pattern_subtype: str | None = None
    metrics: dict[str, float] = field(default_factory=dict)
    validation: PatternValidation = field(default_factory=PatternValidation)
    score: float = 0.0
    label: str | None = None

    @property
    def price_change(self) -> float:
        if self.children:
            return self.children[-1].end_price - self.children[0].start_price
        if "price_change" in self.metrics:
            return self.metrics["price_change"]
        return self.end_price - self.start_price

    @property
    def abs_price_change(self) -> float:
        if self.children:
            return abs(self.children[-1].end_price - self.children[0].start_price)
        if "abs_price_change" in self.metrics:
            return self.metrics["abs_price_change"]
        return abs(self.price_change)

    @property
    def duration(self) -> float:
        if self.children:
            return (self.children[-1].end_time - self.children[0].start_time).total_seconds()
        if "duration" in self.metrics:
            return float(self.metrics["duration"])
        return (self.end_time - self.start_time).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "level": self.level,
            "degree_label": self.degree_label,
            "start_idx": self.start_idx,
            "end_idx": self.end_idx,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "high_price": self.high_price,
            "low_price": self.low_price,
            "start_price": self.start_price,
            "end_price": self.end_price,
            "direction": self.direction,
            "pattern_type": self.pattern_type,
            "pattern_subtype": self.pattern_subtype,
            "metrics": dict(self.metrics),
            "validation": asdict(self.validation),
            "score": self.score,
            "label": self.label,
            "children": [child.to_dict() for child in self.children],
        }

    @classmethod
    def from_monowave(cls, mw: Monowave) -> "WaveNode":
        return cls(
            id=mw.id,
            level=0,
            degree_label=None,
            start_idx=mw.start_idx,
            end_idx=mw.end_idx,
            start_time=mw.start_time,
            end_time=mw.end_time,
            high_price=mw.high_price,
            low_price=mw.low_price,
            start_price=mw.start_price,
            end_price=mw.end_price,
            direction=mw.direction,
            children=[],
            pattern_type="Monowave",
            pattern_subtype=None,
            metrics={
                "price_change": mw.price_change,
                "abs_price_change": mw.abs_price_change,
                "duration": float(mw.duration),
                "start_price": mw.start_price,
                "end_price": mw.end_price,
                "volume_sum": mw.volume_sum,
            },
            validation=PatternValidation(hard_valid=True, soft_score=0.0, satisfied_rules=["monowave"]),
            score=0.0,
            label=str(mw.id),
        )


@dataclass(slots=True)
class Scenario:
    id: int
    root_nodes: list[WaveNode]
    global_score: float
    status: str = "active"  # active, invalidated, completed
    invalidation_reasons: list[str] = field(default_factory=list)
    
    # New fields for Phase 3
    probability: float = 0.5
    invalidation_levels: list[dict[str, Any]] = field(default_factory=list)
    view_level: int = 0  # 0=Micro, 1=Macro

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "root_nodes": [node.to_dict() for node in self.root_nodes],
            "global_score": self.global_score,
            "status": self.status,
            "invalidation_reasons": list(self.invalidation_reasons),
        }
