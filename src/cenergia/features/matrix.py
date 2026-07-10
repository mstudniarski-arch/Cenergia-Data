"""Leakage-safe feature matrix.

Cutoff-safety derivation: a D+1 forecast is made before 12:00 Europe/Warsaw on
day D. Day-ahead prices for delivery day X are published ~13:00 on day X-1, so
at the forecast moment every price with local delivery date <= D is known. A
price lag of `L` hours from delivery hour `h` (local) of day D+1 reaches local
day <= D iff `L >= h + 1`; the worst case is `h = 23`, so any `L >= 24` is safe
for all hours. `load_fcst_mw` (PSE's D+1 forecast) and weather (Open-Meteo D+1
forecast) are forecast-kind: published before the cutoff by construction.
Calendar features are deterministic.
"""

from __future__ import annotations

import duckdb
import holidays
import pandas as pd

BREAK_TS_UTC = pd.Timestamp("2025-09-30 22:00:00")

FEATURES: list[str] = [
    "price_lag24",
    "price_lag48",
    "price_lag168",
    "price_roll7d_mean",
    "price_roll7d_std",
    "load_fcst_mw",
    "temp_c",
    "wind_ms",
    "ghi_wm2",
    "cloud_pct",
    "hour_local",
    "dow_local",
    "month_local",
    "is_holiday",
    "is_weekend",
    "post_break",
]

FEATURE_KIND: dict[str, tuple[str, int | None]] = {
    "price_lag24": ("lagged_price", 24),
    "price_lag48": ("lagged_price", 48),
    "price_lag168": ("lagged_price", 168),
    "price_roll7d_mean": ("lagged_price", 24),  # window ENDS at lag24
    "price_roll7d_std": ("lagged_price", 24),
    "load_fcst_mw": ("forecast", None),
    "temp_c": ("forecast", None),
    "wind_ms": ("forecast", None),
    "ghi_wm2": ("forecast", None),
    "cloud_pct": ("forecast", None),
    "hour_local": ("deterministic", None),
    "dow_local": ("deterministic", None),
    "month_local": ("deterministic", None),
    "is_holiday": ("deterministic", None),
    "is_weekend": ("deterministic", None),
    "post_break": ("deterministic", None),
}

_PL_HOLIDAYS = holidays.country_holidays("PL")


def lag_is_cutoff_safe(lag_h: int) -> bool:
    return lag_h >= 24


def is_pl_holiday(ts: pd.Timestamp) -> bool:
    return ts.date() in _PL_HOLIDAYS


def build_matrix(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    df = con.execute("select * from marts.modeling_hourly order by ts_utc").df().set_index("ts_utc")
    # pandas 3.x can hand back a datetime64[us] index from DuckDB's .df();
    # normalize to [ns] so asfreq/tz_localize behave like the rest of the repo
    # (see ingest/ember.py, ingest/nbp.py for the same pattern).
    df.index = df.index.astype("datetime64[ns]")
    df = df.asfreq("h")  # gaps become explicit NaN rows

    price = df["price_pln_mwh"]
    out = pd.DataFrame(index=df.index)
    out["y"] = price
    out["price_lag24"] = price.shift(24)
    out["price_lag48"] = price.shift(48)
    out["price_lag168"] = price.shift(168)
    lag24 = price.shift(24)
    # Full window required (default min_periods == 168): partial-window rolling
    # stats near the start of history would be noisy, and the dropna on
    # price_roll7d_mean below is what enforces the warm-up boundary — the first
    # surviving row is the first with BOTH a full lag168 and a complete
    # 168-point window on lag24 (pinned by test_first_row_is_full_window_boundary).
    out["price_roll7d_mean"] = lag24.rolling(168).mean()
    out["price_roll7d_std"] = lag24.rolling(168).std()
    for col in ("load_fcst_mw", "temp_c", "wind_ms", "ghi_wm2", "cloud_pct"):
        out[col] = df[col]

    local = pd.DatetimeIndex(out.index).tz_localize("UTC").tz_convert("Europe/Warsaw")
    out["hour_local"] = local.hour
    out["dow_local"] = local.dayofweek
    out["month_local"] = local.month
    local_dates = pd.Series(local.date, index=out.index)
    out["is_holiday"] = local_dates.map(lambda d: int(d in _PL_HOLIDAYS))
    out["is_weekend"] = (out["dow_local"] >= 5).astype(int)
    out["post_break"] = (out.index >= BREAK_TS_UTC).astype(int)

    out = out.dropna(subset=["y", "price_lag168", "price_roll7d_mean"])
    return out[["y", *FEATURES]]
