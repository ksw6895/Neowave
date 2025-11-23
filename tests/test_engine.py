from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
from fastapi.testclient import TestClient

from neowave_core.models import Monowave
from neowave_core.swings import detect_monowaves_from_df, merge_by_similarity
from neowave_core.wave_engine import analyze_market_structure
from neowave_web.api import create_app


def _bar(ts: datetime, close: float) -> dict[str, float]:
    return {"timestamp": ts, "open": close, "high": close, "low": close, "close": close, "volume": 1.0}


def test_monowave_detection_and_merge():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    closes = [100, 110, 103, 122, 118, 132, 125]
    df = pd.DataFrame([_bar(start + timedelta(hours=i), c) for i, c in enumerate(closes)])
    monowaves = detect_monowaves_from_df(df, retrace_threshold_price=0.1, retrace_threshold_time_ratio=0.2, similarity_threshold=0.4)
    assert len(monowaves) >= 3
    merged = merge_by_similarity(monowaves, min_ratio=0.4)
    assert len(merged) <= len(monowaves)


def test_analyze_builds_impulse_from_monowaves():
    base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)

    def mw(idx: int, start: float, end: float) -> Monowave:
        return Monowave(
            id=idx,
            start_idx=idx,
            end_idx=idx,
            start_time=base_time + timedelta(minutes=idx * 5),
            end_time=base_time + timedelta(minutes=idx * 5 + 1),
            start_price=start,
            end_price=end,
            high_price=max(start, end),
            low_price=min(start, end),
            direction="up" if end >= start else "down",
            price_change=end - start,
            abs_price_change=abs(end - start),
            duration=1,
            volume_sum=1.0,
        )

    # Simple 5-leg motive move (up-down-up-down-up)
    monowaves = [
        mw(0, 100, 110),
        mw(1, 110, 105),
        mw(2, 105, 125),
        mw(3, 125, 118),
        mw(4, 118, 140),
    ]
    scenarios = analyze_market_structure(monowaves)
    assert scenarios, "Expected at least one scenario"
    best = scenarios[0]
    assert best.root_nodes, "Expected root nodes"
    assert best.root_nodes[0].pattern_type == "Impulse"


def test_api_endpoints_return_data():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    closes = [100, 108, 102, 120, 115, 130, 122, 140]
    df = pd.DataFrame([_bar(start + timedelta(hours=i), c) for i, c in enumerate(closes)])

    def provider(symbol: str, interval: str, limit: int, **kwargs):  # noqa: ARG001
        return df

    app = create_app(data_provider=provider)
    client = TestClient(app)

    mono_resp = client.get("/api/monowaves")
    assert mono_resp.status_code == 200
    mono_data = mono_resp.json()
    assert mono_data["count"] > 0

    sc_resp = client.get("/api/scenarios")
    assert sc_resp.status_code == 200
    sc_data = sc_resp.json()
    assert sc_data["count"] >= 0
