"""Tomorrow's forecast page: the dashboard's runtime-live "wow feature" — a
real next-day price forecast computed at request time (see `live.py`), shown
next to the trailing 30 days so a viewer can judge the model's recent track
record, not just trust a single number.

Pure render function: `live.py` does the pull/build/predict, this module
only draws from the already-computed `LiveForecast`.
"""

from __future__ import annotations

from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from cenergia.dashboard.live import LiveForecast
from cenergia.dashboard.views import _palette as pal
from cenergia.models.metrics import mae

# PSE delivery days are Europe/Warsaw *local* calendar days, not UTC calendar
# days — a naive `made_at_utc.normalize() + 1 day` boundary silently drops
# the first 1-2 hours of "tomorrow" (and includes hours from the day after)
# whenever Warsaw's UTC offset isn't zero, i.e. always. Caught by the manual
# live check (22/24 rows), not by unit tests with dense synthetic data.
_WARSAW_TZ = "Europe/Warsaw"


def render(live: LiveForecast) -> None:
    st.header("Tomorrow's forecast")

    if live.degraded:
        # frame can be empty if the snapshot fallback itself failed too
        # (live._get_live_forecast_uncached's double-failure path) — max()
        # is NaT then, so name the snapshot date only when there is one.
        ts_max = live.frame["ts_utc"].max()
        as_of = f"{ts_max:%Y-%m-%d %H:%M} UTC" if pd.notna(ts_max) else "unavailable"
        st.warning(
            "Live PSE/weather data is unavailable right now — showing the last known "
            f"snapshot instead (as of {as_of}). No live forecast to "
            "show until the next successful refresh."
        )

    tomorrow = _tomorrow_slice(live.frame, live.made_at_utc)

    col1, col2 = st.columns([3, 1])
    with col1:
        if tomorrow.empty:
            st.info("Tomorrow's day-ahead price isn't available yet — check back later today.")
        else:
            st.plotly_chart(_tomorrow_figure(tomorrow), use_container_width=True)
    with col2:
        trailing_mae = _trailing_mae(live.frame)
        st.metric(
            "Trailing MAE (30d)",
            f"{trailing_mae:,.1f} PLN/MWh" if trailing_mae is not None else "n/a",
        )

    st.plotly_chart(_trailing_figure(live.frame), use_container_width=True)

    st.caption(f"Model trained on data through {live.train_end}; later days are out-of-sample.")


def _tomorrow_slice(frame: pd.DataFrame, made_at_utc: pd.Timestamp) -> pd.DataFrame:
    start, end = _tomorrow_window_utc(made_at_utc)
    mask = (frame["ts_utc"] >= start) & (frame["ts_utc"] < end)
    return frame.loc[mask].sort_values("ts_utc")


def _tomorrow_window_utc(made_at_utc: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    """[start, end) UTC bounds of the Warsaw-local calendar day after
    `made_at_utc` — 23/24/25 hours across a DST transition, 24 otherwise.

    Every day-step here is *calendar* arithmetic on plain dates, localized to
    midnight only afterwards. Adding `pd.Timedelta(days=1)` to a tz-aware
    timestamp instead would be absolute 24-hour arithmetic, which goes wrong
    twice near DST transitions: `start_local + 1 day` overshoots the next
    local midnight on the 23-hour spring-forward day (leaking an hour of the
    day after into the window) and undershoots it on the 25-hour fall-back
    day (dropping the day's last hour); and `(local_now + 1 day).date()`
    evaluated in the last local hour before a spring-forward day skips
    "tomorrow" entirely. Pinned by the parametrized DST cases in
    tests/unit/dashboard/test_live.py.
    """
    local_now = made_at_utc.tz_localize("UTC").tz_convert(_WARSAW_TZ)
    tomorrow_local_date = local_now.date() + timedelta(days=1)
    start_local = pd.Timestamp(tomorrow_local_date, tz=_WARSAW_TZ)
    end_local = pd.Timestamp(tomorrow_local_date + timedelta(days=1), tz=_WARSAW_TZ)
    start_utc = start_local.tz_convert("UTC").tz_localize(None)
    end_utc = end_local.tz_convert("UTC").tz_localize(None)
    return start_utc, end_utc


def _trailing_mae(frame: pd.DataFrame) -> float | None:
    valid = frame.dropna(subset=["y_actual", "y_pred"])
    if valid.empty:
        return None
    return mae(valid["y_actual"], valid["y_pred"])


def _tomorrow_figure(tomorrow: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=tomorrow["ts_utc"],
            y=tomorrow["y_pred"],
            marker={"color": pal.BLUE},
            name="Forecast",
            hovertemplate="%{x|%H:00} UTC: %{y:,.0f} PLN/MWh<extra></extra>",
        )
    )
    known = tomorrow.dropna(subset=["y_actual"])
    if not known.empty:
        fig.add_trace(
            go.Scatter(
                x=known["ts_utc"],
                y=known["y_actual"],
                mode="lines+markers",
                line={"color": pal.RED, "width": 2},
                marker={"size": 6, "color": pal.RED},
                name="Actual (published)",
                hovertemplate="%{x|%H:00} UTC: %{y:,.0f} PLN/MWh<extra></extra>",
            )
        )
    fig.update_layout(
        title="Tomorrow's 24-hour forecast",
        xaxis_title="Hour (UTC)",
        yaxis_title="Price (PLN/MWh)",
        plot_bgcolor=pal.PLOT_BGCOLOR,
        font={"color": pal.FONT_COLOR},
        margin={"l": 40, "r": 20, "t": 50, "b": 40},
        legend={"orientation": "h", "y": -0.2},
    )
    return fig


def _trailing_figure(frame: pd.DataFrame) -> go.Figure:
    df = frame.sort_values("ts_utc")
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["ts_utc"],
            y=df["y_actual"],
            mode="lines",
            line={"color": pal.INK_MUTED, "width": 1.2},
            name="Actual",
            hovertemplate="%{x|%Y-%m-%d %H:%M}: %{y:,.0f} PLN/MWh<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["ts_utc"],
            y=df["y_pred"],
            mode="lines",
            line={"color": pal.BLUE, "width": 1.2},
            name="Model prediction",
            hovertemplate="%{x|%Y-%m-%d %H:%M}: %{y:,.0f} PLN/MWh<extra></extra>",
        )
    )
    fig.update_layout(
        title="Trailing 30 days: predicted vs actual",
        xaxis_title="Time (UTC)",
        yaxis_title="Price (PLN/MWh)",
        plot_bgcolor=pal.PLOT_BGCOLOR,
        font={"color": pal.FONT_COLOR},
        margin={"l": 40, "r": 20, "t": 50, "b": 40},
        legend={"orientation": "h", "y": -0.2},
    )
    return fig
