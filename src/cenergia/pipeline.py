"""Pipeline CLI: `python -m cenergia.pipeline <cmd>`.

Every cmd_* is a plain function with explicit path/param arguments (defaulting
to the canonical `paths.*` locations) so tests call functions directly rather
than shelling out. `main()` only parses argv and dispatches.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

# Re-exported (not just imported) so `pipeline.paths.*` is a valid public path
# for callers/tests (e.g. test_end_to_end.py's `sql_dir=pipeline.paths.SQL_DIR`);
# mypy strict's no_implicit_reexport otherwise treats a bare import as private.
from cenergia import paths as paths
from cenergia.features.matrix import FEATURES, build_matrix
from cenergia.ingest import ember, nbp, openmeteo, pse
from cenergia.models.backtest import walk_forward
from cenergia.models.lgbm import LgbmModel
from cenergia.warehouse import db

_SNAPSHOT_MARTS: tuple[str, ...] = ("price_daily", "typical_shape", "merit_order", "qa_overlap")

# Tables whose grain is one row per ts_utc (so ts_utc must be unique). Excludes
# staging.gen_mix_hourly (deliberately (ts_utc, fuel) long-grain) and the
# date-/season-grained tables (fx_daily, price_daily, typical_shape).
_TS_GRAIN_TABLES: tuple[str, ...] = (
    "staging.price_pse_hourly",
    "staging.price_hourly",
    "staging.load_hourly",
    "staging.res_hourly",
    "staging.weather_hourly",
    "marts.modeling_hourly",
    "marts.merit_order",
    "marts.qa_overlap",
)


def cmd_ember_slice(raw: Path, ember_csv: Path = paths.EMBER_CSV) -> None:
    ember_csv.parent.mkdir(parents=True, exist_ok=True)
    ember.slice_ember(raw, ember_csv)


def cmd_ingest(
    start: date,
    end: date | None = None,
    raw_dir: Path = paths.RAW,
) -> None:
    end_date = end or date.today()
    raw_dir.mkdir(parents=True, exist_ok=True)
    pse.fetch_all(start, end_date, raw_dir)
    nbp.fetch_eur_pln(date(2015, 1, 1), end_date).to_parquet(
        raw_dir / "nbp_fx.parquet", index=False
    )
    openmeteo.fetch_history(start, end_date).to_parquet(
        raw_dir / "weather_history.parquet", index=False
    )


def cmd_transform(
    db_path: Path = paths.DB_PATH,
    raw_dir: Path = paths.RAW,
    ember_csv: Path = paths.EMBER_CSV,
    sql_dir: Path = paths.SQL_DIR,
) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)  # db.connect does not mkdir
    con = db.connect(db_path)
    db.load_raw(con, raw_dir, ember_csv)
    db.run_sql(con, sql_dir)


def cmd_backtest(
    months: int = 6,
    db_path: Path = paths.DB_PATH,
    results_dir: Path = paths.RESULTS,
) -> None:
    con = db.connect(db_path)
    matrix = build_matrix(con)
    result = walk_forward(matrix, n_test_months=months)
    results_dir.mkdir(parents=True, exist_ok=True)
    result.summary.to_csv(results_dir / "backtest.csv", index=False)
    result.per_hour.to_csv(results_dir / "backtest_per_hour.csv", index=False)
    result.predictions.to_parquet(results_dir / "predictions.parquet")


def cmd_train_artifact(
    holdout_days: int = 30,
    db_path: Path = paths.DB_PATH,
    model_path: Path = paths.MODEL_PATH,
    model_meta: Path = paths.MODEL_META,
) -> None:
    con = db.connect(db_path)
    matrix = build_matrix(con)
    max_ts = pd.Timestamp(matrix.index.max())
    train_end = max_ts - pd.Timedelta(days=holdout_days)
    train = matrix[matrix.index < train_end]

    model = LgbmModel().fit(train[FEATURES], train["y"])
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model.save(model_path)

    meta = {
        "train_end": train_end.isoformat(),
        "trained_rows": len(train),
        "features": FEATURES,
    }
    model_meta.parent.mkdir(parents=True, exist_ok=True)
    model_meta.write_text(json.dumps(meta, indent=2))


def cmd_snapshot(
    db_path: Path = paths.DB_PATH,
    snapshot_dir: Path = paths.SNAPSHOT,
) -> None:
    con = db.connect(db_path)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    for name in _SNAPSHOT_MARTS:
        frame = con.execute(f"select * from marts.{name}").df()
        frame.to_parquet(snapshot_dir / f"{name}.parquet")
    recent = con.execute(
        "select * from marts.modeling_hourly "
        "where ts_utc >= (select max(ts_utc) from marts.modeling_hourly) - interval 60 day "
        "order by ts_utc"
    ).df()
    recent.to_parquet(snapshot_dir / "recent_hourly.parquet")


def _report(label: str, ok: bool, detail: str) -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}: {detail}")
    return ok


def cmd_validate(db_path: Path = paths.DB_PATH) -> int:
    """Assert real-warehouse invariants (Task 13 thresholds).

    A plain function over a db path so it is exercisable against a fixture
    warehouse without a live network. Prints one line per check and raises
    SystemExit(1) if any check fails (after printing every line).
    """
    con = db.connect(db_path)
    today = date.today()
    checks: list[bool] = []

    ph = con.execute(
        "select count(*) as n, max(ts_utc) as max_ts, "
        "bool_or(source = 'ember') as has_ember, bool_or(source = 'pse') as has_pse "
        "from staging.price_hourly"
    ).df()
    n_ph = int(ph["n"].iloc[0])
    max_ts = pd.Timestamp(ph["max_ts"].iloc[0])
    gap_days = abs((today - max_ts.date()).days)
    has_ember = bool(ph["has_ember"].iloc[0])
    has_pse = bool(ph["has_pse"].iloc[0])
    checks.append(
        _report(
            "staging.price_hourly",
            n_ph > 95_000 and gap_days <= 3 and has_ember and has_pse,
            f"rows={n_ph:,} (>95,000); max_ts={max_ts:%Y-%m-%d %H:%M}Z gap={gap_days}d (<=3); "
            f"sources ember={has_ember} pse={has_pse}",
        )
    )

    cov = con.execute(
        "with daily as (select cast(ts_utc as date) as d, count(*) as n "
        "from staging.price_pse_hourly where cast(ts_utc as date) >= date '2024-06-15' "
        "group by 1) "
        "select count(*) filter (where n < 22 or n > 26) as bad_days, count(*) as total_days, "
        "min(n) as min_n, max(n) as max_n from daily"
    ).df()
    bad_days = int(cov["bad_days"].iloc[0])
    total_days = int(cov["total_days"].iloc[0])
    min_n = int(cov["min_n"].iloc[0])
    max_n = int(cov["max_n"].iloc[0])
    checks.append(
        _report(
            "staging.price_pse_hourly daily coverage",
            bad_days == 0,
            f"{total_days:,} UTC-days since 2024-06-15; per-day rows in "
            f"[{min_n},{max_n}]; {bad_days} outside [22,26]",
        )
    )

    nq = con.execute(
        "select avg(case when n_quarters = 4 then 1.0 else 0.0 end) as frac4, count(*) as n "
        "from staging.price_pse_hourly"
    ).df()
    frac4 = float(nq["frac4"].iloc[0])
    checks.append(
        _report(
            "staging.price_pse_hourly n_quarters",
            frac4 > 0.99,
            f"n_quarters==4 for {frac4:.4%} of {int(nq['n'].iloc[0]):,} rows (>99%)",
        )
    )

    mh = con.execute(
        "select count(*) as n, "
        "avg(case when load_fcst_mw is not null then 1.0 else 0.0 end) as load_nn, "
        "avg(case when temp_c is not null and wind_ms is not null and ghi_wm2 is not null "
        "and cloud_pct is not null then 1.0 else 0.0 end) as wx_nn "
        "from marts.modeling_hourly"
    ).df()
    n_mh = int(mh["n"].iloc[0])
    load_nn = float(mh["load_nn"].iloc[0])
    wx_nn = float(mh["wx_nn"].iloc[0])
    checks.append(
        _report(
            "marts.modeling_hourly",
            n_mh > 15_000 and load_nn > 0.95 and wx_nn > 0.95,
            f"rows={n_mh:,} (>15,000); load_fcst non-null={load_nn:.4%} (>95%); "
            f"weather non-null={wx_nn:.4%} (>95%)",
        )
    )

    qa = con.execute(
        "select median(abs_diff) as med, corr(ember_pln, pse_pln) as corr, count(*) as n "
        "from marts.qa_overlap"
    ).df()
    med = float(qa["med"].iloc[0])
    corr = float(qa["corr"].iloc[0])
    checks.append(
        _report(
            "marts.qa_overlap",
            med < 25.0 and corr > 0.97,
            f"median(abs_diff)={med:.2f} PLN/MWh (<25); corr(ember,pse)={corr:.4f} (>0.97); "
            f"n={int(qa['n'].iloc[0]):,}",
        )
    )

    for table in _TS_GRAIN_TABLES:
        dup = con.execute(f"select count(*) as c, count(distinct ts_utc) as d from {table}").df()
        c = int(dup["c"].iloc[0])
        d = int(dup["d"].iloc[0])
        checks.append(
            _report(
                f"{table} ts_utc uniqueness",
                c == d,
                f"count={c:,} distinct={d:,} ({c - d} dup)",
            )
        )

    con.close()
    if not all(checks):
        raise SystemExit(1)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cenergia")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ember = sub.add_parser("ember-slice")
    p_ember.add_argument("--raw", type=Path, required=True)
    p_ember.set_defaults(func=cmd_ember_slice)

    p_ingest = sub.add_parser("ingest")
    p_ingest.add_argument("--start", type=date.fromisoformat, required=True)
    p_ingest.add_argument("--end", type=date.fromisoformat, default=None)
    p_ingest.set_defaults(func=cmd_ingest)

    p_transform = sub.add_parser("transform")
    p_transform.set_defaults(func=cmd_transform)

    p_backtest = sub.add_parser("backtest")
    p_backtest.add_argument("--months", type=int, default=6)
    p_backtest.set_defaults(func=cmd_backtest)

    p_train = sub.add_parser("train-artifact")
    p_train.add_argument("--holdout-days", type=int, default=30)
    p_train.set_defaults(func=cmd_train_artifact)

    p_snapshot = sub.add_parser("snapshot")
    p_snapshot.set_defaults(func=cmd_snapshot)

    p_validate = sub.add_parser("validate")
    p_validate.set_defaults(func=cmd_validate)

    args = parser.parse_args(argv)
    kwargs = {k: v for k, v in vars(args).items() if k not in ("cmd", "func")}
    args.func(**kwargs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
