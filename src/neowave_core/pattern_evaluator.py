from __future__ import annotations

import math
from typing import Any, Callable, Sequence

from neowave_core.models import PatternValidation, WaveNode
from neowave_core.patterns.metrics import compute_metrics_for_pattern


class PatternEvaluator:
    """Evaluates a candidate pattern window using RULE_DB style definitions."""

    def __init__(self, rule_db: dict[str, Any], tolerance: float = 0.02):
        self.rule_db = rule_db
        self.tolerance = tolerance

    def evaluate(self, pattern_name: str, subtype: str, waves: Sequence[WaveNode], context: dict[str, Any] | None = None) -> tuple[PatternValidation, dict[str, float]]:
        rules = self._select_rules(pattern_name, subtype)
        metrics = compute_metrics_for_pattern(pattern_name, subtype, waves)
        if context:
            metrics = {**context, **metrics}
        validation = PatternValidation(hard_valid=True, soft_score=0.0, satisfied_rules=[], violated_soft_rules=[], violated_hard_rules=[])
        for rule in rules.get("price_rules", []):
            self._apply_rule(rule, metrics, validation)
        for rule in rules.get("time_rules", []):
            self._apply_rule(rule, metrics, validation)
        for rule in rules.get("volume_rules", []):
            self._apply_rule(rule, metrics, validation)
        validation.soft_score = round(validation.soft_score, 3)
        return validation, metrics

    def _select_rules(self, pattern_name: str, subtype: str) -> dict[str, Any]:
        if pattern_name not in self.rule_db:
            raise KeyError(f"Unknown pattern: {pattern_name}")
        subrules = self.rule_db.get(pattern_name, {})
        if subtype not in subrules:
            # fallback to any available subtype
            subtype = next(iter(subrules.keys()))
        return subrules[subtype]

    def _allowed_funcs(self) -> dict[str, Callable[..., Any]]:
        return {"min": min, "max": max, "abs": abs, "sqrt": math.sqrt}

    def _eval_expr(self, expr: str, metrics: dict[str, Any]) -> bool:
        safe_locals = {**metrics, **self._allowed_funcs()}
        return bool(eval(expr, {"__builtins__": {}}, safe_locals))  # noqa: S307 - expressions are controlled from RULE_DB

    def _apply_rule(self, rule: dict[str, Any], metrics: dict[str, Any], validation: PatternValidation) -> None:
        expr = rule.get("expr", "True")
        desc = rule.get("description", expr)
        is_hard = bool(rule.get("hard", False))
        weight = float(rule.get("weight", 0.1))
        try:
            passed = self._eval_expr(expr, metrics)
        except Exception:
            passed = False
        if passed:
            validation.satisfied_rules.append(desc)
            return
        if is_hard:
            validation.hard_valid = False
            validation.violated_hard_rules.append(desc)
        else:
            validation.soft_score += weight
            validation.violated_soft_rules.append(desc)
