"""Baselines ARE matrix columns — by construction identical to what a lag-only
forecaster could know before the auction cutoff."""

from __future__ import annotations

import pandas as pd


def naive(m: pd.DataFrame) -> pd.Series:
    return m["price_lag24"].rename("naive")


def seasonal_naive(m: pd.DataFrame) -> pd.Series:
    return m["price_lag168"].rename("seasonal_naive")
