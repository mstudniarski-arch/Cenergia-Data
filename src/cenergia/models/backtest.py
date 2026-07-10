"""Walk-forward backtest: monthly refit, train strictly before each test month."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import pandas as pd

from cenergia.features.matrix import FEATURES
from cenergia.models import baselines, metrics

# Re-exported (not just imported) so `backtest.LgbmModel` is a valid public
# name for callers/tests to subclass, e.g. test_backtest.py's SpyModel; mypy
# strict's no_implicit_reexport otherwise treats a bare import as private.
from cenergia.models.lgbm import LgbmModel as LgbmModel

MODEL_NAMES: tuple[str, ...] = ("naive", "seasonal_naive", "lgbm")


@dataclass
class BacktestResult:
    summary: pd.DataFrame
    per_hour: pd.DataFrame
    predictions: pd.DataFrame


def _local_period(idx: pd.DatetimeIndex) -> pd.PeriodIndex:
    return idx.tz_localize("UTC").tz_convert("Europe/Warsaw").to_period("M")


def month_start_utc(month: pd.Period) -> pd.Timestamp:
    local_start = month.to_timestamp().tz_localize("Europe/Warsaw")
    return local_start.tz_convert("UTC").tz_localize(None)


def test_months(m: pd.DataFrame, n: int) -> list[pd.Period]:
    periods = _local_period(pd.DatetimeIndex(m.index))
    complete = [p for p in periods.unique() if (periods == p).sum() >= 27 * 24]
    return sorted(complete)[-n:]


def walk_forward(
    m: pd.DataFrame, n_test_months: int = 6, model_cls: type[LgbmModel] = LgbmModel
) -> BacktestResult:
    months = test_months(m, n_test_months)
    periods = _local_period(pd.DatetimeIndex(m.index))
    pred_frames: list[pd.DataFrame] = []
    for month in months:
        cutoff = month_start_utc(month)
        train = m[m.index < cutoff]
        test = m[periods == month]
        model = model_cls().fit(train[FEATURES], train["y"])
        chunk = test[["y"]].copy()
        chunk["naive"] = baselines.naive(test)
        chunk["seasonal_naive"] = baselines.seasonal_naive(test)
        chunk["lgbm"] = model.predict(test[FEATURES])
        chunk["month"] = str(month)
        chunk["hour_local"] = test["hour_local"].astype(int)
        pred_frames.append(chunk)
    preds = pd.concat(pred_frames)

    month_groups: list[tuple[str, pd.DataFrame]] = [
        (str(month_key), grp) for month_key, grp in preds.groupby("month")
    ]
    rows: list[dict[str, str | float]] = []
    for model_name in MODEL_NAMES:
        for month_label, grp in [*month_groups, ("ALL", preds)]:
            rows.append(
                {
                    "model": model_name,
                    "month": month_label,
                    "mae": metrics.mae(grp["y"], grp[model_name]),
                    "rmse": metrics.rmse(grp["y"], grp[model_name]),
                    "rmae": metrics.rmae(grp["y"], grp[model_name], grp["naive"]),
                }
            )
    summary = pd.DataFrame(rows)

    # pandas-stubs types a by-column-name groupby key as a broad Hashable
    # union that `int()` doesn't accept; cast narrows it back to what
    # "hour_local" actually holds at runtime (see FEATURES/matrix.py).
    hour_groups: list[tuple[int, pd.DataFrame]] = [
        (cast(int, hour), grp) for hour, grp in preds.groupby("hour_local")
    ]
    hour_rows: list[dict[str, str | int | float]] = []
    for model_name in MODEL_NAMES:
        for hour, grp in hour_groups:
            hour_rows.append(
                {
                    "model": model_name,
                    "hour_local": hour,
                    "mae": metrics.mae(grp["y"], grp[model_name]),
                }
            )
    per_hour = pd.DataFrame(hour_rows)
    return BacktestResult(summary, per_hour, preds.drop(columns=["hour_local"]))
