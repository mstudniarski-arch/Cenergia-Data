import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from cenergia.ingest import nbp

FIXTURES = Path(__file__).parents[2] / "fixtures" / "nbp"


class FakeResponse:
    def __init__(self, payload: dict[str, Any] | None, status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise nbp.requests.HTTPError(f"{self.status_code}")  # type: ignore[attr-defined]

    def json(self) -> dict[str, Any]:
        assert self._payload is not None
        return self._payload


def test_fetch_chunks_at_90_days(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.loads((FIXTURES / "rates_chunk.json").read_text())
    windows: list[str] = []

    def fake_get(url: str, timeout: int = 0) -> FakeResponse:
        windows.append(url)
        return FakeResponse(payload)

    monkeypatch.setattr(nbp.requests, "get", fake_get)  # type: ignore[attr-defined]
    df = nbp.fetch_eur_pln(date(2015, 1, 1), date(2015, 7, 20))  # 201 days -> 3 chunks
    assert len(windows) == 3
    assert df.columns.tolist() == ["date", "eur_pln"]
    assert len(df) == 6  # 2 rows per chunk
    assert str(df["date"].dtype) == "datetime64[ns]"  # warehouse convention


def test_404_empty_range_tolerated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        nbp.requests,  # type: ignore[attr-defined]
        "get",
        lambda url, timeout=0: FakeResponse(None, status=404),
    )
    df = nbp.fetch_eur_pln(date(2015, 1, 3), date(2015, 1, 4))  # weekend-only range
    assert df.empty


def test_connection_error_retries_then_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = {"n": 0}

    def always_fail(url: str, timeout: int = 0) -> FakeResponse:
        attempts["n"] += 1
        raise nbp.requests.ConnectionError("network down")  # type: ignore[attr-defined]

    monkeypatch.setattr(nbp.requests, "get", always_fail)  # type: ignore[attr-defined]
    monkeypatch.setattr(nbp.time, "sleep", lambda s: None)  # type: ignore[attr-defined]
    with pytest.raises(nbp.NbpApiError):
        nbp.fetch_eur_pln(date(2015, 1, 1), date(2015, 1, 2))
    assert attempts["n"] == 4  # 1 try + 3 retries
