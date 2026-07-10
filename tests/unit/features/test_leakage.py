"""THE leakage guard: every feature must be classified and provably pre-cutoff."""

from cenergia.features import matrix


def test_every_feature_is_classified() -> None:
    assert set(matrix.FEATURE_KIND) == set(matrix.FEATURES)


def test_lagged_price_features_are_cutoff_safe() -> None:
    for name, (kind, lag) in matrix.FEATURE_KIND.items():
        if kind == "lagged_price":
            assert lag is not None and matrix.lag_is_cutoff_safe(lag), name
        else:
            assert kind in ("forecast", "deterministic"), name


def test_unsafe_lag_rejected() -> None:
    # h=23 delivery hour would see a 12h lag reach into its own delivery day
    assert not matrix.lag_is_cutoff_safe(12)
    assert not matrix.lag_is_cutoff_safe(23)
    assert matrix.lag_is_cutoff_safe(24)
