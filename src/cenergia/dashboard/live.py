"""Runtime-live forecast: the dashboard's "wow feature" — a real next-day
price forecast computed at request time, not baked into the snapshot.

Engineering core is maximum reuse: the live path pulls fresh data with the
SAME ingest clients (`pse.fetch_entity`, `openmeteo.fetch_forecast`), runs it
through the SAME staging/marts SQL on an in-memory DuckDB warehouse
(`db.connect(":memory:")` + `load_frames` + `run_sql`), builds features with
the SAME leakage-safe `build_matrix`, and predicts with the committed model
artifact — all the same code the batch pipeline uses, just pointed at fresh
data instead of `data/raw/*.parquet`.

`ember_pl`/`nbp_fx` aren't needed live (the PSE era needs no Ember/FX
backfill) — empty stand-ins with the right columns/dtypes are supplied
because `03_staging_price_long.sql`/`01_staging_fx.sql` read them
unconditionally; both tolerate an empty input (the union then just yields
PSE rows). Likewise `pse_his_gen_pal` (generation mix) isn't a column
`marts.modeling_hourly` needs, so an empty stub avoids a 45-day, 13-fuel
fetch for data the model never sees.

Any failure in the pull/build/predict path (network outage, PSE/Open-Meteo
API errors, an unreadable warehouse, ...) degrades gracefully: the frame
falls back to the pre-baked snapshot's trailing 60 days
(`Snapshot.recent_hourly`), with `y_pred` all-NaN (there is no live forecast
to show) and `degraded=True` so the view can warn instead of crashing.

`get_live_forecast` is the `st.cache_data`-wrapped public entry point (1h
TTL — no reason to re-pull PSE/weather data on every Streamlit rerun); tests
call the underlying `_get_live_forecast_uncached` directly, since cache
decorators make direct testing awkward (same documented pattern as
`data_access._read_snapshot`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd
import streamlit as st

# Re-exported (not just imported) so `live.paths.*`/`live.pse.*`/
# `live.openmeteo.*` are valid public paths for tests to monkeypatch (e.g.
# `monkeypatch.setattr(live.pse, "fetch_entity", ...)`); mypy strict's
# no_implicit_reexport otherwise treats a bare import as private (same
# pattern as `pipeline.py`'s `paths as paths`).
from cenergia import paths as paths
from cenergia.dashboard.data_access import load_snapshot
from cenergia.features.matrix import FEATURES, build_matrix
from cenergia.ingest import openmeteo as openmeteo
from cenergia.ingest import pse as pse
from cenergia.models.lgbm import LgbmModel
from cenergia.warehouse import db

_PULL_DAYS = 45
_TRAILING_DAYS = 30


@dataclass(frozen=True)
class LiveForecast:
    made_at_utc: pd.Timestamp
    frame: pd.DataFrame
    degraded: bool
    train_end: str


@st.cache_data(ttl=3600)
def get_live_forecast(now_utc: pd.Timestamp | None = None) -> LiveForecast:
    return _get_live_forecast_uncached(now_utc)


def _get_live_forecast_uncached(now_utc: pd.Timestamp | None = None) -> LiveForecast:
    made_at = now_utc if now_utc is not None else pd.Timestamp.now(tz="UTC").tz_localize(None)
    train_end = _read_train_end()
    try:
        frame = _pull_and_predict(made_at)
        degraded = False
    except Exception:
        frame = _degraded_frame()
        degraded = True
    return LiveForecast(made_at_utc=made_at, frame=frame, degraded=degraded, train_end=train_end)


def _read_train_end() -> str:
    try:
        meta = json.loads(paths.MODEL_META.read_text())
        return str(meta["train_end"])
    except Exception:
        return "unknown"


def _pull_and_predict(now_utc: pd.Timestamp) -> pd.DataFrame:
    start = (now_utc - pd.Timedelta(days=_PULL_DAYS)).date()
    end = (now_utc + pd.Timedelta(days=1)).date()

    raw = {
        "pse_csdac_pln": pse.fetch_entity("csdac-pln", start, end),
        "pse_kse_load": pse.fetch_entity("kse-load", start, end),
        "pse_his_wlk_cal": pse.fetch_entity("his-wlk-cal", start, end),
        "pse_his_gen_pal": _empty_gen_frame(),
        "weather_history": openmeteo.fetch_forecast(days=2, past_days=_PULL_DAYS),
        "weather_cities": openmeteo.cities_frame(),
        "nbp_fx": _empty_nbp_frame(),
        "ember_pl": _empty_ember_frame(),
    }

    con = db.connect(":memory:")
    db.load_frames(con, raw)
    db.run_sql(con, paths.SQL_DIR)
    matrix = build_matrix(con)

    model = LgbmModel.load(paths.MODEL_PATH)
    y_pred = model.predict(matrix[FEATURES])

    frame = pd.DataFrame(
        {
            "ts_utc": matrix.index.to_numpy(),
            "y_pred": y_pred,
            "y_actual": matrix["y"].to_numpy(),
        }
    )
    window_start = now_utc.normalize() - pd.Timedelta(days=_TRAILING_DAYS)
    frame = frame[frame["ts_utc"] >= window_start].reset_index(drop=True)
    return frame


def _degraded_frame() -> pd.DataFrame:
    recent = load_snapshot().recent_hourly
    return pd.DataFrame(
        {
            "ts_utc": recent["ts_utc"].to_numpy(),
            "y_pred": np.nan,
            "y_actual": recent["price_pln_mwh"].to_numpy(),
        }
    )


def _empty_gen_frame() -> pd.DataFrame:
    # dtype="string" (not "object"): an empty object-dtype column registers
    # with DuckDB as INTEGER, breaking try_strptime(dtime_utc, ...).
    return pd.DataFrame(
        {
            "dtime_utc": pd.Series(dtype="string"),
            "alias_entsoe": pd.Series(dtype="string"),
            "value": pd.Series(dtype="float64"),
        }
    )


def _empty_nbp_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {"date": pd.Series(dtype="datetime64[ns]"), "eur_pln": pd.Series(dtype="float64")}
    )


def _empty_ember_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {"ts_utc": pd.Series(dtype="datetime64[ns]"), "price_eur_mwh": pd.Series(dtype="float64")}
    )
