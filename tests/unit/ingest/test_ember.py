from pathlib import Path

import pandas as pd

from cenergia.ingest import ember

FIXTURES = Path(__file__).parents[2] / "fixtures" / "ember"


def test_slice_filters_poland_and_standardizes(tmp_path: Path) -> None:
    out = tmp_path / "pl.csv"
    n = ember.slice_ember(FIXTURES / "ember_raw_snippet.csv", out)
    assert n == 4
    df = pd.read_csv(out)
    assert list(df.columns) == ["ts_utc", "price_eur_mwh"]


def test_load_pl_hourly_types(tmp_path: Path) -> None:
    out = tmp_path / "pl.csv"
    ember.slice_ember(FIXTURES / "ember_raw_snippet.csv", out)
    df = ember.load_pl_hourly(out)
    assert str(df["ts_utc"].dtype) == "datetime64[ns]"  # UTC-naive by convention
    assert df["price_eur_mwh"].dtype == "float64"
    assert df["ts_utc"].is_monotonic_increasing
