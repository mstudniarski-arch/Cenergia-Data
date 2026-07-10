import duckdb
import numpy as np
import pandas as pd

from cenergia.features import matrix
from cenergia.warehouse import db


def _seed_modeling(n_hours: int = 24 * 10) -> duckdb.DuckDBPyConnection:
    con = db.connect(":memory:")
    ts = pd.date_range("2025-01-01", periods=n_hours, freq="h")
    frame = pd.DataFrame(
        {
            "ts_utc": ts,
            "price_pln_mwh": np.arange(n_hours, dtype="float64"),
            "load_fcst_mw": 20000.0,
            "temp_c": 5.0,
            "wind_ms": 6.0,
            "ghi_wm2": 50.0,
            "cloud_pct": 80.0,
            "wind_mw": 3000.0,
            "pv_mw": 100.0,
            "is_15min_regime": False,
        }
    )
    con.register("_m", frame)
    con.execute("create or replace table marts.modeling_hourly as select * from _m")
    return con


def test_lags_are_exact() -> None:
    m = matrix.build_matrix(_seed_modeling())
    row = m.iloc[-1]
    assert row["y"] - row["price_lag24"] == 24.0
    assert row["y"] - row["price_lag168"] == 168.0
    # rolling mean of a linear sequence ending at lag24: mean of (y-24-167 .. y-24)
    assert row["price_roll7d_mean"] == row["price_lag24"] - 167 / 2


def test_calendar_features_are_warsaw_local() -> None:
    m = matrix.build_matrix(_seed_modeling())
    # 2025-01-08 22:00 UTC == 23:00 CET
    row = m.loc[pd.Timestamp("2025-01-08 22:00:00")]
    assert row["hour_local"] == 23
    # 2025-01-01 is a Polish holiday; UTC 2025-01-01 10:00 is local 11:00 same day
    # (that row is dropped by lag168 NaN — instead check via the holiday helper)
    assert matrix.is_pl_holiday(pd.Timestamp("2025-01-06"))  # Epiphany
    assert not matrix.is_pl_holiday(pd.Timestamp("2025-01-07"))


def test_no_nan_targets_or_price_lags() -> None:
    m = matrix.build_matrix(_seed_modeling())
    assert m["y"].notna().all()
    assert m["price_lag168"].notna().all()
    assert list(m.columns) == ["y", *matrix.FEATURES]
