"""Read-only analysis helpers shared by the EDA notebooks and (later) the
dashboard.

Every function here opens its own short-lived, read-only connection to the
canonical warehouse at `paths.DB_PATH` and closes it before returning, so
notebook cells can call these repeatedly without juggling a connection.
`paths.DB_PATH` is read at call time (not bound as a default argument), so
tests can monkeypatch it to point at a throwaway warehouse.
"""

from __future__ import annotations

import duckdb
import pandas as pd

from cenergia import paths

WHITELISTED_TABLES: tuple[str, ...] = (
    "staging.price_hourly",
    "marts.price_daily",
    "marts.typical_shape",
    "marts.merit_order",
    "marts.qa_overlap",
    "marts.modeling_hourly",
)


def load_table(name: str) -> pd.DataFrame:
    """Load a whitelisted `schema.table` from the warehouse (read-only).

    Raises ValueError for any name outside `WHITELISTED_TABLES` — including
    SQL-injection-shaped strings — since `name` is interpolated into a query.
    """
    if name not in WHITELISTED_TABLES:
        raise ValueError(f"table not whitelisted: {name!r}")
    con = duckdb.connect(str(paths.DB_PATH), read_only=True)
    try:
        return con.execute(f"select * from {name}").df()
    finally:
        con.close()


def price_hourly() -> pd.DataFrame:
    """staging.price_hourly with a `ts_local` (Europe/Warsaw) column added."""
    df = load_table("staging.price_hourly")
    ts_local = pd.DatetimeIndex(df["ts_utc"]).tz_localize("UTC").tz_convert("Europe/Warsaw")
    df["ts_local"] = ts_local
    return df


def yearly_stats() -> pd.DataFrame:
    """Per-year mean/std/min/max price and count of negative-price hours.

    Years are taken from `ts_local` (Europe/Warsaw), matching how a Polish
    market participant would read "2022", "2023", etc.
    """
    df = price_hourly()
    year = df["ts_local"].dt.year
    grouped = df.groupby(year)["price_pln_mwh"]
    out = grouped.agg(["mean", "std", "min", "max"])
    out["negative_hours"] = grouped.apply(lambda s: int((s < 0).sum()))
    out.index.name = "year"
    return out.reset_index()
