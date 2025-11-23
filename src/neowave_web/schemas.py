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


class ScenarioOut(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    pattern_type: str
    score: float
    swing_indices: tuple[int, int]
    textual_summary: str
    invalidation_levels: dict[str, float] | None = None
    details: dict[str, Any] | None = None
    in_progress: bool | None = None


class ScenariosResponse(BaseModel):
    scenarios: list[ScenarioOut]
    count: int
