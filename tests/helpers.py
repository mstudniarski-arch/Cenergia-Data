"""Shared test fixture builders — plain module, no pytest magic.

Single source for the Task-6 minimal-but-complete raw fixture set: used by
tests/unit/sql/conftest.py's in-memory `con` fixture and by
tests/integration/test_end_to_end.py's `seed_raw_dir` (parquet + ember CSV on
disk), so both stay in sync.
"""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

# Re-exported (the redundant `as` aliases satisfy mypy strict's
# no_implicit_reexport) so tests exercise the exact empty-stub frames the
# live path supplies, rather than byte-for-byte copies that could drift.
from cenergia.dashboard.live import empty_ember_frame as empty_ember_frame
from cenergia.dashboard.live import empty_gen_frame as empty_gen_frame
from cenergia.dashboard.live import empty_nbp_frame as empty_nbp_frame
from cenergia.ingest.openmeteo import CITIES


def _pse_quarters(
    dtime_utc_start: str, hours: int, values: list[float], value_col: str
) -> pd.DataFrame:
    """Build 15-min rows: interval-END dtime_utc strings starting at start+15min."""
    start = pd.Timestamp(dtime_utc_start)
    rows = []
    for i in range(hours * 4):
        end_ts = start + pd.Timedelta(minutes=15 * (i + 1))
        rows.append(
            {
                "dtime": "IGNORED 02a:15:00",  # proves SQL never parses dtime
                "dtime_utc": end_ts.strftime("%Y-%m-%d %H:%M:%S"),
                "business_date": "2024-06-14",
                value_col: values[i],
            }
        )
    return pd.DataFrame(rows)


def raw_frames() -> dict[str, pd.DataFrame]:
    """The Task-6 raw fixture set, keyed by raw table name / parquet stem."""
    # csdac: hour A replicated-hourly (4x 400.0), hour B true 15-min (4 distinct)
    csdac = _pse_quarters(
        "2024-06-13 22:00:00", 2, [400.0] * 4 + [100.0, 200.0, 300.0, 400.0], "csdac_pln"
    )
    # kse-load: one past hour (actuals) + one future hour (fcst only)
    load = _pse_quarters("2024-06-13 22:00:00", 2, [20000.0] * 8, "load_fcst")
    load["load_actual"] = [21000.0] * 4 + [None] * 4
    # his-gen-pal: one hour, solar + two codes mapping to 'other'
    gen = pd.concat(
        [
            _pse_quarters("2024-06-13 22:00:00", 1, [1000.0] * 4, "value").assign(
                alias_entsoe="B16"
            ),
            _pse_quarters("2024-06-13 22:00:00", 1, [10.0] * 4, "value").assign(alias_entsoe="B15"),
            _pse_quarters("2024-06-13 22:00:00", 1, [20.0] * 4, "value").assign(alias_entsoe="B20"),
        ],
        ignore_index=True,
    )
    # his-wlk-cal: one hour of wind/pv
    wlk = _pse_quarters("2024-06-13 22:00:00", 1, [3000.0] * 4, "wi")
    wlk["pv"] = 1500.0
    # weather: two cities, one hour; third city intentionally absent (renormalization test)
    weather = pd.DataFrame(
        {
            "city": ["warszawa", "krakow"],
            "ts_utc": [pd.Timestamp("2024-06-13 22:00:00")] * 2,
            "temp_c": [10.0, 20.0],
            "wind_ms": [5.0, 7.0],
            "ghi_wm2": [100.0, 300.0],
            "cloud_pct": [50.0, 100.0],
        }
    )
    # fx: Friday + Monday rates (weekend gap)
    fx = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-06-07", "2024-06-10"]),
            "eur_pln": [4.30, 4.40],
        }
    )
    return {
        "pse_csdac_pln": csdac,
        "pse_kse_load": load,
        "pse_his_gen_pal": gen,
        "pse_his_wlk_cal": wlk,
        "weather_history": weather,
        "nbp_fx": fx,
    }


