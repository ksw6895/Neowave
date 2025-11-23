from __future__ import annotations

from datetime import datetime

import pandas as pd
from fastapi.testclient import TestClient

from neowave_web.api import create_app


def dummy_provider(symbol: str, interval: str, limit: int, **_: object) -> pd.DataFrame:
    timestamps = pd.date_range(datetime(2024, 1, 1), periods=12, freq="H")
    closes = [100, 110, 95, 120, 108, 130, 118, 140, 130, 145, 135, 150]
    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
            "volume": [100] * len(closes),
        }
    )
    return df.head(limit)


def test_api_endpoints_return_payloads():
    app = create_app(data_provider=dummy_provider)
    client = TestClient(app)

    ohlcv_resp = client.get("/api/ohlcv?limit=50")
    assert ohlcv_resp.status_code == 200
    ohlcv = ohlcv_resp.json()
    assert ohlcv["count"] > 0

    swings_resp = client.get("/api/swings?limit=50&price_threshold=0.05")
    assert swings_resp.status_code == 200
    swings = swings_resp.json()
    assert "swings" in swings
    assert swings["count"] >= 1

    scenarios_resp = client.get("/api/scenarios?limit=50&max_scenarios=5&price_threshold=0.05")
    assert scenarios_resp.status_code == 200
    scenarios = scenarios_resp.json()
    assert "scenarios" in scenarios
    assert isinstance(scenarios["scenarios"], list)
