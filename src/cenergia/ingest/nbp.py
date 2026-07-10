"""NBP table-A EUR/PLN daily mid rates. Ranges chunked to <=90 days (API limit 93)."""

from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Any

import pandas as pd
import requests

_URL = "https://api.nbp.pl/api/exchangerates/rates/a/eur/{start}/{end}/?format=json"
_TIMEOUT = 60
_CHUNK_DAYS = 90
_RETRIES = 3


class NbpApiError(RuntimeError):
    """The NBP API failed after retries."""


def _get_chunk(start: date, end: date) -> list[dict[str, Any]]:
    url = _URL.format(start=start.isoformat(), end=end.isoformat())
    last: Exception | None = None
    for attempt in range(_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=_TIMEOUT)
            if resp.status_code == 404:  # no business days in range
                return []
            resp.raise_for_status()
            return list(resp.json()["rates"])
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
            last = exc
            if attempt < _RETRIES:
                time.sleep(2**attempt)
    raise NbpApiError(f"GET {url} failed after {_RETRIES + 1} attempts") from last


def fetch_eur_pln(start: date, end: date) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    chunk_start = start
    while chunk_start <= end:
        chunk_end = min(chunk_start + timedelta(days=_CHUNK_DAYS - 1), end)
        rows.extend(_get_chunk(chunk_start, chunk_end))
        chunk_start = chunk_end + timedelta(days=1)
    if not rows:
        return pd.DataFrame(
            {"date": pd.Series(dtype="datetime64[ns]"), "eur_pln": pd.Series(dtype="float64")}
        )
    df = pd.DataFrame(rows)[["effectiveDate", "mid"]].rename(
        columns={"effectiveDate": "date", "mid": "eur_pln"}
    )
    df["date"] = pd.to_datetime(df["date"])
    df["eur_pln"] = df["eur_pln"].astype("float64")
    return df.sort_values("date").reset_index(drop=True)
