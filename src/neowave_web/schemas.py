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


class SwingOut(BaseModel):
    start_time: datetime
    end_time: datetime
    start_price: float
    end_price: float
    direction: str
    high: float
    low: float
    duration: float = Field(..., description="Duration in seconds")
    volume: float


class SwingsResponse(BaseModel):
    swings: list[SwingOut]
    count: int
    scale_id: str | None = None


class WaveBoxOut(BaseModel):
    swing_start: int
    swing_end: int
    time_start: datetime
    time_end: datetime
    price_low: float
    price_high: float


class WaveNodeOut(BaseModel):
    id: str
    label: str
    pattern_type: str
    direction: str | None = None
    degree: int | None = None
    swing_start: int
    swing_end: int
    children: list["WaveNodeOut"] = Field(default_factory=list)


class RuleEvidenceItem(BaseModel):
    key: str
    description: str | None = None
    value: float | bool | str
    expected: str | None = None
    passed: bool | None = None
    penalty: float | None = None


class ScenarioOut(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    pattern_type: str
    score: float
    weighted_score: float | None = None
    swing_indices: tuple[int, int]
    textual_summary: str
    invalidation_levels: dict[str, float] | None = None
    details: dict[str, Any] | None = None
    in_progress: bool | None = None
    scale_id: str | None = None
    wave_box: WaveBoxOut | None = None
    wave_labels: list[str] | None = None
    wave_tree: WaveNodeOut | None = None
    rule_evidence: list[RuleEvidenceItem] | None = None


class ScenariosResponse(BaseModel):
    scenarios: list[ScenarioOut]
    count: int


WaveNodeOut.model_rebuild()
