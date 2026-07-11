"""Price-drivers page: the merit-order effect (renewables share vs price)
and the last 60 days of price alongside wind/PV output.

Pure render function: all data comes from the already-loaded `Snapshot`, no
I/O happens here.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from cenergia.dashboard.data_access import Snapshot
from cenergia.dashboard.views import _palette as pal

_N_BINS = 20


def render(snap: Snapshot) -> None:
    st.header("Price drivers")

    st.plotly_chart(_merit_order_figure(snap.merit_order), use_container_width=True)
    st.plotly_chart(_recent_hourly_figure(snap.recent_hourly), use_container_width=True)


def _merit_order_figure(merit_order: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scattergl(
            x=merit_order["res_share"],
            y=merit_order["price_pln_mwh"],
            mode="markers",
            marker={"size": 4, "color": pal.BASELINE, "opacity": 0.35},
            name="Hourly observation",
            hovertemplate="res share %{x:.0%}: %{y:,.0f} PLN/MWh<extra></extra>",
        )
    )

    trend = _binned_trend(merit_order, "res_share", "price_pln_mwh", _N_BINS)
    fig.add_trace(
        go.Scatter(
            x=trend["res_share"],
            y=trend["price_pln_mwh"],
            mode="lines+markers",
            line={"color": pal.RED, "width": 2},
            marker={"size": 5, "color": pal.RED},
            name="Binned mean",
        )
    )

    fig.update_layout(
        title="Merit-order effect: renewables share vs price",
        xaxis_title="Wind + solar share of load",
        xaxis_tickformat=".0%",
        yaxis_title="Price (PLN/MWh)",
        plot_bgcolor=pal.PLOT_BGCOLOR,
        font={"color": pal.FONT_COLOR},
        margin={"l": 40, "r": 20, "t": 50, "b": 40},
        showlegend=False,
    )
    return fig


def _binned_trend(df: pd.DataFrame, x_col: str, y_col: str, n_bins: int) -> pd.DataFrame:
    """Mean `y_col` within `n_bins` equal-width bins of `x_col`, sorted by
    bin center — a coarse trend line over a scatter too dense to read raw.
    """
    valid = df[[x_col, y_col]].dropna()
    if valid.empty:
        return pd.DataFrame({x_col: [], y_col: []})
    bins = min(n_bins, valid[x_col].nunique()) or 1
    cut = pd.cut(valid[x_col], bins=bins)
    grouped = valid.groupby(cut, observed=True).agg({x_col: "mean", y_col: "mean"})
    return grouped.reset_index(drop=True).sort_values(x_col)


def _recent_hourly_figure(recent_hourly: pd.DataFrame) -> go.Figure:
    df = recent_hourly.sort_values("ts_utc")
    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=df["ts_utc"],
            y=df["wind_mw"],
            mode="lines",
            line={"width": 0},
            fill="tozeroy",
            fillcolor="rgba(27,175,122,0.35)",
            name="Wind (MW)",
            yaxis="y2",
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["ts_utc"],
            y=df["wind_mw"] + df["pv_mw"],
            mode="lines",
            line={"width": 0.5, "color": pal.AMBER},
            fill="tonexty",
            fillcolor="rgba(237,161,0,0.35)",
            name="Wind + PV (MW)",
            yaxis="y2",
            hovertemplate="%{x|%Y-%m-%d %H:%M}: %{y:,.0f} MW<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["ts_utc"],
            y=df["price_pln_mwh"],
            mode="lines",
            line={"color": pal.RED, "width": 1.4},
            name="Price (PLN/MWh)",
            hovertemplate="%{x|%Y-%m-%d %H:%M}: %{y:,.0f} PLN/MWh<extra></extra>",
        )
    )

    fig.update_layout(
        title="Last 60 days: price vs wind/PV output",
        xaxis_title="Time (UTC)",
        yaxis={"title": "Price (PLN/MWh)"},
        yaxis2={"title": "Wind + PV (MW)", "overlaying": "y", "side": "right"},
        plot_bgcolor=pal.PLOT_BGCOLOR,
        font={"color": pal.FONT_COLOR},
        margin={"l": 40, "r": 40, "t": 50, "b": 40},
        legend={"orientation": "h", "y": -0.2},
    )
    return fig
