from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import logging
import time

import pandas as pd
from dotenv import load_dotenv
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from neowave_core import AnalysisConfig, RULE_DB, detect_monowaves_from_df, fetch_ohlcv, generate_scenarios, MacroScanner, verify_pattern, WaveNode, Monowave
from neowave_core.data_loader import DataLoaderError
from neowave_core.scenarios import find_wave_node, serialize_wave_node, serialize_scenario
from neowave_web.schemas import CandleResponse, MonowaveResponse, RuleXRayResponse, ScenariosResponse, WaveChildrenResponse

STATIC_DIR = Path(__file__).parent / "static"


def _default_data_provider(symbol: str, interval: str, limit: int, **_: Any) -> pd.DataFrame:
    return fetch_ohlcv(symbol, interval=interval, limit=limit)


def _serialize_monowave(mw) -> dict[str, Any]:
    return mw.to_dict()


def _serialize_candles(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {
            "timestamp": pd.to_datetime(row.timestamp, utc=True),
            "open": float(row.open),
            "high": float(row.high),
            "low": float(row.low),
            "close": float(row.close),
            "volume": float(row.volume),
        }
        for row in df.itertuples(index=False)
    ]


def create_app(
    analysis_config: AnalysisConfig | None = None,
    data_provider: Callable[..., pd.DataFrame] | None = None,
) -> FastAPI:
    """Create a FastAPI application serving NEoWave data and scenarios."""
    logger = logging.getLogger("neowave_web.api")
    load_dotenv()
    config = analysis_config or AnalysisConfig.from_env()
    provider = data_provider or _default_data_provider

    app = FastAPI(title="NEoWave Web Service", version="0.3.0")
    index_html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    def _get_df(limit: int, symbol: str | None = None, interval: str | None = None) -> pd.DataFrame:
        try:
            t0 = time.perf_counter()
            result = provider(symbol or config.symbol, interval=interval or config.interval, limit=limit)
            logger.info(
                "Fetched OHLCV symbol=%s interval=%s limit=%s rows=%s (%.3fs)",
                symbol or config.symbol,
                interval or config.interval,
                limit,
                len(result),
                time.perf_counter() - t0,
            )
            return result
        except DataLoaderError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Unexpected error fetching data: {exc}") from exc

    @app.get("/", response_class=HTMLResponse)
    def root() -> str:
        return index_html

    @app.get("/api/ohlcv", response_model=CandleResponse)
    def get_ohlcv(
        limit: int = Query(config.lookback, ge=1, le=2000),
        symbol: str = Query(config.symbol),
        interval: str = Query(config.interval),
    ) -> CandleResponse:
        df = _get_df(limit, symbol=symbol, interval=interval)
        if not df.empty:
            df = df.tail(limit)
        candles = _serialize_candles(df)
        return CandleResponse(candles=candles, count=len(candles))

    @app.get("/api/monowaves", response_model=MonowaveResponse)
    def get_monowaves(
        limit: int = Query(config.lookback, ge=1, le=2000),
        symbol: str = Query(config.symbol),
        interval: str = Query(config.interval),
        retrace_price: float = Query(config.min_price_retrace_ratio, ge=0.05, le=1.0),
        retrace_time: float = Query(config.min_time_ratio, ge=0.05, le=1.0),
        similarity_threshold: float = Query(config.similarity_threshold, ge=0.1, le=1.0),
    ) -> MonowaveResponse:
        df = _get_df(limit, symbol=symbol, interval=interval)
        t0 = time.perf_counter()
        monowaves = detect_monowaves_from_df(
            df,
            retrace_threshold_price=retrace_price,
            retrace_threshold_time_ratio=retrace_time,
            similarity_threshold=similarity_threshold,
        )
        logger.info(
            "Monowaves detected count=%s symbol=%s interval=%s retrace_price=%.3f retrace_time=%.3f similarity=%.3f (%.3fs)",
            len(monowaves),
            symbol,
            interval,
            retrace_price,
            retrace_time,
            similarity_threshold,
            time.perf_counter() - t0,
        )
        serialized = [_serialize_monowave(mw) for mw in monowaves]
        return MonowaveResponse(monowaves=serialized, count=len(serialized))

    @app.get("/api/scenarios", response_model=ScenariosResponse)
    def get_scenarios(
        limit: int = Query(config.lookback, ge=1, le=2000),
        symbol: str = Query(config.symbol),
        interval: str = Query(config.interval),
        target_wave_count: int = Query(config.target_monowaves, ge=5, le=120),
        beam_width: int = Query(6, ge=2, le=12),
    ) -> ScenariosResponse:
        df = _get_df(limit, symbol=symbol, interval=interval)
        t0 = time.perf_counter()
        monowaves = detect_monowaves_from_df(
            df,
            retrace_threshold_price=config.min_price_retrace_ratio,
            retrace_threshold_time_ratio=config.min_time_ratio,
            similarity_threshold=config.similarity_threshold,
        )
        t1 = time.perf_counter()
        scenarios = generate_scenarios(monowaves, rule_db=RULE_DB, beam_width=beam_width, target_wave_count=target_wave_count)
        t2 = time.perf_counter()
        logger.info(
            "Scenarios built symbol=%s interval=%s monowaves=%s scenarios=%s target=%s beam=%s detect=%.3fs analyze=%.3fs total=%.3fs",
            symbol,
            interval,
            len(monowaves),
            len(scenarios),
            target_wave_count,
            beam_width,
            t1 - t0,
            t2 - t1,
            t2 - t0,
        )
        return ScenariosResponse(scenarios=scenarios, count=len(scenarios))

    @app.get("/api/waves/current", response_model=WaveChildrenResponse)
    def get_view_nodes(
        limit: int = Query(config.lookback, ge=1, le=2000),
        symbol: str = Query(config.symbol),
        interval: str = Query(config.interval),
        target_wave_count: int = Query(config.target_monowaves, ge=5, le=120),
    ) -> WaveChildrenResponse:
        df = _get_df(limit, symbol=symbol, interval=interval)
        monowaves = detect_monowaves_from_df(df, retrace_threshold_price=config.min_price_retrace_ratio, retrace_threshold_time_ratio=config.min_time_ratio, similarity_threshold=config.similarity_threshold)
        scenarios = generate_scenarios(monowaves, rule_db=RULE_DB, target_wave_count=target_wave_count)
        if not scenarios:
            return WaveChildrenResponse(parent_id=-1, children=[])
        view_nodes = scenarios[0].get("view_nodes", [])
        return WaveChildrenResponse(parent_id=scenarios[0]["id"], children=view_nodes)

    @app.get("/api/waves/{wave_id}/children", response_model=WaveChildrenResponse)
    def get_wave_children(
        wave_id: int,
        limit: int = Query(config.lookback, ge=1, le=2000),
        symbol: str = Query(config.symbol),
        interval: str = Query(config.interval),
    ) -> WaveChildrenResponse:
        df = _get_df(limit, symbol=symbol, interval=interval)
        monowaves = detect_monowaves_from_df(df, retrace_threshold_price=config.min_price_retrace_ratio, retrace_threshold_time_ratio=config.min_time_ratio, similarity_threshold=config.similarity_threshold)
        node = find_wave_node(monowaves, wave_id, rule_db=RULE_DB)
        if not node:
            raise HTTPException(status_code=404, detail="Wave not found")
        return WaveChildrenResponse(parent_id=wave_id, children=[serialize_wave_node(child) for child in node.children])

    @app.get("/api/waves/{wave_id}/rules", response_model=RuleXRayResponse)
    def get_wave_rules(
        wave_id: int,
        limit: int = Query(config.lookback, ge=1, le=2000),
        symbol: str = Query(config.symbol),
        interval: str = Query(config.interval),
    ) -> RuleXRayResponse:
        df = _get_df(limit, symbol=symbol, interval=interval)
        monowaves = detect_monowaves_from_df(df, retrace_threshold_price=config.min_price_retrace_ratio, retrace_threshold_time_ratio=config.min_time_ratio, similarity_threshold=config.similarity_threshold)
        node = find_wave_node(monowaves, wave_id, rule_db=RULE_DB)
        if not node:
            raise HTTPException(status_code=404, detail="Wave not found")
        return RuleXRayResponse(
            wave_id=wave_id,
            pattern_type=node.pattern_type,
            pattern_subtype=node.pattern_subtype,
            metrics=node.metrics,
            validation=serialize_wave_node(node).get("validation"),
        )

    @app.post("/api/analyze/custom-range", response_model=ScenariosResponse)
    def analyze_custom_range(payload: dict[str, Any] = Body(...)) -> ScenariosResponse:
        symbol = payload.get("symbol", config.symbol)
        interval = payload.get("interval", config.interval)
        start_ts = payload.get("start_ts")
        end_ts = payload.get("end_ts")
        if start_ts is None or end_ts is None:
            raise HTTPException(status_code=400, detail="start_ts and end_ts are required")
        start_dt = pd.to_datetime(start_ts, unit="s", utc=True)
        end_dt = pd.to_datetime(end_ts, unit="s", utc=True)
        if start_dt >= end_dt:
            raise HTTPException(status_code=400, detail="start_ts must be earlier than end_ts")

        df = _get_df(config.lookback * 2, symbol=symbol, interval=interval)
        df_slice = df[(df["timestamp"] >= start_dt) & (df["timestamp"] <= end_dt)].reset_index(drop=True)
        if df_slice.empty:
            raise HTTPException(status_code=400, detail="No candles in the requested range")

        monowaves = detect_monowaves_from_df(
            df_slice,
            retrace_threshold_price=config.min_price_retrace_ratio,
            retrace_threshold_time_ratio=config.min_time_ratio,
            similarity_threshold=config.similarity_threshold,
        )
        target_wave_count = int(payload.get("target_wave_count", config.target_monowaves))
        scenarios = generate_scenarios(monowaves, rule_db=RULE_DB, target_wave_count=target_wave_count)
        return ScenariosResponse(scenarios=scenarios, count=len(scenarios))

    @app.post("/api/scan/macro", response_model=ScenariosResponse)
    def scan_macro(
        payload: dict[str, Any] = Body(...),
    ) -> ScenariosResponse:
        symbol = payload.get("symbol", config.symbol)
        interval = payload.get("interval", config.interval)
        limit = payload.get("limit", config.lookback)
        target_wave_count = payload.get("target_wave_count", 12)
        
        df = _get_df(limit, symbol=symbol, interval=interval)
        
        scanner = MacroScanner(RULE_DB)
        scenarios = scanner.scan(df, target_wave_count=target_wave_count)
        
        # Serialize scenarios
        serialized = [serialize_scenario(sc) for sc in scenarios]
        return ScenariosResponse(scenarios=serialized, count=len(serialized))

    @app.post("/api/verify/pattern")
    def verify_pattern_endpoint(
        payload: dict[str, Any] = Body(...),
    ) -> dict[str, Any]:
        # Extract macro node and micro data params
        macro_node_data = payload.get("macro_node")
        if not macro_node_data:
            raise HTTPException(status_code=400, detail="macro_node is required")
            
        symbol = payload.get("symbol", config.symbol)
        interval = payload.get("interval", config.interval)
        limit = payload.get("limit", config.lookback)
        
        # Reconstruct WaveNode from dict (simplified)
        # In a real app, we might need a proper deserializer
        # For now, we assume basic fields are present
        try:
            macro_node = WaveNode(
                id=macro_node_data["id"],
                level=macro_node_data["level"],
                degree_label=macro_node_data.get("degree_label", ""),
                start_idx=macro_node_data["start_idx"],
                end_idx=macro_node_data["end_idx"],
                start_time=pd.to_datetime(macro_node_data["start_time"]),
                end_time=pd.to_datetime(macro_node_data["end_time"]),
                start_price=macro_node_data["start_price"],
                end_price=macro_node_data["end_price"],
                high_price=macro_node_data["high_price"],
                low_price=macro_node_data["low_price"],
                direction=macro_node_data["direction"],
                pattern_type=macro_node_data["pattern_type"],
                children=[] # Children not needed for verification target
            )
        except KeyError as e:
            raise HTTPException(status_code=400, detail=f"Invalid macro_node data: missing {e}")

        # Fetch micro data
        df = _get_df(limit, symbol=symbol, interval=interval)
        
        # Detect micro monowaves
        micro_monowaves = detect_monowaves_from_df(
            df,
            retrace_threshold_price=config.min_price_retrace_ratio,
            retrace_threshold_time_ratio=config.min_time_ratio,
            similarity_threshold=config.similarity_threshold,
        )
        
        # Verify
        validation = verify_pattern(macro_node, micro_monowaves, rule_db=RULE_DB)
        
        return {
            "hard_valid": validation.hard_valid,
            "soft_score": validation.soft_score,
            "satisfied_rules": validation.satisfied_rules,
            "violated_hard_rules": validation.violated_hard_rules,
            "violated_soft_rules": validation.violated_soft_rules
        }

    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
