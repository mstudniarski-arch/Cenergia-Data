import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from cenergia.ingest import openmeteo as om

FIXTURES = Path(__file__).parents[2] / "fixtures" / "openmeteo"


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None: ...

    def json(self) -> dict[str, Any]:
        return self._payload


def test_weights_sum_to_one() -> None:
    assert sum(c.weight for c in om.CITIES) == pytest.approx(1.0)


def test_fetch_history_long_format_and_units(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.loads((FIXTURES / "archive_city.json").read_text())
    seen_params: list[dict[str, Any]] = []

    def fake_get(url: str, params: dict[str, Any] | None = None, timeout: int = 0) -> FakeResponse:
        assert params is not None
        seen_params.append(params)
        return FakeResponse(payload)

    monkeypatch.setattr(om.requests, "get", fake_get)  # type: ignore[attr-defined]
    df = om.fetch_history(date(2024, 6, 14), date(2024, 6, 14))
    assert len(df) == 4 * len(om.CITIES)
    assert set(df.columns) == {"city", "ts_utc", "temp_c", "wind_ms", "ghi_wm2", "cloud_pct"}
    assert all(p["windspeed_unit"] == "ms" for p in seen_params)  # never km/h
    assert all(p["timezone"] == "UTC" for p in seen_params)
    assert str(df["ts_utc"].dtype) == "datetime64[ns]"


def test_fetch_forecast_uses_forecast_host(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.loads((FIXTURES / "forecast_city.json").read_text())
    urls: list[str] = []

    def fake_get(url: str, params: dict[str, Any] | None = None, timeout: int = 0) -> FakeResponse:
        urls.append(url)
        return FakeResponse(payload)

    monkeypatch.setattr(om.requests, "get", fake_get)  # type: ignore[attr-defined]
    df = om.fetch_forecast(days=2, past_days=1)
    assert all(u.startswith("https://api.open-meteo.com/v1/forecast") for u in urls)
    assert not df.empty


def test_cities_frame_shape() -> None:
    df = om.cities_frame()
    assert df.columns.tolist() == ["city", "lat", "lon", "weight"]
    assert len(df) == len(om.CITIES)


def test_connection_error_retries_then_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = {"n": 0}

    def always_fail(
        url: str, params: dict[str, Any] | None = None, timeout: int = 0
    ) -> FakeResponse:
        attempts["n"] += 1
        raise om.requests.ConnectionError("network down")  # type: ignore[attr-defined]

    monkeypatch.setattr(om.requests, "get", always_fail)  # type: ignore[attr-defined]
    monkeypatch.setattr(om.time, "sleep", lambda s: None)  # type: ignore[attr-defined]
    with pytest.raises(om.OpenMeteoError):
        om.fetch_history(date(2024, 6, 14), date(2024, 6, 14), cities=om.CITIES[:1])
    assert attempts["n"] == 4  # 1 try + 3 retries
