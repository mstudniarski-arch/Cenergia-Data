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