def ember_frame() -> pd.DataFrame:
    """Two hours long before PSE era + one INSIDE PSE era (must be excluded downstream)."""
    return pd.DataFrame(
        {
            "ts_utc": pd.to_datetime(
                ["2015-01-01 00:00:00", "2024-06-08 00:00:00", "2024-06-13 23:00:00"]
            ),
            "price_eur_mwh": [25.0, 50.0, 60.0],
        }
    )


def seed_raw_dir(raw_dir: Path, ember_csv: Path) -> None:
    """Write the Task-6 fixture frames as parquet (raw_dir) + a tiny ember CSV.

    Mirrors the on-disk shape `pipeline.cmd_transform` expects: one parquet
    per raw table under `raw_dir`, plus a standalone ember CSV (ts_utc,
    price_eur_mwh columns, matching `ember.slice_ember`'s output format).
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in raw_frames().items():
        frame.to_parquet(raw_dir / f"{name}.parquet", index=False)
    ember_frame().to_csv(ember_csv, index=False)


def hourly_pse_frames(start: str, hours: int) -> dict[str, pd.DataFrame]:
    """`hours` consecutive hourly rows (each replicated x4 as identical
    quarters, i.e. the pre-2025-10-01 "replicated-hourly" regime — see
    `raw_frames`) of PSE price/load/RES data starting at UTC `start`.

    Values are deterministic but vary with a slow sinusoid so downstream lag
    and rolling-window features aren't degenerate (zero variance). Used by
    Task 18's live-forecast tests, which need many days of data (weeks, not
    the 1-2 hours `raw_frames` provides) without per-quarter realism.
    """

    def _rep(values: list[float]) -> list[float]:
        return [v for v in values for _ in range(4)]

    price = [220.0 + 60.0 * math.sin(h / 24 * 2 * math.pi) + 3.0 * (h % 24) for h in range(hours)]
    load = [17000.0 + 2500.0 * math.sin(h / 24 * 2 * math.pi) for h in range(hours)]
    wind = [1800.0 + 700.0 * math.sin(h / 60) for h in range(hours)]
    pv = [max(0.0, 900.0 * math.sin(((h % 24) - 6) / 12 * math.pi)) for h in range(hours)]

    csdac = _pse_quarters(start, hours, _rep(price), "csdac_pln")
    kse_load = _pse_quarters(start, hours, _rep(load), "load_fcst")
    kse_load["load_actual"] = _rep(load)
    wlk = _pse_quarters(start, hours, _rep(wind), "wi")
    wlk["pv"] = _rep(pv)

    return {"pse_csdac_pln": csdac, "pse_kse_load": kse_load, "pse_his_wlk_cal": wlk}


def hourly_weather_frame(start: str, hours: int) -> pd.DataFrame:
    """`hours` hourly rows across all `openmeteo.CITIES` starting at UTC
    `start` — matches `openmeteo.fetch_forecast`/`fetch_history` output shape.
    """
    ts = pd.date_range(start, periods=hours, freq="h")
    temp = [10.0 + 8.0 * math.sin(i / 24 * 2 * math.pi) for i in range(hours)]
    wind = [4.0 + 2.0 * math.sin(i / 30) for i in range(hours)]
    ghi = [max(0.0, 400.0 * math.sin(((i % 24) - 6) / 12 * math.pi)) for i in range(hours)]
    cloud = [50.0 + 30.0 * math.sin(i / 15) for i in range(hours)]
    frames = [
        pd.DataFrame(
            {
                "city": city.name,
                "ts_utc": ts,
                "temp_c": temp,
                "wind_ms": wind,
                "ghi_wm2": ghi,
                "cloud_pct": cloud,
            }
        )
        for city in CITIES
    ]
    return pd.concat(frames, ignore_index=True)
