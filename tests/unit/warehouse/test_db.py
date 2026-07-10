from pathlib import Path

import pandas as pd

from cenergia.warehouse import db


def test_connect_creates_schemas(tmp_path: Path) -> None:
    con = db.connect(tmp_path / "w.duckdb")
    schemas = {
        r[0] for r in con.execute("select schema_name from information_schema.schemata").fetchall()
    }
    assert {"raw", "staging", "marts"} <= schemas


def test_load_raw_parquet_and_seeds(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    pd.DataFrame({"a": [1, 2]}).to_parquet(raw_dir / "pse_csdac_pln.parquet")
    ember_csv = tmp_path / "ember.csv"
    pd.DataFrame({"ts_utc": ["2015-01-01 00:00:00"], "price_eur_mwh": [25.4]}).to_csv(
        ember_csv, index=False
    )

    con = db.connect(":memory:")
    tables = db.load_raw(con, raw_dir, ember_csv=ember_csv)
    assert set(tables) == {"pse_csdac_pln", "weather_cities", "ember_pl"}
    assert con.execute("select count(*) from raw.pse_csdac_pln").fetchone()[0] == 2  # type: ignore[index]
    assert con.execute("select sum(weight) from raw.weather_cities").fetchone()[0] == 1.0  # type: ignore[index]


def test_run_sql_sorted_and_idempotent(tmp_path: Path) -> None:
    sql_dir = tmp_path / "sql"
    sql_dir.mkdir()
    (sql_dir / "02_second.sql").write_text(
        "create or replace table staging.two as select n + 1 as m from staging.one;"
    )
    (sql_dir / "01_first.sql").write_text("create or replace table staging.one as select 1 as n;")
    con = db.connect(":memory:")
    ran = db.run_sql(con, sql_dir)
    ran2 = db.run_sql(con, sql_dir)  # idempotent re-run
    assert ran == ["01_first.sql", "02_second.sql"] == ran2
    assert con.execute("select m from staging.two").fetchone()[0] == 2  # type: ignore[index]


def test_load_frames_registers_raw_tables() -> None:
    con = db.connect(":memory:")
    db.load_frames(con, {"pse_csdac_pln": pd.DataFrame({"x": [1]})})
    assert con.execute("select x from raw.pse_csdac_pln").fetchone()[0] == 1  # type: ignore[index]
