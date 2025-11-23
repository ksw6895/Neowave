from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


def load_rules(path: str | Path = "rules/neowave_rules.json") -> dict[str, Any]:
    """Load NEoWave rule definitions from JSON."""
    rules_path = Path(path)
    if not rules_path.exists():
        raise FileNotFoundError(f"Rules file not found: {rules_path}")
    with rules_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _numbers_from_rule(text: str, max_value: float = 10.0) -> list[float]:
    """Extract numeric literals from a rule string, ignoring citation indices."""
    pattern = r"(?<![A-Za-z])(-?\d+(?:\.\d+)?)(?![A-Za-z])"
    numbers = [float(match) for match in re.findall(pattern, text)]
    return [num for num in numbers if abs(num) <= max_value]


def _first_number(text: str, default: float) -> float:
    for num in _numbers_from_rule(text):
        return num
    return default


def _range_from_rule(text: str, default: tuple[float, float]) -> tuple[float, float]:
    numbers = _numbers_from_rule(text)
    if len(numbers) >= 2:
        return min(numbers[0], numbers[1]), max(numbers[0], numbers[1])
    if numbers:
        return numbers[0], default[1]
    return default


def _select_rule(block: dict[str, Any] | None, key: str, default: Iterable[str] | None = None) -> list[str]:
    rules = []
    if block and key in block and isinstance(block[key], list):
        rules.extend(str(item) for item in block[key])
    if not rules and default:
        rules.extend(default)
    return rules


@dataclass(slots=True)
class ImpulseRuleSet:
    wave2_min: float = 0.236
    wave2_max: float = 1.0
    extension_ratio: float = 1.618
    wave5_vs_wave4_min: float = 0.382
    similarity_threshold: float = 0.33


def extract_impulse_rules(rule_block: dict[str, Any] | None) -> ImpulseRuleSet:
    price_rules = _select_rule(
        rule_block,
        "price_rules",
        default=[
            "wave2_ratio >= 0.236 && wave2_ratio < 1.0",
            "extension_present >= 1.618x",
            "wave5_length >= 0.382 * wave4_length",
        ],
    )
    time_rules = _select_rule(
        rule_block,
        "time_rules",
        default=["rule_of_similarity: min(time_i,time_j)/max(time_i,time_j) >= 0.33"],
    )
    wave2_rule = next((rule for rule in price_rules if "wave2_ratio" in rule), "")
    wave5_rule = next((rule for rule in price_rules if "wave5_length" in rule), "")
    extension_rule = next((rule for rule in price_rules if "extension" in rule), "")
    similarity_rule = next((rule for rule in time_rules if "similarity" in rule.lower()), "")

    wave2_min, wave2_max = _range_from_rule(wave2_rule, (0.236, 1.0))
    wave5_min = _first_number(wave5_rule, 0.382)
    extension_ratio = _first_number(extension_rule, 1.618)
    similarity_threshold = _first_number(similarity_rule, 0.33)

    return ImpulseRuleSet(
        wave2_min=wave2_min,
        wave2_max=wave2_max,
        extension_ratio=extension_ratio,
        wave5_vs_wave4_min=wave5_min,
        similarity_threshold=similarity_threshold,
    )


@dataclass(slots=True)
class ZigzagRuleSet:
    b_max: float = 0.618
    c_typical: float = 0.618
    c_min_valid: float = 0.382
    c_elongated: float = 1.618


def extract_zigzag_rules(rule_block: dict[str, Any] | None) -> ZigzagRuleSet:
    price_rules = _select_rule(
        rule_block,
        "price_rules",
        default=[
            "waveB_ratio <= 0.618",
            "waveC_length >= 0.618 * waveA_length",
            "waveC_length > 1.618 * waveA_length",
        ],
    )
    b_rule = next((rule for rule in price_rules if "waveB_ratio" in rule), "")
    c_rule = next((rule for rule in price_rules if "waveC_length" in rule and ">=" in rule), "")
    elongated_rule = next(
        (rule for rule in price_rules if "elongated" in rule.lower() or "1.618" in rule),
        "",
    )

    b_max = _first_number(b_rule, 0.618)
    c_typical = _first_number(c_rule, 0.618)
    c_elongated = max(_numbers_from_rule(elongated_rule) or [1.618])

    return ZigzagRuleSet(
        b_max=b_max,
        c_typical=c_typical,
        c_min_valid=min(0.382, c_typical),
        c_elongated=c_elongated,
    )


@dataclass(slots=True)
class FlatRuleSet:
    b_min: float = 0.618
    weak_b_threshold: float = 0.8
    expanded_b_threshold: float = 1.0
    running_flat_b_threshold: float = 1.236
    c_min: float = 0.382
    c_elongated: float = 1.38


