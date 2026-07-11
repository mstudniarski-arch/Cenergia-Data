"""Smoke-tests the whole app shell end to end via Streamlit's `AppTest`
harness: script executes, no exception, both snapshot pages render, and the
forecast placeholder shows. Runs headless, no server, no network — `at.run`
executes `app.py` top to bottom against a tmp snapshot pointed to by
`CENERGIA_SNAPSHOT_DIR` (see the `snapshot_dir` fixture in conftest.py).
"""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest


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


def test_forecast_placeholder_renders(snapshot_dir: Path) -> None:
    at = AppTest.from_file("src/cenergia/dashboard/app.py")
    at.run(timeout=30)

    at.sidebar.radio[0].set_value("Tomorrow's forecast").run(timeout=30)

    assert not at.exception
    assert any("coming in Task 18" in info.value for info in at.info)
