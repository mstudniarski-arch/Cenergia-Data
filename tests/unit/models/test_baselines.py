import pandas as pd

from cenergia.models import baselines


def test_baselines_are_lag_columns() -> None:
    m = pd.DataFrame({"price_lag24": [1.0, 2.0], "price_lag168": [3.0, 4.0]})
    assert baselines.naive(m).tolist() == [1.0, 2.0]
    assert baselines.naive(m).name == "naive"
    assert baselines.seasonal_naive(m).tolist() == [3.0, 4.0]
    assert baselines.seasonal_naive(m).name == "seasonal_naive"
