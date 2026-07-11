"""TDD for `live.py`: the runtime-live forecast pull/build/predict path.

Tests call `_get_live_forecast_uncached` directly (not the `st.cache_data`
-wrapped `get_live_forecast`) — Streamlit's cache decorator makes direct
testing awkward, the documented pattern here and in `data_access.py`.

Happy path monkeypatches `pse.fetch_entity`/`openmeteo.fetch_forecast` with
synthetic multi-week frames (`tests/helpers.py` builders extended for Task
18), fits a tiny real `LgbmModel` on the SAME synthetic matrix so
`FEATURES` line up exactly, and asserts a genuine 24-row, non-NaN
`y_pred` tomorrow. The degraded path forces a `PseApiError` and asserts the
fallback frame comes from `Snapshot.recent_hourly` with no exception
escaping.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from cenergia import paths
from cenergia.dashboard import data_access, live
from cenergia.features.matrix import FEATURES, build_matrix
from cenergia.ingest import pse
from cenergia.ingest.openmeteo import cities_frame
from cenergia.models.lgbm import LgbmModel
from cenergia.warehouse import db
from tests.helpers import (
    empty_ember_frame,
    empty_gen_frame,
    empty_nbp_frame,
    hourly_pse_frames,
    hourly_weather_frame,
)

NOW_UTC = pd.Timestamp("2026-03-15 09:00:00")
_START = NOW_UTC.normalize() - pd.Timedelta(days=50)
_HOURS = 53 * 24  # 50 trailing days + today + tomorrow + a spare day


def _synthetic_matrix() -> tuple[dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame]:
    """Build the same synthetic warehouse `live.py` would build live, so the
    fitted model's `FEATURES` and the live path's matrix are identical in
    shape. Returns (pse raw frames, weather frame, feature matrix).
    """
    pse_frames = hourly_pse_frames(str(_START), _HOURS)
    weather = hourly_weather_frame(str(_START), _HOURS)

    con = db.connect(":memory:")
    db.load_frames(
        con,
        {
            **pse_frames,
            "pse_his_gen_pal": empty_gen_frame(),
            "weather_history": weather,
            "weather_cities": cities_frame(),
            "nbp_fx": empty_nbp_frame(),
            "ember_pl": empty_ember_frame(),
        },
    )
    db.run_sql(con, paths.SQL_DIR)
    matrix = build_matrix(con)
    return pse_frames, weather, matrix


@pytest.fixture
def live_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Fits a tiny real LgbmModel on a synthetic matrix, saves it as a tmp
    artifact, points `live.paths.MODEL_PATH`/`MODEL_META` at it, and
    monkeypatches `live.pse.fetch_entity`/`live.openmeteo.fetch_forecast` to
    serve the same synthetic data the model was trained on. Returns the
    written `train_end` value.
    """
    pse_frames, weather, matrix = _synthetic_matrix()

    model = LgbmModel().fit(matrix[FEATURES], matrix["y"])
    model_path = tmp_path / "model.txt"
    model.save(model_path)

    train_end = pd.Timestamp(matrix.index[10]).isoformat()
    meta = {"train_end": train_end, "trained_rows": len(matrix), "features": FEATURES}
    meta_path = tmp_path / "model_meta.json"
    meta_path.write_text(json.dumps(meta))

    monkeypatch.setattr(live.paths, "MODEL_PATH", model_path)
    monkeypatch.setattr(live.paths, "MODEL_META", meta_path)

    entity_frames = {
        "csdac-pln": pse_frames["pse_csdac_pln"],
        "kse-load": pse_frames["pse_kse_load"],
        "his-wlk-cal": pse_frames["pse_his_wlk_cal"],
    }

    def fake_fetch_entity(entity: str, start: object, end: object) -> pd.DataFrame:
        return entity_frames[entity]

    def fake_fetch_forecast(
        days: int = 2, past_days: int = 0, cities: object = None
    ) -> pd.DataFrame:
        return weather

    monkeypatch.setattr(live.pse, "fetch_entity", fake_fetch_entity)
    monkeypatch.setattr(live.openmeteo, "fetch_forecast", fake_fetch_forecast)

    return train_end


def test_happy_path_predicts_24_hours_for_tomorrow(live_artifact: str) -> None:
    result = live._get_live_forecast_uncached(now_utc=NOW_UTC)

    assert result.degraded is False
    assert result.made_at_utc == NOW_UTC
    assert result.train_end == live_artifact
    assert list(result.frame.columns) == ["ts_utc", "y_pred", "y_actual"]

    tomorrow_start = NOW_UTC.normalize() + pd.Timedelta(days=1)
    tomorrow_end = tomorrow_start + pd.Timedelta(hours=23)
    tomorrow = result.frame[
        (result.frame["ts_utc"] >= tomorrow_start) & (result.frame["ts_utc"] <= tomorrow_end)
    ]
    assert len(tomorrow) == 24
    assert tomorrow["y_pred"].notna().all()

    # Trailing-30-day window: frame reaches back at least ~25 days (loose
    # bound — the exact start depends on the 7-day rolling warm-up).
    assert result.frame["ts_utc"].min() <= NOW_UTC.normalize() - pd.Timedelta(days=25)


def test_get_live_forecast_degrades_on_pse_error(
    snapshot_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(entity: str, start: object, end: object) -> pd.DataFrame:
        raise pse.PseApiError("simulated PSE outage")

    monkeypatch.setattr(live.pse, "fetch_entity", _raise)

    result = live._get_live_forecast_uncached(now_utc=NOW_UTC)

    assert result.degraded is True
    assert result.made_at_utc == NOW_UTC
    assert list(result.frame.columns) == ["ts_utc", "y_pred", "y_actual"]
    assert result.frame["y_pred"].isna().all()
    assert result.frame["y_actual"].notna().any()

    snap = data_access.load_snapshot()
    pd.testing.assert_series_equal(
        result.frame["ts_utc"].reset_index(drop=True),
        snap.recent_hourly["ts_utc"].reset_index(drop=True),
        check_names=False,
    )


def test_get_live_forecast_is_cached() -> None:
    assert hasattr(live.get_live_forecast, "clear")  # st.cache_data-wrapped marker
