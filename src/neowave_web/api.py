from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pandas as pd
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from neowave_core import (
    AnalysisConfig,
    ParseSettings,
    detect_swings,
    detect_swings_multi_scale,
    generate_scenarios,
    generate_scenarios_multi_scale,
    identify_major_pivots,
    load_rules,
)
from neowave_core.data_loader import DataLoaderError, fetch_ohlcv
from neowave_web.schemas import (
    CandleResponse,
    CustomRangeRequest,
    CustomRangeResponse,
    ScenariosResponse,
    SwingsResponse,
)

STATIC_DIR = Path(__file__).parent / "static"


def _default_data_provider(symbol: str, interval: str, limit: int, **_: Any) -> pd.DataFrame:
    return fetch_ohlcv(symbol, interval=interval, limit=limit)


def _serialize_swing(swing) -> dict[str, Any]:
    return {
        "start_time": swing.start_time,
        "end_time": swing.end_time,
        "start_price": swing.start_price,
        "end_price": swing.end_price,
        "direction": swing.direction.value,
        "high": swing.high,
        "low": swing.low,
        "duration": swing.duration,
        "volume": swing.volume,
    }


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


def _load_rules_with_fallback() -> dict[str, Any]:
    try:
        return load_rules()
    except FileNotFoundError:
        project_root = Path(__file__).resolve().parents[3]
        fallback = project_root / "rules" / "neowave_rules.json"
        return load_rules(fallback)


