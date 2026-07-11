"""Dispatch-only unit tests: main() parses argv and calls the right cmd_* with
the right kwargs. Command functions are monkeypatched, so this never touches
the network, a real warehouse, or the filesystem beyond argparse itself.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from cenergia import pipeline


def _capture(monkeypatch: pytest.MonkeyPatch, name: str) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(pipeline, name, fake)
    return calls


def test_ember_slice_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture(monkeypatch, "cmd_ember_slice")
    assert pipeline.main(["ember-slice", "--raw", "raw.csv"]) == 0
    assert calls == [{"raw": Path("raw.csv")}]


def test_ingest_dispatch_defaults_end_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture(monkeypatch, "cmd_ingest")
    assert pipeline.main(["ingest", "--start", "2024-06-14"]) == 0
    assert calls == [{"start": date(2024, 6, 14), "end": None}]


def test_ingest_dispatch_with_end(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture(monkeypatch, "cmd_ingest")
    pipeline.main(["ingest", "--start", "2024-06-14", "--end", "2024-06-20"])
    assert calls == [{"start": date(2024, 6, 14), "end": date(2024, 6, 20)}]


def test_ingest_requires_start() -> None:
    with pytest.raises(SystemExit):
        pipeline.main(["ingest"])


def test_transform_dispatch_no_args(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture(monkeypatch, "cmd_transform")
    assert pipeline.main(["transform"]) == 0
    assert calls == [{}]


def test_backtest_dispatch_default_months(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture(monkeypatch, "cmd_backtest")
    assert pipeline.main(["backtest"]) == 0
    assert calls == [{"months": 6}]


def test_backtest_dispatch_custom_months(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture(monkeypatch, "cmd_backtest")
    pipeline.main(["backtest", "--months", "3"])
    assert calls == [{"months": 3}]


def test_train_artifact_dispatch_default_holdout(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture(monkeypatch, "cmd_train_artifact")
    assert pipeline.main(["train-artifact"]) == 0
    assert calls == [{"holdout_days": 30}]


def test_train_artifact_dispatch_custom_holdout(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture(monkeypatch, "cmd_train_artifact")
    pipeline.main(["train-artifact", "--holdout-days", "45"])
    assert calls == [{"holdout_days": 45}]


def test_snapshot_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture(monkeypatch, "cmd_snapshot")
    assert pipeline.main(["snapshot"]) == 0
    assert calls == [{}]


def test_validate_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture(monkeypatch, "cmd_validate")
    assert pipeline.main(["validate"]) == 0
    assert calls == [{}]


def test_missing_command_errors() -> None:
    with pytest.raises(SystemExit):
        pipeline.main([])
