from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Iterable

import pandas as pd
import requests

from neowave_core.config import FMP_BASE_URL

logger = logging.getLogger(__name__)


class DataLoaderError(RuntimeError):
    """Raised when OHLCV retrieval fails."""


def _ensure_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return pd.to_datetime(value, utc=True).to_pydatetime()


def _build_dataframe(records: Iterable[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for item in records:
        timestamp = _ensure_datetime(item.get("date") or item.get("timestamp"))
        rows.append(
            {
                "timestamp": timestamp,
                "open": float(item["open"]),
                "high": float(item["high"]),
                "low": float(item["low"]),
                "close": float(item["close"]),
                "volume": float(item.get("volume", 0.0)),
            }
        )
    if not rows:
        raise DataLoaderError("Received empty data set from FMP API")
    df = pd.DataFrame(rows)
    return df.sort_values("timestamp").reset_index(drop=True)


def fetch_ohlcv(
    symbol: str,
    interval: str = "1hour",
    limit: int = 1000,
    api_key: str | None = None,
    session: requests.Session | None = None,
    base_url: str = FMP_BASE_URL,
) -> pd.DataFrame:
    """Fetch OHLCV candles from FMP."""
    key = api_key or os.getenv("FMP_API_KEY")
    if not key:
        raise DataLoaderError("FMP_API_KEY is missing; set environment variable or pass api_key.")

    url = f"{base_url}/{interval}/{symbol.upper()}"
    params = {"apikey": key, "limit": int(limit)}
    client = session or requests.Session()
    try:
        response = client.get(url, params=params, timeout=15)
    except requests.RequestException as exc:
        raise DataLoaderError(f"Network error while fetching OHLCV: {exc}") from exc

    if response.status_code != 200:
        raise DataLoaderError(f"FMP API returned status {response.status_code}: {response.text}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise DataLoaderError("Failed to parse FMP response as JSON") from exc

    if not isinstance(payload, list):
        raise DataLoaderError(f"Unexpected FMP response shape: {payload}")
    df = _build_dataframe(payload)
    logger.info("Fetched %s candles for %s (%s)", len(df), symbol.upper(), interval)
    return df
