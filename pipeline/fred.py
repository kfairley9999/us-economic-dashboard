"""Minimal, key-safe FRED API client.

The API key is read from the ``FRED_API_KEY`` environment variable and is
never logged: FRED puts it in the query string, so request URLs and
``requests`` exceptions (which embed the URL) are never surfaced verbatim.
"""

from __future__ import annotations

import os
import time
from typing import Any

import pandas as pd
import requests

BASE_URL = "https://api.stlouisfed.org/fred"
_RETRY_STATUS = {429, 500, 502, 503, 504}


class FredError(RuntimeError):
    """Raised for FRED failures; messages never contain the API key."""


class FredClient:
    def __init__(
        self,
        api_key: str | None = None,
        session: requests.Session | None = None,
        retries: int = 4,
        backoff: float = 1.5,
        timeout: float = 30.0,
    ) -> None:
        key = api_key or os.environ.get("FRED_API_KEY", "")
        if not key.strip():
            raise FredError("FRED_API_KEY is not set")
        self._key = key.strip()
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", "us-economic-dashboard/1.0 (+github)")
        self._retries = retries
        self._backoff = backoff
        self._timeout = timeout

    def _get(self, endpoint: str, **params: Any) -> dict[str, Any]:
        params.update(api_key=self._key, file_type="json")
        what = f"{endpoint} {params.get('series_id', '')}".strip()
        for attempt in range(self._retries + 1):
            try:
                resp = self._session.get(f"{BASE_URL}/{endpoint}", params=params, timeout=self._timeout)
            except requests.RequestException as exc:  # network error; URL would leak the key
                reason = type(exc).__name__
                if attempt < self._retries:
                    time.sleep(self._backoff * 2**attempt)
                    continue
                raise FredError(f"FRED request failed for {what}: {reason}") from None
            if resp.status_code in _RETRY_STATUS and attempt < self._retries:
                time.sleep(self._backoff * 2**attempt)
                continue
            if resp.status_code != 200:
                raise FredError(f"FRED returned HTTP {resp.status_code} for {what}")
            return resp.json()
        raise FredError(f"FRED request failed for {what}")  # pragma: no cover

    def series_info(self, series_id: str) -> dict[str, Any]:
        data = self._get("series", series_id=series_id)
        items = data.get("seriess") or []
        if not items:
            raise FredError(f"No metadata for {series_id}")
        return items[0]

    def observations(self, series_id: str) -> pd.Series:
        data = self._get("series/observations", series_id=series_id)
        return parse_observations(data.get("observations", []), series_id)


def parse_observations(observations: list[dict[str, str]], name: str = "value") -> pd.Series:
    """Turn FRED's JSON observations into a float Series; '.' marks a missing value."""
    if not observations:
        return pd.Series(dtype="float64", name=name, index=pd.DatetimeIndex([], name="date"))
    df = pd.DataFrame(observations, columns=["date", "value"])
    idx = pd.DatetimeIndex(pd.to_datetime(df["date"]), name="date")
    values = pd.to_numeric(df["value"].replace(".", None), errors="coerce").to_numpy()
    s = pd.Series(values, index=idx, name=name, dtype="float64")
    return s.dropna().sort_index()
