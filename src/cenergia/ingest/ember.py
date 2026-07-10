"""Ember European wholesale electricity price CSV — Poland slice.

The raw file is downloaded MANUALLY (the site 403s non-browser fetchers) from
https://ember-energy.org/data/european-wholesale-electricity-price-data/
(hourly, all countries). The PL slice is committed at data/ember_pl_hourly.csv
so the 11-year history is reproducible without the download. CC-BY-4.0.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

_RAW_COLS = {"Datetime (UTC)": "ts_utc", "Price (EUR/MWhe)": "price_eur_mwh"}


def slice_ember(raw_csv: Path, out_csv: Path) -> int:
    df = pd.read_csv(raw_csv)
    missing = {"Country", *_RAW_COLS} - set(df.columns)
    if missing:
        msg = f"Unexpected Ember schema; missing {sorted(missing)}, got {list(df.columns)}"
        raise ValueError(msg)
    pl = (
        df.loc[df["Country"] == "Poland", list(_RAW_COLS)]
        .rename(columns=_RAW_COLS)
        .sort_values("ts_utc")
    )
    pl.to_csv(out_csv, index=False)
    return len(pl)


def load_pl_hourly(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    ts = pd.to_datetime(df["ts_utc"], utc=True).dt.tz_localize(None)
    df["ts_utc"] = ts.astype("datetime64[ns]")
    df["price_eur_mwh"] = df["price_eur_mwh"].astype("float64")
    return df.sort_values("ts_utc").reset_index(drop=True)
