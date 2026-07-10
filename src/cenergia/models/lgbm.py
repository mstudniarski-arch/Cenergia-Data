"""Thin, deterministic LightGBM regressor wrapper (text-format artifact, committed)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

DEFAULT_PARAMS: dict[str, Any] = {
    "objective": "regression_l1",
    "n_estimators": 600,
    "learning_rate": 0.05,
    "num_leaves": 63,
    "seed": 42,
    "deterministic": True,
    "verbosity": -1,
}


class LgbmModel:
    def __init__(self, params: dict[str, Any] | None = None) -> None:
        self.params = dict(DEFAULT_PARAMS if params is None else params)
        self._booster: lgb.Booster | None = None

    def fit(self, X: pd.DataFrame, y: pd.Series) -> LgbmModel:
        reg = lgb.LGBMRegressor(**self.params)
        reg.fit(X, y)
        self._booster = reg.booster_
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self._booster is None:
            raise RuntimeError("model is not fitted")
        return np.asarray(self._booster.predict(X))

    def save(self, path: Path) -> None:
        if self._booster is None:
            raise RuntimeError("model is not fitted")
        path.write_text(self._booster.model_to_string())

    @classmethod
    def load(cls, path: Path) -> LgbmModel:
        model = cls()
        model._booster = lgb.Booster(model_str=path.read_text())
        return model
