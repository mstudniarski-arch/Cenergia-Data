from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cenergia.models.lgbm import LgbmModel


def _toy() -> tuple[pd.DataFrame, pd.Series]:
    rng = np.random.default_rng(0)
    x = rng.uniform(0, 10, size=(500, 2))
    X = pd.DataFrame(x, columns=["a", "b"])
    y = pd.Series(2.0 * X["a"] - 3.0 * X["b"])
    return X, y


def test_fit_predict_learns_linear_signal() -> None:
    X, y = _toy()
    model = LgbmModel().fit(X, y)
    pred = model.predict(X)
    assert float(np.abs(pred - y.to_numpy()).mean()) < 1.0


def test_save_load_roundtrip(tmp_path: Path) -> None:
    X, y = _toy()
    model = LgbmModel().fit(X, y)
    p = tmp_path / "m.txt"
    model.save(p)
    reloaded = LgbmModel.load(p)
    assert np.allclose(model.predict(X), reloaded.predict(X))


def test_unfitted_raises() -> None:
    X, _ = _toy()
    with pytest.raises(RuntimeError):
        LgbmModel().predict(X)
