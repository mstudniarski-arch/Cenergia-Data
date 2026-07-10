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


def cmd_validate() -> int:
    print("validate: thresholds wired in Task 13")
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
