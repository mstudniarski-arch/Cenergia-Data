from pathlib import Path

import duckdb

from cenergia.ingest.openmeteo import cities_frame
from cenergia.warehouse import db
from tests.helpers import empty_ember_frame, empty_nbp_frame, raw_frames

SQL_DIR = Path(__file__).parents[3] / "sql"


def test_price_long_tolerates_empty_ember_and_nbp() -> None:
    """Task 18's live path supplies empty ember_pl/nbp_fx stubs (no Ember/FX
    backfill needed for the PSE-only live pull). `03_staging_price_long.sql`
    reads raw.ember_pl directly and raw.nbp_fx (via staging.fx_daily) — with
    both empty, the union must still succeed and yield only PSE rows.
    """
    c = db.connect(":memory:")
    frames = {**raw_frames(), "nbp_fx": empty_nbp_frame(), "ember_pl": empty_ember_frame()}
    db.load_frames(c, frames)
    db.load_frames(c, {"weather_cities": cities_frame()})
    db.run_sql(c, SQL_DIR)

    rows = c.execute("select source, count(*) from staging.price_hourly group by 1").fetchall()
    assert dict(rows) == {"pse": 2}


def test_price_pse_hourly_interval_start_and_aggregation(con: duckdb.DuckDBPyConnection) -> None:
    rows = con.execute(
        "select ts_utc, price_pln_mwh, n_quarters from staging.price_pse_hourly order by ts_utc"
    ).fetchall()
    assert len(rows) == 2
    # quarters with dtime_utc 22:15..23:00 (interval-END) belong to hour 22:00 (interval-START)
    assert str(rows[0][0]) == "2024-06-13 22:00:00"
    assert rows[0][1] == 400.0 and rows[0][2] == 4  # replicated-hourly regime
    assert rows[1][1] == 250.0  # mean of 100..400
    assert str(rows[1][0]) == "2024-06-13 23:00:00"


def test_fx_daily_forward_fills_weekend(con: duckdb.DuckDBPyConnection) -> None:
    rate = con.execute(
        "select eur_pln from staging.fx_daily where date = date '2024-06-08'"
    ).fetchone()[0]  # type: ignore[index]
    assert rate == 4.30  # Saturday inherits Friday


def test_price_long_stitches_sources(con: duckdb.DuckDBPyConnection) -> None:
    rows = con.execute(
        "select source, count(*) from staging.price_hourly group by 1 order by 1"
    ).fetchall()
    # 2015 row dropped (no FX match), in-era ember row excluded
    assert dict(rows) == {"ember": 1, "pse": 2}
    pln = con.execute(
        "select price_pln_mwh from staging.price_hourly where source = 'ember'"
    ).fetchone()[0]  # type: ignore[index]
    assert pln == 50.0 * 4.30
    flags = con.execute("select distinct is_15min_regime from staging.price_hourly").fetchall()
    assert flags == [(False,)]  # all fixture rows predate 2025-09-30 22:00 UTC


def test_load_hourly_future_nulls(con: duckdb.DuckDBPyConnection) -> None:
    rows = con.execute(
        "select load_mw, load_fcst_mw from staging.load_hourly order by ts_utc"
    ).fetchall()
    assert rows[0] == (21000.0, 20000.0)
    assert rows[1][0] is None and rows[1][1] == 20000.0


def test_gen_mix_fuel_mapping_and_other_summed(con: duckdb.DuckDBPyConnection) -> None:
    rows = dict(con.execute("select fuel, gen_mw from staging.gen_mix_hourly").fetchall())
    assert rows["solar"] == 1000.0
    assert rows["other"] == 30.0  # B15 (10) + B20 (20) summed per quarter, then averaged


def test_res_hourly(con: duckdb.DuckDBPyConnection) -> None:
    wind, pv = con.execute("select wind_mw, pv_mw from staging.res_hourly").fetchone()  # type: ignore[misc]
    assert (wind, pv) == (3000.0, 1500.0)


def test_weather_weight_renormalization(con: duckdb.DuckDBPyConnection) -> None:
    temp = con.execute("select temp_c from staging.weather_hourly").fetchone()[0]  # type: ignore[index]
    # warszawa 0.25, krakow 0.15 present -> (10*0.25 + 20*0.15) / 0.40 = 13.75
    assert abs(temp - 13.75) < 1e-9