def create_app(
    analysis_config: AnalysisConfig | None = None,
    data_provider: Callable[..., pd.DataFrame] | None = None,
) -> FastAPI:
    """Create a FastAPI application serving NEoWave data and scenarios."""
    load_dotenv()
    config = analysis_config or AnalysisConfig.from_env()
    provider = data_provider or _default_data_provider

    app = FastAPI(title="NEoWave Web Service", version="0.2.1")
    index_html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    def _get_df(limit: int, symbol: str | None = None, interval: str | None = None) -> pd.DataFrame:
        try:
            return provider(symbol or config.symbol, interval=interval or config.interval, limit=limit)
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

    def _resolve_swings(
        df: pd.DataFrame,
        scale_id: str,
        price_threshold: float | None,
        similarity_threshold: float | None,
        min_price_retrace_ratio: float | None = None,
        min_time_ratio: float | None = None,
    ) -> tuple[list, list, float, float, float, float]:
        if price_threshold is not None or similarity_threshold is not None:
            price_threshold_effective = price_threshold if price_threshold is not None else config.price_threshold_pct
            similarity_effective = similarity_threshold if similarity_threshold is not None else config.similarity_threshold
            min_price_effective = min_price_retrace_ratio if min_price_retrace_ratio is not None else config.min_price_retrace_ratio
            min_time_effective = min_time_ratio if min_time_ratio is not None else config.min_time_ratio
            swings = detect_swings(
                df,
                price_threshold_pct=price_threshold_effective,
                similarity_threshold=similarity_effective,
                min_price_retrace_ratio=min_price_effective,
                min_time_ratio=min_time_effective,
                target_count_range=config.swing_count_range,
            )
            return swings, [], similarity_effective, price_threshold_effective, min_price_effective, min_time_effective

        swing_sets = detect_swings_multi_scale(df, scales=config.swing_scales)
        selected = next((s for s in swing_sets if s.scale_id == scale_id), None)
        if not selected and swing_sets:
            selected = next((s for s in swing_sets if s.scale_id == "base"), swing_sets[0])
        similarity_effective = config.similarity_threshold
        price_threshold_effective = config.price_threshold_pct
        min_price_effective = config.min_price_retrace_ratio
        min_time_effective = config.min_time_ratio
        if selected:
            for scale_cfg in config.swing_scales:
                if scale_cfg.get("id") == selected.scale_id:
                    price_threshold_effective = scale_cfg.get("price_threshold_pct", price_threshold_effective)
                    similarity_effective = scale_cfg.get("similarity_threshold", similarity_effective)
                    min_price_effective = scale_cfg.get("min_price_retrace_ratio", min_price_effective)
                    min_time_effective = scale_cfg.get("min_time_ratio", min_time_effective)
                    break
        return (
            list(selected.swings) if selected else [],
            swing_sets,
            similarity_effective,
            price_threshold_effective,
            float(min_price_effective),
            float(min_time_effective),
        )

    @app.get("/api/swings", response_model=SwingsResponse)
    def get_swings(
        limit: int = Query(config.lookback, ge=1, le=2000),
        symbol: str = Query(config.symbol),
        interval: str = Query(config.interval),
        price_threshold: float | None = Query(None, ge=0.001, le=0.2),
        similarity_threshold: float | None = Query(None, ge=0.1, le=1.0),
        min_price_retrace_ratio: float | None = Query(None, ge=0.1, le=1.0),
        min_time_ratio: float | None = Query(None, ge=0.1, le=1.0),
        scale_id: str = Query("base"),
    ) -> SwingsResponse:
        df = _get_df(limit, symbol=symbol, interval=interval)
        swings, swing_sets, _, _, _, _ = _resolve_swings(
            df,
            scale_id,
            price_threshold,
            similarity_threshold,
            min_price_retrace_ratio,
            min_time_ratio,
        )
        serialized = [_serialize_swing(s) for s in swings]
        return SwingsResponse(swings=serialized, count=len(serialized), scale_id=scale_id)

    @app.get("/api/scenarios", response_model=ScenariosResponse)
    def get_scenarios(
        limit: int = Query(config.lookback, ge=1, le=2000),
        symbol: str = Query(config.symbol),
        interval: str = Query(config.interval),
        max_scenarios: int = Query(8, ge=1, le=20),
        max_pivots: int = Query(5, ge=1, le=10),
        price_threshold: float | None = Query(None, ge=0.001, le=0.2),
        similarity_threshold: float | None = Query(None, ge=0.1, le=1.0),
        min_price_retrace_ratio: float | None = Query(None, ge=0.1, le=1.0),
        min_time_ratio: float | None = Query(None, ge=0.1, le=1.0),
        scale_id: str = Query("base"),
    ) -> ScenariosResponse:
        df = _get_df(limit, symbol=symbol, interval=interval)
        swings, swing_sets, similarity_effective, _, _, _ = _resolve_swings(
            df,
            scale_id,
            price_threshold,
            similarity_threshold,
            min_price_retrace_ratio,
            min_time_ratio,
        )
        rules = _load_rules_with_fallback()
        current_price = float(df["close"].iloc[-1]) if not df.empty else None
        context_summary = {s.scale_id: len(s.swings) for s in swing_sets} if swing_sets else {}
        scenarios = generate_scenarios(
            swings,
            rules,
            max_pivots=max_pivots,
            max_scenarios=max_scenarios,
            current_price=current_price,
            settings=ParseSettings(similarity_threshold=similarity_effective),
            scale_id=scale_id,
            swing_sets=swing_sets,
        )
        for sc in scenarios:
            sc.setdefault("details", {})
            sc["details"]["scale_context"] = context_summary
        return ScenariosResponse(scenarios=scenarios, count=len(scenarios))

    @app.post("/api/analyze/custom-range", response_model=CustomRangeResponse)
    def analyze_custom_range(payload: CustomRangeRequest = Body(...)) -> CustomRangeResponse:
        start_dt = pd.to_datetime(payload.start_ts, unit="s", utc=True)
        end_dt = pd.to_datetime(payload.end_ts, unit="s", utc=True)
        if start_dt >= end_dt:
            raise HTTPException(status_code=400, detail="start_ts must be earlier than end_ts")

        df = _get_df(config.lookback * 2, symbol=payload.symbol, interval=payload.interval)
        df_slice = df[(df["timestamp"] >= start_dt) & (df["timestamp"] <= end_dt)].reset_index(drop=True)
        if df_slice.empty:
            raise HTTPException(status_code=400, detail="No candles in the requested range")

        swings = detect_swings(
            df_slice,
            price_threshold_pct=config.price_threshold_pct,
            similarity_threshold=config.similarity_threshold,
            min_price_retrace_ratio=config.min_price_retrace_ratio,
            min_time_ratio=config.min_time_ratio,
            target_count_range=config.swing_count_range,
        )
        rules = _load_rules_with_fallback()
        current_price = float(df_slice["close"].iloc[-1]) if not df_slice.empty else None
        scenarios = generate_scenarios(
            swings,
            rules,
            max_pivots=payload.max_pivots or 5,
            max_scenarios=payload.max_scenarios or 3,
            current_price=current_price,
            settings=ParseSettings(similarity_threshold=config.similarity_threshold),
            scale_id="custom",
            anchor_indices=[0],
        )
        anchors = identify_major_pivots(swings, max_pivots=payload.max_pivots or 5)
        anchor_candidates = [
            {"idx": idx, "start_time": swings[idx].start_time, "start_price": swings[idx].start_price} for idx in anchors if 0 <= idx < len(swings)
        ]
        return CustomRangeResponse(
            scenarios=scenarios,
            count=len(scenarios),
            anchor_candidates=anchor_candidates,
            candles=_serialize_candles(df_slice),
            swings=[_serialize_swing(sw) for sw in swings],
        )

    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
