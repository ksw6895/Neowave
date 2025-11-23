from __future__ import annotations

import argparse
import logging
import sys

from dotenv import load_dotenv

from neowave_core.config import (
    AnalysisConfig,
    DEFAULT_INTERVAL,
    DEFAULT_LOOKBACK,
    DEFAULT_MIN_PRICE_RETRACE_RATIO,
    DEFAULT_MIN_TIME_RATIO,
    DEFAULT_SIMILARITY_THRESHOLD,
    DEFAULT_SYMBOL,
    DEFAULT_TARGET_MONOWAVES,
)
from neowave_core.data_loader import DataLoaderError, fetch_ohlcv
from neowave_core.rules_db import RULE_DB
from neowave_core.scenarios import generate_scenarios
from neowave_core.swings import detect_monowaves_from_df

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    env_defaults = AnalysisConfig.from_env()
    parser = argparse.ArgumentParser(description="Fractal NEoWave scenario engine")
    parser.add_argument("--symbol", default=env_defaults.symbol or DEFAULT_SYMBOL, help="Symbol to analyze (default: BTCUSD)")
    parser.add_argument("--interval", default=env_defaults.interval or DEFAULT_INTERVAL, help="Candle interval (default: 1hour)")
    parser.add_argument("--lookback", type=int, default=env_defaults.lookback or DEFAULT_LOOKBACK, help="Number of candles to request")
    parser.add_argument(
        "--retrace-price",
        type=float,
        default=env_defaults.min_price_retrace_ratio or DEFAULT_MIN_PRICE_RETRACE_RATIO,
        help="Minimum opposing retrace (fraction) to start a new monowave (default 0.236)",
    )
    parser.add_argument(
        "--retrace-time",
        type=float,
        default=env_defaults.min_time_ratio or DEFAULT_MIN_TIME_RATIO,
        help="Minimum opposing time ratio to start a new monowave (default 0.2)",
    )
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=env_defaults.similarity_threshold or DEFAULT_SIMILARITY_THRESHOLD,
        help="Rule of Similarity threshold for merging monowaves (default 0.33)",
    )
    parser.add_argument("--target-waves", type=int, default=env_defaults.target_monowaves or DEFAULT_TARGET_MONOWAVES, help="Target visible wave count for view level selection")
    parser.add_argument("--max-scenarios", type=int, default=5, help="Maximum scenarios to display")
    parser.add_argument("--api-key", dest="api_key", default=None, help="FMP API key (overrides env if provided)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        df = fetch_ohlcv(args.symbol, interval=args.interval, limit=args.lookback, api_key=args.api_key)
    except DataLoaderError as exc:
        logger.error("Failed to fetch OHLCV: %s", exc)
        return 1
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error fetching OHLCV: %s", exc)
        return 1

    monowaves = detect_monowaves_from_df(
        df,
        retrace_threshold_price=args.retrace_price,
        retrace_threshold_time_ratio=args.retrace_time,
        similarity_threshold=args.similarity_threshold,
    )
    logger.info("Detected %s monowaves after similarity merge", len(monowaves))

    scenarios = generate_scenarios(
        monowaves,
        rule_db=RULE_DB,
        target_wave_count=args.target_waves,
    )
    if not scenarios:
        print("No scenarios detected with current parameters.")
        return 0

    for idx, scenario in enumerate(scenarios[: args.max_scenarios], start=1):
        print(f"[Scenario {idx}] Score={scenario['global_score']:.3f} Status={scenario['status']}")
        roots = scenario.get("roots", [])
        root_desc = ", ".join(f"{r['pattern_type'] or 'Monowave'}[{r['start_idx']}-{r['end_idx']}]" for r in roots)
        print(f"  Roots: {root_desc}")
        print(f"  View level {scenario.get('view_level', 0)} nodes: {len(scenario.get('view_nodes', []))}")
        if scenario.get("invalidation_reasons"):
            print(f"  Invalidation: {scenario['invalidation_reasons']}")
        print()

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
