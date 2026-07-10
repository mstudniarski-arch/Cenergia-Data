import numpy as np
import pandas as pd

from cenergia.features.matrix import FEATURES
from cenergia.models import backtest


def _matrix(months: int = 10) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=24 * 30 * months, freq="h")
    rng = np.random.default_rng(1)
    m = pd.DataFrame(index=idx)
    base = 300 + 50 * np.sin(np.arange(len(idx)) * 2 * np.pi / 24)
    m["y"] = base + rng.normal(0, 5, len(idx))
    m["price_lag24"] = m["y"].shift(24)
    m["price_lag48"] = m["y"].shift(48)
    m["price_lag168"] = m["y"].shift(168)
    m["price_roll7d_mean"] = m["y"].shift(24).rolling(168).mean()
    m["price_roll7d_std"] = m["y"].shift(24).rolling(168).std()
    for c in FEATURES:
        if c not in m.columns:
            m[c] = 0.0
    return m.dropna()


def test_test_months_are_last_complete() -> None:
    m = _matrix()
    months = backtest.test_months(m, 3)
    assert len(months) == 3
    assert all(isinstance(p, pd.Period) for p in months)
    assert months == sorted(months)


def test_no_training_on_test_month() -> None:
    m = _matrix()
    captured: list[tuple[pd.Timestamp, pd.Timestamp]] = []

    class SpyModel(backtest.LgbmModel):
        # Base LgbmModel.fit is annotated `-> LgbmModel` (a concrete class,
        # not `Self`), so `super().fit(...)` is statically an LgbmModel even
        # though it returns `self` at runtime; match that here rather than
        # narrowing to "SpyModel", which mypy strict would reject.
        def fit(self, X: pd.DataFrame, y: pd.Series) -> "backtest.LgbmModel":
            captured.append((X.index.max(), X.index.min()))
            return super().fit(X, y)

    backtest.walk_forward(m, n_test_months=2, model_cls=SpyModel)
    assert len(captured) == 2  # refit per month
    for (train_max, _), month in zip(captured, backtest.test_months(m, 2), strict=True):
        month_start_utc = backtest.month_start_utc(month)
        assert train_max < month_start_utc


def test_summary_shape_and_naive_rmae_is_one() -> None:
    m = _matrix()
    result = backtest.walk_forward(m, n_test_months=2)
    assert set(result.summary["model"]) == {"naive", "seasonal_naive", "lgbm"}
    naive_all = result.summary.query("model == 'naive' and month == 'ALL'")
    assert naive_all["rmae"].iloc[0] == 1.0
    assert set(result.per_hour["model"]) == {"naive", "seasonal_naive", "lgbm"}
    assert {"y", "naive", "seasonal_naive", "lgbm", "month"} <= set(result.predictions.columns)
