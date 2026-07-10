"""MAE/RMSE/rMAE. No MAPE: Polish day-ahead prices cross zero (negative-price hours),
which makes percentage errors explode or flip sign — rMAE vs naive is the skill metric."""

from __future__ import annotations

import pandas as pd


def mae(y_true: pd.Series, y_pred: pd.Series) -> float:
    return float((y_true - y_pred).abs().mean())


def rmse(y_true: pd.Series, y_pred: pd.Series) -> float:
    return float(((y_true - y_pred) ** 2).mean() ** 0.5)


def rmae(y_true: pd.Series, y_pred: pd.Series, y_naive: pd.Series) -> float:
    denom = mae(y_true, y_naive)
    if denom == 0.0:
        raise ValueError("naive MAE is zero; rMAE undefined")
    return mae(y_true, y_pred) / denom