def extract_flat_rules(rule_block: dict[str, Any] | None) -> FlatRuleSet:
    price_rules = _select_rule(
        rule_block,
        "price_rules",
        default=[
            "waveB_ratio >= 0.618",
            "waveC_length >= 0.382 * waveA_length",
            "waveB_ratio <= 0.8 -> weak B flat",
            "0.81 <= waveB_ratio <= 1.0 -> normal flat",
            "waveB_ratio > 1.0 -> expanded flat",
            "if expanded and waveB_ratio <= 1.236",
            "if waveC_length > 1.38 * waveB_length -> elongated flat",
        ],
    )
    b_rule = next((rule for rule in price_rules if "waveB_ratio >=" in rule), "")
    c_rule = next((rule for rule in price_rules if "waveC_length" in rule and ">=" in rule), "")
    elongated_rule = next((rule for rule in price_rules if "1.38" in rule or "elongated" in rule), "")

    b_min = _first_number(b_rule, 0.618)
    c_min = _first_number(c_rule, 0.382)
    c_elongated = _first_number(elongated_rule, 1.38)

    return FlatRuleSet(
        b_min=b_min,
        weak_b_threshold=0.8,
        expanded_b_threshold=1.0,
        running_flat_b_threshold=1.236,
        c_min=c_min,
        c_elongated=c_elongated,
    )


@dataclass(slots=True)
class TriangleRuleSet:
    contracting_c_to_a: float = 0.618
    contracting_e_min: float = 0.382
    contracting_e_max: float = 0.99
    expanding_c_min: float = 1.01
    expanding_e_min: float = 1.01
    expanding_e_max: float = 2.618
    neutral_a_min: float = 0.382
    neutral_a_max: float = 0.72
    neutral_e_min: float = 0.382
    neutral_e_max: float = 0.72
    similarity_tolerance: float = 0.8


def extract_triangle_rules(rule_block: dict[str, Any] | None) -> TriangleRuleSet:
    contracting_rules = _select_rule(rule_block.get("Contracting") if rule_block else None, "price_rules", default=[])
    expanding_rules = _select_rule(rule_block.get("Expanding") if rule_block else None, "price_rules", default=[])
    neutral_rules = _select_rule(rule_block.get("Neutral") if rule_block else None, "price_rules", default=[])

    contract_c_rule = next((rule for rule in contracting_rules if "waveC_length" in rule), "")
    contract_e_rule = next((rule for rule in contracting_rules if "waveE_length" in rule), "")
    expand_c_rule = next((rule for rule in expanding_rules if "waveC_length" in rule), "")
    expand_e_rule = next((rule for rule in expanding_rules if "waveE_length" in rule), "")
    neutral_a_rule = next((rule for rule in neutral_rules if "waveA_length" in rule), "")
    neutral_e_rule = next((rule for rule in neutral_rules if "waveE_length" in rule), "")

    contracting_c_to_a = _first_number(contract_c_rule, 0.618)
    contracting_e_min, contracting_e_max = _range_from_rule(contract_e_rule, (0.382, 0.99))
    expanding_c_min = _first_number(expand_c_rule, 1.01)
    expanding_e_min = _first_number(expand_e_rule, 1.01)
    expanding_e_numbers = _numbers_from_rule(expand_e_rule)
    expanding_e_max = max([num for num in expanding_e_numbers if num >= expanding_e_min] or [2.618])
    neutral_a_min, neutral_a_max = _range_from_rule(neutral_a_rule, (0.382, 0.72))
    neutral_e_min, neutral_e_max = _range_from_rule(neutral_e_rule, (0.382, 0.72))

    return TriangleRuleSet(
        contracting_c_to_a=contracting_c_to_a,
        contracting_e_min=contracting_e_min,
        contracting_e_max=contracting_e_max,
        expanding_c_min=expanding_c_min,
        expanding_e_min=expanding_e_min,
        expanding_e_max=expanding_e_max,
        neutral_a_min=neutral_a_min,
        neutral_a_max=neutral_a_max,
        neutral_e_min=neutral_e_min,
        neutral_e_max=neutral_e_max,
        similarity_tolerance=0.8,
    )


@dataclass(slots=True)
class TerminalImpulseRuleSet:
    correction_depth_min: float = 0.33
    proportion_similarity: float = 0.5


def extract_terminal_impulse_rules(rule_block: dict[str, Any] | None) -> TerminalImpulseRuleSet:
    return TerminalImpulseRuleSet()
