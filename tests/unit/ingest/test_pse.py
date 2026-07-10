import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from cenergia.ingest import pse

FIXTURES = Path(__file__).parents[2] / "fixtures" / "pse"


class FakeResponse:
    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise pse.requests.HTTPError(f"{self.status_code}")  # type: ignore[attr-defined]

    def json(self) -> dict[str, Any]:
        return self._payload


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())  # type: ignore[no-any-return]


def test_fetch_entity_follows_next_link(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = [_load("csdac_page1.json"), _load("csdac_page2.json")]
    calls: list[str] = []

    def fake_get(url: str, params: dict[str, str] | None = None, timeout: int = 0) -> FakeResponse:
        calls.append(url)
        return FakeResponse(pages[len(calls) - 1])

    monkeypatch.setattr(pse.requests, "get", fake_get)  # type: ignore[attr-defined]
    df = pse.fetch_entity("csdac-pln", date(2025, 10, 1), date(2025, 10, 1))
    assert len(df) == 5  # 3 from page1 + 2 from page2
    assert calls[1].startswith("https://api.raporty.pse.pl/api/csdac-pln?$after=")


def test_fetch_entity_keeps_dst_strings_unparsed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pse.requests,  # type: ignore[attr-defined]
        "get",
        lambda url, params=None, timeout=0: FakeResponse(_load("rce_dst_fallback.json")),
    )
    df = pse.fetch_entity("rce-pln", date(2024, 10, 27), date(2024, 10, 27))
    # the 02a rows survive verbatim; nothing tried to parse dtime
    assert (df["dtime"] == "2024-10-27 02a:15:00").any()
    assert df["dtime_utc"].dtype == object  # still strings — parsing is staging's job


def test_his_gen_pal_comma_decimal_cast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pse.requests,  # type: ignore[attr-defined]
        "get",
        lambda url, params=None, timeout=0: FakeResponse(_load("his_gen_pal.json")),
    )
    df = pse.fetch_entity("his-gen-pal", date(2025, 6, 1), date(2025, 6, 1))
    assert df["value"].dtype == "float64"
    assert df["value"].iloc[0] == pytest.approx(1234.56)


def test_kse_load_null_actuals_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pse.requests,  # type: ignore[attr-defined]
        "get",
        lambda url, params=None, timeout=0: FakeResponse(_load("kse_load.json")),
    )
    df = pse.fetch_entity("kse-load", date(2026, 7, 1), date(2026, 7, 2))
    assert df["load_actual"].isna().sum() == 2  # future forecast rows kept, not dropped


def test_retry_then_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = {"n": 0}

    def always_500(
        url: str, params: dict[str, str] | None = None, timeout: int = 0
    ) -> FakeResponse:
        attempts["n"] += 1
        return FakeResponse({}, status=500)

    monkeypatch.setattr(pse.requests, "get", always_500)  # type: ignore[attr-defined]
    monkeypatch.setattr(pse.time, "sleep", lambda s: None)  # type: ignore[attr-defined]
    with pytest.raises(pse.PseApiError):
        pse.fetch_entity("csdac-pln", date(2025, 1, 1), date(2025, 1, 1))
    assert attempts["n"] == 4  # 1 try + 3 retries


def test_fetch_all_writes_parquet(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        pse.requests,  # type: ignore[attr-defined]
        "get",
        lambda url, params=None, timeout=0: FakeResponse(_load("csdac_page2.json")),
    )
    out = pse.fetch_all(date(2025, 10, 1), date(2025, 10, 1), tmp_path)
    assert set(out) == set(pse.ENTITIES)
    assert out["csdac-pln"].name == "pse_csdac_pln.parquet"
    assert len(pd.read_parquet(out["csdac-pln"])) == 2
