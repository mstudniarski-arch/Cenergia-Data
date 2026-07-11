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


_GEN_FUELS: tuple[str, ...] = (
    "lignite",
    "hard_coal",
    "gas",
    "solar",
    "wind_onshore",
    "biomass",
    "pumped_storage",
    "hydro_ror",
    "hydro_res",
    "other",
)


def drivers_frame() -> pd.DataFrame:
    """`marts.modeling_hourly` (one row per PSE-era hour) plus actual load and
    the fuel-mix breakdown, for the price-drivers notebook.

    Adds `load_mw` (`staging.load_hourly`) and one `gen_<fuel>` column per
    fuel in `staging.gen_mix_hourly` (pivoted from its long `fuel`/`gen_mw`
    form). Neither source table is in `WHITELISTED_TABLES` — they're staging
    detail, not meant for ad-hoc dashboard loads — so, like `load_table`,
    this opens its own short-lived read-only connection rather than widening
    the whitelist.
    """
    fuel_cols_cte = ",\n            ".join(
        f"max(case when fuel = '{fuel}' then gen_mw end) as gen_{fuel}" for fuel in _GEN_FUELS
    )
    fuel_cols_select = ", ".join(f"gw.gen_{fuel}" for fuel in _GEN_FUELS)
    query = f"""
        with gen_wide as (
            select ts_utc,
            {fuel_cols_cte}
            from staging.gen_mix_hourly
            group by ts_utc
        )
        select m.*, l.load_mw, {fuel_cols_select}
        from marts.modeling_hourly m
        left join staging.load_hourly l using (ts_utc)
        left join gen_wide gw using (ts_utc)
        order by m.ts_utc
    """
    con = duckdb.connect(str(paths.DB_PATH), read_only=True)
    try:
        return con.execute(query).df()
    finally:
        con.close()


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
