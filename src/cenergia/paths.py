"""Canonical on-disk locations, shared by the pipeline CLI, notebooks, and the
dashboard. All paths are absolute and derived from the repo root so callers
never depend on the current working directory.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
DB_PATH = DATA / "warehouse.duckdb"
EMBER_CSV = DATA / "ember_pl_hourly.csv"
SQL_DIR = ROOT / "sql"
RESULTS = ROOT / "results"
SNAPSHOT = DATA / "snapshot"
MODEL_PATH = DATA / "model_lgbm.txt"
MODEL_META = DATA / "model_meta.json"
