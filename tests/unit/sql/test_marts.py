import duckdb


def test_modeling_hourly_is_pse_era_join(con: duckdb.DuckDBPyConnection) -> None:
    rows = con.execute(
        "select ts_utc, price_pln_mwh, load_fcst_mw, temp_c, wind_mw, pv_mw "
        "from marts.modeling_hourly order by ts_utc"
    ).fetchall()
    assert len(rows) == 2  # only the two PSE hours, never ember rows
    first = rows[0]
    assert first[1] == 400.0 and first[2] == 20000.0
    assert abs(first[3] - 13.75) < 1e-9  # weather joined
    assert first[4] == 3000.0 and first[5] == 1500.0


def test_typical_shape_uses_warsaw_local_hour(con: duckdb.DuckDBPyConnection) -> None:
    # PSE hours 2024-06-13 22:00/23:00 UTC = CEST +2 -> local 00:00/01:00 (2024-06-14, summer).
    # typical_shape blends all price_hourly sources (no PSE-only filter, unlike modeling_hourly/
    # merit_order), so the pre-era ember row 2024-06-08 00:00 UTC (-> local 02:00, still June/
    # summer) contributes a third hour_local.
    hours = {
        r[0]
        for r in con.execute(
            "select hour_local from marts.typical_shape where season = 'summer'"
        ).fetchall()
    }
    assert hours == {0, 1, 2}


def test_merit_order_res_share(con: duckdb.DuckDBPyConnection) -> None:
    row = con.execute("select res_mw, load_mw, res_share from marts.merit_order").fetchone()
    assert row[0] == 4500.0 and row[1] == 21000.0  # type: ignore[index]
    assert abs(row[2] - 4500.0 / 21000.0) < 1e-9  # type: ignore[index]


def test_qa_overlap_diff(con: duckdb.DuckDBPyConnection) -> None:
    # ember fixture has one row inside the PSE era: 2024-06-13 23:00 @ 60 EUR.
    # cast(ts_utc as date) = 2024-06-13, which fx_daily forward-fills from the Monday
    # 2024-06-10 rate (4.40), not the earlier Friday 2024-06-07 rate (4.30).
    row = con.execute("select ember_pln, pse_pln, abs_diff from marts.qa_overlap").fetchone()
    assert row[0] == 60.0 * 4.40  # type: ignore[index]
    assert row[1] == 250.0  # type: ignore[index]
    assert abs(row[2] - abs(60.0 * 4.40 - 250.0)) < 1e-9  # type: ignore[index]


def test_price_daily_grouped_by_source(con: duckdb.DuckDBPyConnection) -> None:
    rows = con.execute("select source, avg_price from marts.price_daily order by source").fetchall()
    assert [r[0] for r in rows] == ["ember", "pse"]
