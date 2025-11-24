from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Candle(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class CandleResponse(BaseModel):
    candles: list[Candle]
    count: int


class MonowaveOut(BaseModel):
    id: int
    start_idx: int
    end_idx: int
    start_time: datetime
    end_time: datetime
    start_price: float
    end_price: float
    high_price: float
    low_price: float
    direction: str
    price_change: float
    abs_price_change: float
    duration: float
    volume_sum: float
    atr_avg: float | None = None


class MonowaveResponse(BaseModel):
    monowaves: list[MonowaveOut]
    count: int


class ValidationOut(BaseModel):
    hard_valid: bool
    soft_score: float
    satisfied_rules: list[str] = Field(default_factory=list)
    violated_soft_rules: list[str] = Field(default_factory=list)
    violated_hard_rules: list[str] = Field(default_factory=list)


class WaveNodeOut(BaseModel):
    id: int
    level: int
    degree_label: str | None = None
    start_idx: int
    end_idx: int
    start_time: datetime | None = None
    end_time: datetime | None = None
    start_price: float | None = None
    end_price: float | None = None
    high_price: float | None = None
    low_price: float | None = None
    direction: str | None = None
    pattern_type: str | None = None
    pattern_subtype: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    validation: ValidationOut | None = None
    score: float | None = None
    label: str | None = None
    children: list["WaveNodeOut"] = Field(default_factory=list)


class ScenarioOut(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: int
    global_score: float
    status: str
    invalidation_reasons: list[str] = Field(default_factory=list)
    probability: float = 0.5
    invalidation_levels: list[dict[str, Any]] = Field(default_factory=list)
    roots: list[WaveNodeOut]
    view_nodes: list[WaveNodeOut] = Field(default_factory=list)
    view_level: int = 0


class ScenariosResponse(BaseModel):
    scenarios: list[ScenarioOut]
    count: int


class WaveChildrenResponse(BaseModel):
    parent_id: int
    children: list[WaveNodeOut]


class RuleXRayResponse(BaseModel):
    wave_id: int
    pattern_type: str | None = None
    pattern_subtype: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    validation: ValidationOut | None = None


WaveNodeOut.model_rebuild()
