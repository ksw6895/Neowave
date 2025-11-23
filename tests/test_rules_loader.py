from __future__ import annotations

from neowave_core.rules_loader import (
    extract_flat_rules,
    extract_impulse_rules,
    extract_triangle_rules,
    extract_zigzag_rules,
    load_rules,
)


def test_extract_impulse_rules_from_json():
    rules = load_rules("rules/neowave_rules.json")
    params = extract_impulse_rules(rules["Impulse"]["TrendingImpulse"])
    assert 0.23 <= params.wave2_min <= 0.24
    assert params.wave2_max == 1.0
    assert 1.6 <= params.extension_ratio <= 1.62
    assert 0.38 <= params.wave5_vs_wave4_min <= 0.39


def test_extract_correction_rules_from_json():
    rules = load_rules("rules/neowave_rules.json")
    zigzag = extract_zigzag_rules(rules["Corrections"]["Zigzag"])
    flat = extract_flat_rules(rules["Corrections"]["Flat"])
    triangle = extract_triangle_rules(rules["Corrections"]["Triangle"])

    assert zigzag.b_max <= 0.618
    assert zigzag.c_typical >= 0.618
    assert flat.b_min >= 0.618
    assert triangle.contracting_e_min >= 0.3
    assert triangle.expanding_c_min >= 1.0
