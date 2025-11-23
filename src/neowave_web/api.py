from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from neowave_core import AnalysisConfig, detect_swings, generate_scenarios, load_rules
from neowave_core.data_loader import DataLoaderError, fetch_ohlcv
from neowave_web.schemas import CandleResponse, ScenariosResponse, SwingsResponse

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
    config = analysis_config or AnalysisConfig()
    provider = data_provider or _default_data_provider

    app = FastAPI(title="NEoWave Web Service", version="0.2.0")
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
        limit: int = Query(config.lookback, ge=10, le=2000),
        symbol: str = Query(config.symbol),
        interval: str = Query(config.interval),
    ) -> CandleResponse:
        df = _get_df(limit, symbol=symbol, interval=interval)
        if not df.empty:
            df = df.tail(limit)
        candles = _serialize_candles(df)
        return CandleResponse(candles=candles, count=len(candles))

    @app.get("/api/swings", response_model=SwingsResponse)
    def get_swings(
        limit: int = Query(config.lookback, ge=10, le=2000),
        symbol: str = Query(config.symbol),
        interval: str = Query(config.interval),
        price_threshold: float = Query(config.price_threshold_pct, ge=0.001, le=0.2),
        similarity_threshold: float = Query(config.similarity_threshold, ge=0.1, le=1.0),
    ) -> SwingsResponse:
        df = _get_df(limit, symbol=symbol, interval=interval)
        swings = detect_swings(
            df,
            price_threshold_pct=price_threshold,
            similarity_threshold=similarity_threshold,
        )
        serialized = [_serialize_swing(s) for s in swings]
        return SwingsResponse(swings=serialized, count=len(serialized))

    @app.get("/api/scenarios", response_model=ScenariosResponse)
    def get_scenarios(
        limit: int = Query(config.lookback, ge=10, le=2000),
        symbol: str = Query(config.symbol),
        interval: str = Query(config.interval),
        max_scenarios: int = Query(8, ge=1, le=20),
        price_threshold: float = Query(config.price_threshold_pct, ge=0.001, le=0.2),
        similarity_threshold: float = Query(config.similarity_threshold, ge=0.1, le=1.0),
    ) -> ScenariosResponse:
        df = _get_df(limit, symbol=symbol, interval=interval)
        swings = detect_swings(
            df,
            price_threshold_pct=price_threshold,
            similarity_threshold=similarity_threshold,
        )
        rules = _load_rules_with_fallback()
        scenarios = generate_scenarios(swings, rules, max_scenarios=max_scenarios)
        return ScenariosResponse(scenarios=scenarios, count=len(scenarios))

    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
