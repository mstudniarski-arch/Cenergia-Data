"""Snapshot loading for the dashboard: reads the pre-baked parquet marts from
`paths.SNAPSHOT` (or an override) into a typed, frozen `Snapshot`.

Loading is split into a thin public `load_snapshot`, which resolves *where*
to read from, and a private `st.cache_data`-wrapped `_read_snapshot`, which
does the actual parquet I/O keyed on the resolved directory. Resolving first
and caching second matters: `st.cache_data` hashes only its *arguments*, not
ambient state, so a cached function that reads `CENERGIA_SNAPSHOT_DIR`
internally would keep returning the first directory's data forever, even
after the env var changes (e.g. across pytest tests in the same worker, or
if a deployment ever changes the env var without restarting the process).
Resolving the directory outside the cached function and passing it in as
the sole argument sidesteps that trap.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import streamlit as st

from cenergia import paths

_ENV_VAR = "CENERGIA_SNAPSHOT_DIR"

# Field order matches the produced-interface contract other tasks (Task 18)
# depend on: price_daily, typical_shape, merit_order, recent_hourly, qa_overlap.
_SNAPSHOT_FILES: tuple[str, ...] = (
    "price_daily",
    "typical_shape",
    "merit_order",
    "recent_hourly",
    "qa_overlap",
)


@dataclass(frozen=True)
class Snapshot:
    price_daily: pd.DataFrame
    typical_shape: pd.DataFrame
    merit_order: pd.DataFrame
    recent_hourly: pd.DataFrame
    qa_overlap: pd.DataFrame
    as_of: pd.Timestamp


def load_snapshot(snapshot_dir: Path | None = None) -> Snapshot:
    """Load the dashboard snapshot.

    Resolution order: explicit `snapshot_dir` arg > `CENERGIA_SNAPSHOT_DIR`
    env var > `paths.SNAPSHOT`. Resolution happens on every call (cheap), so
    the env var is honored on every Streamlit rerun; only the parquet read
    itself is cached, keyed on the resolved path.
    """
    resolved = _resolve_dir(snapshot_dir)
    return _read_snapshot(resolved)


def _resolve_dir(snapshot_dir: Path | None) -> Path:
    if snapshot_dir is not None:
        return snapshot_dir
    env_value = os.environ.get(_ENV_VAR)
    if env_value:
        return Path(env_value)
    return paths.SNAPSHOT


@st.cache_data
def _read_snapshot(snapshot_dir: Path) -> Snapshot:
    frames = {name: _read_parquet(snapshot_dir, name) for name in _SNAPSHOT_FILES}
    as_of = pd.Timestamp(frames["price_daily"]["date"].max())
    return Snapshot(
        price_daily=frames["price_daily"],
        typical_shape=frames["typical_shape"],
        merit_order=frames["merit_order"],
        recent_hourly=frames["recent_hourly"],
        qa_overlap=frames["qa_overlap"],
        as_of=as_of,
    )


def _read_parquet(snapshot_dir: Path, name: str) -> pd.DataFrame:
    path = snapshot_dir / f"{name}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"missing dashboard snapshot file: {path}")
    return pd.read_parquet(path)
