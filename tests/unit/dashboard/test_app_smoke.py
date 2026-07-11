"""Smoke-tests the whole app shell end to end via Streamlit's `AppTest`
harness: script executes, no exception, both snapshot pages render, and the
forecast page renders in both its happy and degraded forms (with the live
loader monkeypatched — no network in this suite). Runs headless, no server —
`at.run` executes `app.py` top to bottom against a tmp snapshot pointed to by
`CENERGIA_SNAPSHOT_DIR` (see the `snapshot_dir` fixture in conftest.py).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from cenergia.dashboard import live


def test_app_renders_without_exception(snapshot_dir: Path) -> None:
    at = AppTest.from_file("src/cenergia/dashboard/app.py")
    at.run(timeout=30)

    assert not at.exception


def test_market_overview_page_renders(snapshot_dir: Path) -> None:
    at = AppTest.from_file("src/cenergia/dashboard/app.py")
    at.run(timeout=30)

    at.sidebar.radio[0].set_value("Market overview").run(timeout=30)

    assert not at.exception
    assert "Market overview" in [h.value for h in at.header]


def test_price_drivers_page_renders(snapshot_dir: Path) -> None:
    at = AppTest.from_file("src/cenergia/dashboard/app.py")
    at.run(timeout=30)

    at.sidebar.radio[0].set_value("Price drivers").run(timeout=30)

    assert not at.exception
    assert "Price drivers" in [h.value for h in at.header]


def _fake_live_forecast(degraded: bool) -> live.LiveForecast:
    made_at = pd.Timestamp("2026-03-15 09:00:00")
    # 5 days: made_at-2d .. made_at+2d, so the "tomorrow" slice (made_at+1d,
    # 24h) is populated even in the happy case.
    ts = pd.date_range(made_at.normalize() - pd.Timedelta(days=2), periods=5 * 24, freq="h")
    frame = pd.DataFrame(
        {
            "ts_utc": ts,
            "y_pred": [float("nan")] * len(ts) if degraded else [300.0 + i for i in range(len(ts))],
            "y_actual": [290.0 + i for i in range(len(ts))],
        }
    )
    return live.LiveForecast(
        made_at_utc=made_at, frame=frame, degraded=degraded, train_end="2026-02-01T00:00:00"
    )


def test_forecast_page_renders_happy(snapshot_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(live, "get_live_forecast", lambda: _fake_live_forecast(degraded=False))

    at = AppTest.from_file("src/cenergia/dashboard/app.py")
    at.run(timeout=30)
    at.sidebar.radio[0].set_value("Tomorrow's forecast").run(timeout=30)

    assert not at.exception
    assert "Tomorrow's forecast" in [h.value for h in at.header]
    assert not any(w for w in at.warning)


def test_forecast_page_renders_degraded(
    snapshot_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(live, "get_live_forecast", lambda: _fake_live_forecast(degraded=True))

    at = AppTest.from_file("src/cenergia/dashboard/app.py")
    at.run(timeout=30)
    at.sidebar.radio[0].set_value("Tomorrow's forecast").run(timeout=30)

    assert not at.exception
    assert "Tomorrow's forecast" in [h.value for h in at.header]
    assert any(w for w in at.warning)
