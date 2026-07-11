"""Shared tmp-snapshot fixture builder for dashboard tests.

`write_snapshot` builds tiny (2-row) parquet files matching the real
`data/snapshot/*.parquet` schemas (see `cenergia.pipeline.cmd_snapshot` and
`sql/11_marts_dashboard.sql` / `sql/12_marts_qa.sql`), so `data_access` and
the `AppTest` smoke test exercise the same shapes production data has.
"""

from __future__ import annotations

from collections.abc import Iterator, Set
from pathlib import Path

import pandas as pd
import pytest

_ALL_FILES: tuple[str, ...] = (
    "price_daily",
    "typical_shape",
    "merit_order",
    "recent_hourly",
    "qa_overlap",
)


def _price_daily(avg_price: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-06-13", "2024-06-14"]),
            "source": ["ember", "pse"],
            "avg_price": [avg_price, avg_price + 10.0],
            "min_price": [50.0, 60.0],
            "max_price": [150.0, 180.0],
        }
    )


def _typical_shape() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "season": ["winter", "summer"],
            "year": [2024, 2024],
            "hour_local": [8, 20],
            "avg_price": [180.0, 220.0],
        }
    )


def _merit_order() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_utc": pd.to_datetime(["2024-06-14 00:00:00", "2024-06-14 01:00:00"]),
            "price_pln_mwh": [400.0, 350.0],
            "res_mw": [2500.0, 3000.0],
            "load_mw": [19000.0, 18500.0],
            "res_share": [0.13, 0.16],
        }
    )


def _qa_overlap() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_utc": pd.to_datetime(["2024-06-13 16:00:00", "2024-06-13 17:00:00"]),
            "ember_pln": [750.0, 500.0],
            "pse_pln": [749.8, 499.5],
            "abs_diff": [0.2, 0.5],
        }
    )


def _recent_hourly() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_utc": pd.to_datetime(["2026-05-12 21:00:00", "2026-05-12 22:00:00"]),
            "price_pln_mwh": [494.985, 488.910],
            "load_fcst_mw": [18000.0, 17500.0],
            "temp_c": [12.0, 11.5],
            "wind_ms": [4.0, 4.5],
            "ghi_wm2": [0.0, 0.0],
            "cloud_pct": [80.0, 90.0],
            "wind_mw": [2100.0, 2200.0],
            "pv_mw": [0.0, 0.0],
            "is_15min_regime": [True, True],
        }
    )


_BUILDERS = {
    "typical_shape": lambda: _typical_shape(),
    "merit_order": lambda: _merit_order(),
    "qa_overlap": lambda: _qa_overlap(),
    "recent_hourly": lambda: _recent_hourly(),
}


def write_snapshot(dir_: Path, skip: Set[str] = frozenset(), price_avg: float = 100.0) -> None:
    """Write the 2-row fixture parquets into `dir_`, skipping any name in `skip`."""
    if "price_daily" not in skip:
        _price_daily(price_avg).to_parquet(dir_ / "price_daily.parquet")
    for name in _ALL_FILES:
        if name == "price_daily" or name in skip:
            continue
        _BUILDERS[name]().to_parquet(dir_ / f"{name}.parquet")


@pytest.fixture
def snapshot_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A tmp snapshot dir with all 5 parquets, with CENERGIA_SNAPSHOT_DIR pointed
    at it. `monkeypatch` restores the env var on teardown.
    """
    snap_dir = tmp_path / "snapshot"
    snap_dir.mkdir()
    write_snapshot(snap_dir)
    monkeypatch.setenv("CENERGIA_SNAPSHOT_DIR", str(snap_dir))
    yield snap_dir
