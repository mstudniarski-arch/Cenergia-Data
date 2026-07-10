"""Open-Meteo weather client (archive + forecast). CC-BY-4.0, non-commercial tier.

Attribution: weather data by Open-Meteo.com (see README). Wind requested in m/s
explicitly — the API default is km/h.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd
import requests

_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_HOURLY_VARS = "temperature_2m,wind_speed_100m,shortwave_radiation,cloud_cover"
_RENAME = {
    "temperature_2m": "temp_c",
    "wind_speed_100m": "wind_ms",
    "shortwave_radiation": "ghi_wm2",
    "cloud_cover": "cloud_pct",
}
_TIMEOUT = 60
_RETRIES = 3


class OpenMeteoError(RuntimeError):
    """Open-Meteo failed after retries."""


@dataclass(frozen=True)
class City:
    name: str
    lat: float
    lon: float
    weight: float


CITIES: tuple[City, ...] = (
    City("warszawa", 52.23, 21.01, 0.25),
    City("krakow", 50.06, 19.94, 0.15),
    City("wroclaw", 51.11, 17.03, 0.12),
    City("poznan", 52.41, 16.93, 0.12),
    City("gdansk", 54.35, 18.65, 0.11),
    City("ustka_coast", 54.58, 16.86, 0.25),  # wind-belt proxy, deliberately over-weighted
)


def _get(url: str, params: dict[str, Any]) -> dict[str, Any]:
    last: Exception | None = None
    for attempt in range(_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, timeout=_TIMEOUT)
            resp.raise_for_status()
            return resp.json()  # type: ignore[no-any-return]
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
            last = exc
            if attempt < _RETRIES:
                time.sleep(2**attempt)
    raise OpenMeteoError(f"GET {url} failed after {_RETRIES + 1} attempts") from last


def _to_frame(payload: dict[str, Any], city: City) -> pd.DataFrame:
    hourly = payload["hourly"]
    df = pd.DataFrame(hourly).rename(columns=_RENAME | {"time": "ts_utc"})
    # Already UTC via timezone=UTC param; pandas 3.0.x returns us, cast to ns
    df["ts_utc"] = pd.to_datetime(df["ts_utc"]).astype("datetime64[ns]")
    df.insert(0, "city", city.name)
    for col in _RENAME.values():
        df[col] = df[col].astype("float64")
    return df[["city", "ts_utc", *_RENAME.values()]]


def _fetch(url: str, cities: tuple[City, ...], extra: dict[str, Any]) -> pd.DataFrame:
    frames = []
    for city in cities:
        params: dict[str, Any] = {
            "latitude": city.lat,
            "longitude": city.lon,
            "hourly": _HOURLY_VARS,
            "windspeed_unit": "ms",
            "timezone": "UTC",
            **extra,
        }
        frames.append(_to_frame(_get(url, params), city))
    return pd.concat(frames, ignore_index=True)


def fetch_history(start: date, end: date, cities: tuple[City, ...] = CITIES) -> pd.DataFrame:
    extra = {"start_date": start.isoformat(), "end_date": end.isoformat()}
    return _fetch(_ARCHIVE_URL, cities, extra)


def fetch_forecast(
    days: int = 2, past_days: int = 0, cities: tuple[City, ...] = CITIES
) -> pd.DataFrame:
    extra: dict[str, Any] = {"forecast_days": days}
    if past_days:
        extra["past_days"] = past_days
    return _fetch(_FORECAST_URL, cities, extra)


def cities_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [{"city": c.name, "lat": c.lat, "lon": c.lon, "weight": c.weight} for c in CITIES]
    )
