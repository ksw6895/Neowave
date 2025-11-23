"""Lightweight in-memory NEoWave rule database.

The goal is not to mirror every nuance of the PDF, but to provide structured,
machine-readable rules that the PatternEvaluator can score with tolerances.
"""

from __future__ import annotations

from typing import Any

# Each rule: id, expr (python-safe expression using metrics), hard(bool), weight(float), description(str)
RULE_DB: dict[str, dict[str, dict[str, list[dict[str, Any]]]]] = {
    "Impulse": {
        "TrendingImpulse": {
            "price_rules": [
                {"id": "wave2_lt_100", "expr": "wave2_ratio < 1.0", "hard": True, "weight": 0.4, "description": "Wave2 retrace < 100% of Wave1"},
                {"id": "wave2_min", "expr": "wave2_ratio >= 0.236", "hard": False, "weight": 0.1, "description": "Wave2 retrace >= 23.6%"},
                {"id": "wave3_not_shortest", "expr": "wave3_not_shortest", "hard": True, "weight": 0.6, "description": "Wave3 not shortest motive wave"},
                {"id": "extension_present", "expr": "extension_present", "hard": False, "weight": 0.1, "description": "At least one extension in 1/3/5"},
                {"id": "wave5_vs4", "expr": "wave5_over_wave4 >= 0.382", "hard": False, "weight": 0.08, "description": "Wave5 >= 38.2% of Wave4"},
            ],
            "time_rules": [
                {"id": "alt_time", "expr": "wave2_time >= 0.33 * wave1_time and wave4_time >= 0.33 * wave3_time", "hard": False, "weight": 0.05, "description": "Wave2/4 time similarity >= 1/3"},
            ],
            "volume_rules": [],
        },
        "TerminalImpulse": {
            "price_rules": [
                {"id": "wave2_lt_100", "expr": "wave2_ratio < 1.0", "hard": True, "weight": 0.4, "description": "Wave2 retrace < 100%"},
                {"id": "wave3_not_shortest", "expr": "wave3_not_shortest", "hard": True, "weight": 0.6, "description": "Wave3 not shortest motive wave"},
                {"id": "diagonal_overlap", "expr": "True", "hard": False, "weight": 0.05, "description": "Overlap tolerated in terminal impulse"},
            ],
            "time_rules": [],
            "volume_rules": [],
        },
    },
    "Zigzag": {
        "Standard": {
            "price_rules": [
                {"id": "b_depth", "expr": "B_over_A < 0.7", "hard": True, "weight": 0.5, "description": "Wave B < 70% of A"},
                {"id": "c_min", "expr": "C_over_A >= 0.618", "hard": False, "weight": 0.15, "description": "Wave C >= 61.8% of A"},
            ],
            "time_rules": [],
            "volume_rules": [],
        }
    },
    "Flat": {
        "Normal": {
            "price_rules": [
                {"id": "b_min", "expr": "B_over_A >= 0.618", "hard": True, "weight": 0.45, "description": "Wave B >= 61.8% of A"},
                {"id": "c_min_vs_b", "expr": "C_over_B >= 0.382", "hard": False, "weight": 0.12, "description": "Wave C >= 38.2% of B"},
            ],
            "time_rules": [],
            "volume_rules": [],
        },
        "Expanded": {
            "price_rules": [
                {"id": "b_strong", "expr": "B_over_A >= 1.0", "hard": True, "weight": 0.4, "description": "Wave B exceeds start of A"},
                {"id": "c_follow_through", "expr": "C_over_B >= 0.618", "hard": False, "weight": 0.15, "description": "Wave C carries through >=61.8% of B"},
            ],
            "time_rules": [],
            "volume_rules": [],
        },
        "Running": {
            "price_rules": [
                {"id": "b_very_strong", "expr": "B_over_A >= 1.236", "hard": True, "weight": 0.4, "description": "Wave B 123.6%+ of A"},
                {"id": "c_short", "expr": "C_over_A >= 0.382", "hard": False, "weight": 0.1, "description": "Wave C at least shallow 38.2% of A"},
            ],
            "time_rules": [],
            "volume_rules": [],
        },
    },
    "Triangle": {
        "Contracting": {
            "price_rules": [
                {"id": "alternation", "expr": "alternating", "hard": True, "weight": 0.4, "description": "Directions alternate a-b-c-d-e"},
                {"id": "price_contraction", "expr": "price_contraction <= 1.05", "hard": False, "weight": 0.12, "description": "Price range contracts"},
            ],
            "time_rules": [
                {"id": "time_balance", "expr": "time_balance >= 0.25", "hard": False, "weight": 0.05, "description": "Adjacent leg times >= 25% ratio"},
            ],
            "volume_rules": [],
        },
        "Expanding": {
            "price_rules": [
                {"id": "alternation", "expr": "alternating", "hard": True, "weight": 0.4, "description": "Directions alternate"},
                {"id": "price_expansion", "expr": "price_contraction >= 0.95", "hard": False, "weight": 0.12, "description": "Price legs expanding"},
            ],
            "time_rules": [],
            "volume_rules": [],
        },
        "Neutral": {
            "price_rules": [
                {"id": "alternation", "expr": "alternating", "hard": True, "weight": 0.35, "description": "Directions alternate"},
                {"id": "balance", "expr": "price_balance >= 0.33", "hard": False, "weight": 0.12, "description": "Leg sizes balanced"},
            ],
            "time_rules": [],
            "volume_rules": [],
        },
    },
}


def load_rule_db(custom_rules: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a merged rule DB (custom overrides default)."""
    if not custom_rules:
        return RULE_DB
    merged = {**RULE_DB}
    for pattern, sub in custom_rules.items():
        merged.setdefault(pattern, {}).update(sub)
    return merged
