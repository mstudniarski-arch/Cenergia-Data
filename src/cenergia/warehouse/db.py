"""DuckDB warehouse: schema bootstrap, raw loading, ordered SQL runner."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from cenergia.ingest.openmeteo import cities_frame

_SCHEMAS = ("raw", "staging", "marts")


def connect(db_path: Path | str) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(db_path))
    for schema in _SCHEMAS:
        con.execute(f"create schema if not exists {schema}")
    return con


def load_raw(
    con: duckdb.DuckDBPyConnection, raw_dir: Path, ember_csv: Path | None = None
) -> list[str]:
    created: list[str] = []
    for parquet in sorted(raw_dir.glob("*.parquet")):
        table = parquet.stem
        con.execute(
            f"create or replace table raw.{table} as "
            f"select * from read_parquet('{parquet.as_posix()}')"
        )
        created.append(table)
    cities = cities_frame()
    con.register("_cities_df", cities)
    con.execute("create or replace table raw.weather_cities as select * from _cities_df")
    con.unregister("_cities_df")
    created.append("weather_cities")
    if ember_csv is not None:
        con.execute(
            "create or replace table raw.ember_pl as "
            f"select cast(ts_utc as timestamp) as ts_utc, "
            f"cast(price_eur_mwh as double) as price_eur_mwh "
            f"from read_csv_auto('{ember_csv.as_posix()}')"
        )
        created.append("ember_pl")
    return created


def run_sql(con: duckdb.DuckDBPyConnection, sql_dir: Path) -> list[str]:
    ran: list[str] = []
    for sql_file in sorted(sql_dir.glob("*.sql")):
        con.execute(sql_file.read_text())
        ran.append(sql_file.name)
    return ran


def load_frames(con: duckdb.DuckDBPyConnection, frames: dict[str, pd.DataFrame]) -> None:
    for name, frame in frames.items():
        con.register(f"_df_{name}", frame)
        con.execute(f"create or replace table raw.{name} as select * from _df_{name}")
        con.unregister(f"_df_{name}")
