"""TDD for src/cenergia/analysis.py: whitelisted table loads, the localized
hourly price series, and per-year summary stats.

Each test builds a tiny warehouse on disk under `tmp_path` and monkeypatches
`paths.DB_PATH` at it, so the suite never opens the real warehouse.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from cenergia import analysis, paths
from cenergia.warehouse import db


def _seed_warehouse(db_path: Path) -> None:
    con = db.connect(db_path)
    price_hourly = pd.DataFrame(
        {
            "ts_utc": pd.to_datetime(
                [
                    "2023-06-14 10:00:00",  # positive, summer 2023 (12:00 CEST local)
                    "2023-06-14 12:00:00",  # negative, summer 2023 midday
                    "2024-01-15 18:00:00",  # positive, winter 2024
                ]
            ),
            "price_pln_mwh": [300.0, -10.0, 500.0],
            "source": ["pse", "pse", "pse"],
            "is_15min_regime": [False, False, False],
        }
    )
    db.load_frames(con, {"_price_hourly": price_hourly})
    con.execute("create or replace table staging.price_hourly as select * from raw._price_hourly")
    con.execute(
        "create or replace table marts.price_daily as "
        "select cast(ts_utc as date) as date, source, avg(price_pln_mwh) as avg_price "
        "from staging.price_hourly group by 1, 2"
    )
    con.close()


@pytest.fixture()
def warehouse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "warehouse.duckdb"
    _seed_warehouse(db_path)
    monkeypatch.setattr(paths, "DB_PATH", db_path)
    return db_path


def test_load_table_whitelisted(warehouse: Path) -> None:
    df = analysis.load_table("staging.price_hourly")
    assert len(df) == 3
    assert set(df.columns) >= {"ts_utc", "price_pln_mwh", "source"}


def test_load_table_rejects_non_whitelisted_name(warehouse: Path) -> None:
    with pytest.raises(ValueError, match="not whitelisted"):
        analysis.load_table("raw._price_hourly")


def test_load_table_rejects_injection(warehouse: Path) -> None:
    with pytest.raises(ValueError, match="not whitelisted"):
        analysis.load_table("staging.price_hourly; drop table staging.price_hourly; --")


def test_price_hourly_adds_ts_local_in_warsaw_tz(warehouse: Path) -> None:
    df = analysis.price_hourly()
    assert "ts_local" in df.columns
    assert str(df["ts_local"].dt.tz) == "Europe/Warsaw"
    # 2023-06-14 10:00 UTC -> 12:00 local (CEST, summer UTC+2)
    row = df.loc[df["ts_utc"] == pd.Timestamp("2023-06-14 10:00:00")].iloc[0]
    assert row["ts_local"].hour == 12
    # 2024-01-15 18:00 UTC -> 19:00 local (CET, winter UTC+1)
    row = df.loc[df["ts_utc"] == pd.Timestamp("2024-01-15 18:00:00")].iloc[0]
    assert row["ts_local"].hour == 19


def test_yearly_stats_aggregates_and_counts_negative_hours(warehouse: Path) -> None:
    out = analysis.yearly_stats().set_index("year")
    assert set(out.index) == {2023, 2024}
    assert out.loc[2023, "min"] == -10.0
    assert out.loc[2023, "max"] == 300.0
    assert out.loc[2023, "negative_hours"] == 1
    assert out.loc[2024, "mean"] == 500.0
    assert out.loc[2024, "negative_hours"] == 0


_TS1 = pd.Timestamp("2024-06-14 10:00:00")
_TS2 = pd.Timestamp("2024-06-14 11:00:00")
_TS_EXTRA = pd.Timestamp("2024-06-14 12:00:00")  # present upstream, absent from modeling_hourly

_DRIVERS_GEN_COLS = (
    "gen_lignite",
    "gen_hard_coal",
    "gen_gas",
    "gen_solar",
    "gen_wind_onshore",
    "gen_biomass",
    "gen_pumped_storage",
    "gen_hydro_ror",
    "gen_hydro_res",
    "gen_other",
)


_FUELS_TS1: dict[str, float] = {
    "lignite": 5000.0,
    "hard_coal": 3000.0,
    "gas": 1000.0,
    "solar": 2000.0,
    "wind_onshore": 1000.0,
    "biomass": 200.0,
    "pumped_storage": 50.0,
    "hydro_ror": 100.0,
    "hydro_res": 80.0,
    "other": 70.0,
}
_FUELS_TS2: dict[str, float] = {
    "lignite": 4800.0,
    "hard_coal": 2900.0,
    "gas": 1100.0,
    "solar": 2200.0,
    "wind_onshore": 900.0,
    "biomass": 210.0,
    "pumped_storage": 40.0,
    "hydro_ror": 110.0,
    "hydro_res": 90.0,
    "other": 60.0,
}


def _seed_drivers_warehouse(db_path: Path) -> None:
    con = db.connect(db_path)

    modeling_hourly = pd.DataFrame(
        {
            "ts_utc": [_TS1, _TS2],
            "price_pln_mwh": [400.0, 450.0],
            "load_fcst_mw": [15000.0, 15500.0],
            "temp_c": [20.0, 21.0],
            "wind_ms": [5.0, 4.0],
            "ghi_wm2": [300.0, 350.0],
            "cloud_pct": [10.0, 5.0],
            "wind_mw": [1000.0, 900.0],
            "pv_mw": [2000.0, 2200.0],
            "is_15min_regime": [False, False],
        }
    )
    load_hourly = pd.DataFrame(
        {
            "ts_utc": [_TS1, _TS2, _TS_EXTRA],
            "load_mw": [14800.0, 15200.0, 15600.0],
            "load_fcst_mw": [15000.0, 15500.0, 15900.0],
        }
    )
    gen_mix_hourly = pd.DataFrame(
        [
            {"ts_utc": ts, "fuel": fuel, "gen_mw": gen_mw}
            for ts, fuels in ((_TS1, _FUELS_TS1), (_TS2, _FUELS_TS2))
            for fuel, gen_mw in fuels.items()
        ]
        + [{"ts_utc": _TS_EXTRA, "fuel": "lignite", "gen_mw": 9999.0}]
    )

    db.load_frames(
        con,
        {
            "_modeling_hourly": modeling_hourly,
            "_load_hourly": load_hourly,
            "_gen_mix_hourly": gen_mix_hourly,
        },
    )
    con.execute(
        "create or replace table marts.modeling_hourly as select * from raw._modeling_hourly"
    )
    con.execute("create or replace table staging.load_hourly as select * from raw._load_hourly")
    con.execute(
        "create or replace table staging.gen_mix_hourly as select * from raw._gen_mix_hourly"
    )
    con.close()


@pytest.fixture()
def drivers_warehouse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "warehouse.duckdb"
    _seed_drivers_warehouse(db_path)
    monkeypatch.setattr(paths, "DB_PATH", db_path)
    return db_path


def test_drivers_frame_has_one_row_per_pse_era_hour(drivers_warehouse: Path) -> None:
    df = analysis.drivers_frame()
    # modeling_hourly has 2 rows; load_hourly/gen_mix_hourly have an extra hour
    # that must NOT leak in via the join.
    assert len(df) == 2
    assert set(df["ts_utc"]) == {_TS1, _TS2}


def test_drivers_frame_has_pivoted_gen_columns_and_load_mw(drivers_warehouse: Path) -> None:
    df = analysis.drivers_frame()
    assert set(_DRIVERS_GEN_COLS) <= set(df.columns)
    assert "load_mw" in df.columns
    # modeling_hourly's own columns must survive the join untouched.
    assert {"price_pln_mwh", "load_fcst_mw", "temp_c", "wind_mw", "pv_mw"} <= set(df.columns)


def test_drivers_frame_pivoted_values_match_fixture(drivers_warehouse: Path) -> None:
    df = analysis.drivers_frame().set_index("ts_utc")
    # Every one of the ten pivoted gen_<fuel> columns must carry the exact
    # fixture value for both hours — catches any fuel/column mislabeling in
    # the pivot, not just at the sampled corners.
    for ts, fuels in ((_TS1, _FUELS_TS1), (_TS2, _FUELS_TS2)):
        row = df.loc[ts]
        for fuel, expected in fuels.items():
            assert row[f"gen_{fuel}"] == expected, f"gen_{fuel} at {ts}"

    row1 = df.loc[_TS1]
    assert row1["load_mw"] == 14800.0
    assert row1["price_pln_mwh"] == 400.0

    row2 = df.loc[_TS2]
    assert row2["load_mw"] == 15200.0
