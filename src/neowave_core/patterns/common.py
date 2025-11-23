from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from neowave_core.swings import Direction, Swing


@dataclass(slots=True)
class PatternCheckResult:
    pattern: str
    is_valid: bool
    score: float
    violations: list[str] = field(default_factory=list)
    details: dict[str, Any] | None = None


def is_alternating(swings: Sequence[Swing]) -> bool:
    if len(swings) < 2:
        return True
    for prev, current in zip(swings, swings[1:]):
        if prev.direction == current.direction:
            return False
    return True


def pattern_direction(swings: Sequence[Swing]) -> Direction:
    """Assume the first swing sets the trend direction."""
    if not swings:
        return Direction.UP
    return swings[0].direction
