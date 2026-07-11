"""cmd_validate against a synthetic warehouse — no network, no live warehouse.

cmd_validate is a plain function over a db path, so we build a tiny DuckDB file
that satisfies every Task-13 threshold, assert it passes, then corrupt one
invariant and assert it raises SystemExit(1). The synthetic tables mirror only
the columns cmd_validate reads (not the full staging/marts schema).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from cenergia import pipeline
from cenergia.warehouse import db

# UTC-hour spines: prices from 2015 (Ember era) so price_hourly clears 95k rows;
# PSE-era tables from 2024-06-15 to today so coverage/gap/row-count thresholds hold.
_END_TS = f"{date.today().isoformat()} 23:00:00"
_PRICE = "50 + 20 * sin(epoch(ts_utc) / 3600.0)"


def _build_valid(db_path: Path) -> None:
    con = db.connect(db_path)
    con.execute(
        "create table staging.price_hourly as "
        f"select ts_utc, {_PRICE} as price_pln_mwh, "
        "case when ts_utc < timestamp '2024-06-13 22:00:00' then 'ember' else 'pse' end as source, "
        "ts_utc >= timestamp '2025-09-30 22:00:00' as is_15min_regime "
        "from (select unnest(generate_series(timestamp '2015-01-01 00:00:00', "
        f"timestamp '{_END_TS}', interval 1 hour)) as ts_utc)"
    )
    con.execute(
        "create table staging.price_pse_hourly as "
        f"select ts_utc, {_PRICE} as price_pln_mwh, 4 as n_quarters "
        "from (select unnest(generate_series(timestamp '2024-06-15 00:00:00', "
        f"timestamp '{_END_TS}', interval 1 hour)) as ts_utc)"
    )
    con.execute(
        "create table marts.modeling_hourly as "
        "select ts_utc, price_pln_mwh, 30000.0 as load_fcst_mw, "
        "10.0 as temp_c, 5.0 as wind_ms, 200.0 as ghi_wm2, 50.0 as cloud_pct "
        "from staging.price_pse_hourly"
    )
    con.execute(
        "create table marts.qa_overlap as "
        "select ts_utc, price_pln_mwh + 3.0 as ember_pln, price_pln_mwh as pse_pln, "
        "3.0 as abs_diff from staging.price_pse_hourly"
    )
    # ts_utc-grain tables that only need to exist + be unique for the dup checks.
    for stmt in (
        "create table staging.load_hourly as select ts_utc, 30000.0 as load_fcst_mw "
        "from staging.price_pse_hourly",
        "create table staging.res_hourly as select ts_utc from staging.price_pse_hourly",
        "create table staging.weather_hourly as select ts_utc from staging.price_pse_hourly",
        "create table marts.merit_order as select ts_utc from staging.price_pse_hourly",
    ):
        con.execute(stmt)
    con.close()


def test_validate_passes_on_valid_warehouse(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "wh.duckdb"
    _build_valid(db_path)
    assert pipeline.cmd_validate(db_path) == 0
    out = capsys.readouterr().out
    assert "[FAIL]" not in out
    # 5 threshold checks (price_hourly, pse coverage, pse n_quarters, modeling,
    # qa_overlap) + 8 ts_utc-uniqueness checks = 13.
    assert out.count("[PASS]") == 13


def test_validate_raises_on_duplicate_ts(tmp_path: Path) -> None:
    db_path = tmp_path / "wh.duckdb"
    _build_valid(db_path)
    con = db.connect(db_path)
    con.execute("insert into staging.res_hourly select ts_utc from staging.res_hourly limit 1")
    con.close()
    with pytest.raises(SystemExit):
        pipeline.cmd_validate(db_path)
