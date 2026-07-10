"""PSE open-data API client (api.raporty.pse.pl, v2).

Raw-shaped output: no timestamp parsing here (fall-back DST rows contain
literal '02a:15:00' in dtime — only staging SQL touches time, via dtime_utc).
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests

PSE_BASE = "https://api.raporty.pse.pl/api"
ENTITIES: tuple[str, ...] = ("csdac-pln", "rce-pln", "kse-load", "his-gen-pal", "his-wlk-cal")
_TIMEOUT = 60
_PAGE_SIZE = 50_000
_CHUNK_DAYS = 90
_RETRIES = 3


class PseApiError(RuntimeError):
    """The PSE API failed after retries."""


def _get(url: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    last: Exception | None = None
    for attempt in range(_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, timeout=_TIMEOUT)
            resp.raise_for_status()
            return resp.json()  # type: ignore[no-any-return]
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
            last = exc
            if attempt < _RETRIES:
                time.sleep(2**attempt)
    raise PseApiError(f"GET {url} failed after {_RETRIES + 1} attempts") from last


def _fetch_window(entity: str, start: date, end: date) -> list[dict[str, Any]]:
    start_iso = start.isoformat()
    end_iso = end.isoformat()
    params = {
        "$filter": f"business_date ge '{start_iso}' and business_date le '{end_iso}'",
        "$first": str(_PAGE_SIZE),
    }
    payload = _get(f"{PSE_BASE}/{entity}", params=params)
    rows: list[dict[str, Any]] = list(payload.get("value", []))
    while next_link := payload.get("nextLink"):
        payload = _get(str(next_link))
        rows.extend(payload.get("value", []))
    return rows


def fetch_entity(entity: str, start: date, end: date) -> pd.DataFrame:
    """All rows with business_date in [start, end], chunked politely."""
    rows: list[dict[str, Any]] = []
    chunk_start = start
    while chunk_start <= end:
        chunk_end = min(chunk_start + timedelta(days=_CHUNK_DAYS - 1), end)
        rows.extend(_fetch_window(entity, chunk_start, chunk_end))
        chunk_start = chunk_end + timedelta(days=1)
    df = pd.DataFrame(rows)
    # Ensure string/object columns stay as object dtype (pandas 2.0+ compatibility)
    for col in df.columns:
        if not pd.api.types.is_numeric_dtype(df[col]):
            df[col] = df[col].astype(object)
    if entity == "his-gen-pal" and not df.empty and "value" in df.columns:
        df["value"] = df["value"].astype(str).str.replace(",", ".", regex=False).astype("float64")
    return df


def fetch_all(start: date, end: date, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for entity in ENTITIES:
        path = out_dir / f"pse_{entity.replace('-', '_')}.parquet"
        fetch_entity(entity, start, end).to_parquet(path, index=False)
        written[entity] = path
    return written
