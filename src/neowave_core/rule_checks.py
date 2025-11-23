from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Iterable, List


@dataclass(slots=True)
class RuleCheck:
    """Represents the evaluation of a single NEoWave rule."""

    key: str
    description: str | None
    value: float | bool | str
    expected: str | None
    passed: bool
    penalty: float


def serialize_rule_checks(checks: Iterable[RuleCheck] | None) -> list[dict[str, Any]]:
    """Convert RuleCheck objects into JSON-serializable dictionaries."""
    if not checks:
        return []

    def _value(val: Any) -> Any:
        if isinstance(val, dict):
            return ", ".join(f"{k}:{v}" for k, v in val.items())
        return val

    serialized: List[dict[str, Any]] = []
    for check in checks:
        if isinstance(check, RuleCheck):
            item = asdict(check)
            item["value"] = _value(item.get("value"))
            serialized.append(item)
            continue
        if isinstance(check, dict):
            converted = dict(check)
            converted["value"] = _value(converted.get("value"))
            serialized.append(converted)
    return serialized
