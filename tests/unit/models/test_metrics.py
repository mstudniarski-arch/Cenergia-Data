import pandas as pd
import pytest

from cenergia.models import metrics


def test_mae_rmse() -> None:
    y = pd.Series([0.0, 2.0])
    p = pd.Series([1.0, 0.0])
    assert metrics.mae(y, p) == 1.5
    assert metrics.rmse(y, p) == pytest.approx((2.5) ** 0.5)


def test_rmae_beats_naive_is_below_one() -> None:
    y = pd.Series([10.0, 10.0])
    good = pd.Series([9.5, 10.5])
    naive = pd.Series([8.0, 12.0])
    assert metrics.rmae(y, good, naive) == pytest.approx(0.25)


def test_rmae_zero_naive_raises() -> None:
    y = pd.Series([1.0])
    with pytest.raises(ValueError):
        metrics.rmae(y, y, y)
