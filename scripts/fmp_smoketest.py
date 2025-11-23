"""Quick FMP connectivity check."""

from __future__ import annotations

import os
import sys

import requests


def main(symbol: str = "BTCUSD", interval: str = "1hour", limit: int = 5) -> int:
    api_key = os.getenv("FMP_API_KEY")
    if not api_key:
        print("FMP_API_KEY is not set; export it or pass via environment.")
        return 1

    url = f"https://financialmodelingprep.com/api/v3/historical-chart/{interval}/{symbol}"
    params = {"apikey": api_key, "limit": limit}
    try:
        resp = requests.get(url, params=params, timeout=15)
    except requests.RequestException as exc:
        print(f"Request failed: {exc}")
        return 1

    print(f"Status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"Body: {resp.text[:300]}")
        return 1

    try:
        data = resp.json()
    except ValueError:
        print("Failed to parse JSON")
        print(resp.text[:300])
        return 1

    if isinstance(data, list):
        print(f"Received {len(data)} records")
        if data:
            first = data[0]
            snippet = {k: first[k] for k in list(first)[:4]}
            print(f"First item: {snippet}")
    else:
        print(f"Response JSON: {data}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
