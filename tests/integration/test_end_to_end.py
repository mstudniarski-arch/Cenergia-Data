"""End-to-end pipeline tests: real DuckDB + real SQL, no network."""

from __future__ import annotations

from pathlib import Path

from cenergia import pipeline
from cenergia.warehouse import db
from tests.helpers import seed_raw_dir


def test_transform_end_to_end(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    ember_csv = tmp_path / "ember.csv"
    seed_raw_dir(raw, ember_csv)
    db_path = tmp_path / "w.duckdb"

    pipeline.cmd_transform(
        db_path=db_path, raw_dir=raw, ember_csv=ember_csv, sql_dir=pipeline.paths.SQL_DIR
    )

    con = db.connect(db_path)
    assert con.execute("select count(*) from marts.modeling_hourly").fetchone()[0] == 2  # type: ignore[index]


def test_transform_creates_missing_db_parent_dir(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    ember_csv = tmp_path / "ember.csv"
    seed_raw_dir(raw, ember_csv)
    db_path = tmp_path / "nested" / "does" / "not" / "exist" / "w.duckdb"

    pipeline.cmd_transform(
        db_path=db_path, raw_dir=raw, ember_csv=ember_csv, sql_dir=pipeline.paths.SQL_DIR
    )

    assert db_path.exists()
