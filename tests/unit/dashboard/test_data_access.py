from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from cenergia.dashboard import data_access
from tests.unit.dashboard.conftest import write_snapshot


def test_load_snapshot_returns_typed_frames(snapshot_dir: Path) -> None:
    snap = data_access.load_snapshot(snapshot_dir)

    assert isinstance(snap.price_daily, pd.DataFrame)
    assert isinstance(snap.typical_shape, pd.DataFrame)
    assert isinstance(snap.merit_order, pd.DataFrame)
    assert isinstance(snap.recent_hourly, pd.DataFrame)
    assert isinstance(snap.qa_overlap, pd.DataFrame)
    assert len(snap.price_daily) == 2
    assert len(snap.typical_shape) == 2
    assert len(snap.merit_order) == 2
    assert len(snap.recent_hourly) == 2
    assert len(snap.qa_overlap) == 2
    assert list(snap.price_daily.columns) == [
        "date",
        "source",
        "avg_price",
        "min_price",
        "max_price",
    ]


def test_as_of_is_max_date_in_price_daily(snapshot_dir: Path) -> None:
    snap = data_access.load_snapshot(snapshot_dir)

    assert snap.as_of == pd.Timestamp("2024-06-14")


def test_missing_file_raises_file_not_found_error_naming_it(tmp_path: Path) -> None:
    incomplete = tmp_path / "incomplete"
    incomplete.mkdir()
    write_snapshot(incomplete, skip={"price_daily"})

    with pytest.raises(FileNotFoundError, match=r"price_daily\.parquet"):
        data_access.load_snapshot(incomplete)


def test_env_var_override_is_honored(snapshot_dir: Path) -> None:
    # snapshot_dir fixture already exported CENERGIA_SNAPSHOT_DIR; calling with
    # no explicit arg must fall back to it.
    snap = data_access.load_snapshot()

    assert len(snap.price_daily) == 2


def test_env_var_change_is_reflected_across_calls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression guard: `load_snapshot` must resolve the env var on every
    call, not read it once inside the `st.cache_data`-wrapped reader — a
    cache keyed only on a fixed default arg would otherwise return the first
    directory's data forever.
    """
    dir_a = tmp_path / "a"
    dir_a.mkdir()
    write_snapshot(dir_a, price_avg=100.0)
    dir_b = tmp_path / "b"
    dir_b.mkdir()
    write_snapshot(dir_b, price_avg=900.0)

    monkeypatch.setenv("CENERGIA_SNAPSHOT_DIR", str(dir_a))
    snap_a = data_access.load_snapshot()
    monkeypatch.setenv("CENERGIA_SNAPSHOT_DIR", str(dir_b))
    snap_b = data_access.load_snapshot()

    assert snap_a.price_daily["avg_price"].iloc[0] == 100.0
    assert snap_b.price_daily["avg_price"].iloc[0] == 900.0


def test_explicit_arg_takes_priority_over_env_var(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_dir = tmp_path / "env"
    env_dir.mkdir()
    write_snapshot(env_dir, price_avg=1.0)
    explicit_dir = tmp_path / "explicit"
    explicit_dir.mkdir()
    write_snapshot(explicit_dir, price_avg=2.0)

    monkeypatch.setenv("CENERGIA_SNAPSHOT_DIR", str(env_dir))
    snap = data_access.load_snapshot(explicit_dir)

    assert snap.price_daily["avg_price"].iloc[0] == 2.0
