from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

from neowave_core.config import (
    DEFAULT_INTERVAL,
    DEFAULT_LOOKBACK,
    DEFAULT_PRICE_THRESHOLD_PCT,
    DEFAULT_SIMILARITY_THRESHOLD,
    DEFAULT_SYMBOL,
)
from neowave_core.data_loader import DataLoaderError, fetch_ohlcv
from neowave_core.rules_loader import load_rules
from neowave_core.scenarios import generate_scenarios
from neowave_core.swings import detect_swings

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NEoWave Elliott Wave scenario engine (Phase 1)")
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL, help="Symbol to analyze (default: BTCUSD)")
    parser.add_argument("--interval", default=DEFAULT_INTERVAL, help="Candle interval (default: 1hour)")
    parser.add_argument("--lookback", type=int, default=DEFAULT_LOOKBACK, help="Number of candles to request")
    parser.add_argument(
        "--price-threshold",
        type=float,
        default=DEFAULT_PRICE_THRESHOLD_PCT,
        help="Reversal threshold for swing detection (fractional, default 0.01 => 1%%)",
    )
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=DEFAULT_SIMILARITY_THRESHOLD,
        help="Similarity threshold for merging swings (default 0.33)",
    )
    parser.add_argument("--max-scenarios", type=int, default=5, help="Maximum scenarios to display")
    parser.add_argument("--rules-path", default="rules/neowave_rules.json", help="Path to NEoWave rules JSON")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        rules = load_rules(args.rules_path)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load rules: %s", exc)
        return 1

    try:
        df = fetch_ohlcv(args.symbol, interval=args.interval, limit=args.lookback)
    except DataLoaderError as exc:
        logger.error("Failed to fetch OHLCV: %s", exc)
        return 1

    swings = detect_swings(
        df,
        price_threshold_pct=args.price_threshold,
        similarity_threshold=args.similarity_threshold,
    )
    logger.info("Using %s swings for scenario generation", len(swings))

    scenarios = generate_scenarios(swings, rules, max_scenarios=args.max_scenarios)
    if not scenarios:
        print("No scenarios detected with current parameters.")
        return 0

    for idx, scenario in enumerate(scenarios, start=1):
        print(f"Scenario {idx} (score: {scenario['score']:.2f})")
        print(f"  Pattern: {scenario['pattern_type']}")
        start_idx, end_idx = scenario["swing_indices"]
        print(f"  Swings: {start_idx} to {end_idx}")
        print(f"  Summary: {scenario['textual_summary']}")
        invalidation = scenario.get("invalidation_levels", {})
        if invalidation:
            print(f"  Invalidation: {invalidation}")
        print()

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
