from pathlib import Path

import duckdb
import pytest

from cenergia.ingest.openmeteo import cities_frame
from cenergia.warehouse import db
from tests.helpers import ember_frame, raw_frames

SQL_DIR = Path(__file__).parents[3] / "sql"


@pytest.fixture()
def con() -> duckdb.DuckDBPyConnection:
    """In-memory warehouse with minimal-but-complete raw fixtures."""
    c = db.connect(":memory:")
    frames = {**raw_frames(), "ember_pl": ember_frame()}
    db.load_frames(c, frames)
    # cities seed comes from load_raw normally; register directly here
    db.load_frames(c, {"weather_cities": cities_frame()})
    db.run_sql(c, SQL_DIR)
    return c
