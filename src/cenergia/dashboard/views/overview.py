"""Market overview page: the 11-year price history with regime annotations,
the typical daily shape by season, and the year-over-year price range — the
first three things a viewer should see about the Polish day-ahead market.

Pure render function: all data comes from the already-loaded `Snapshot`, no
I/O happens here.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from cenergia.dashboard.data_access import Snapshot
from cenergia.dashboard.views import _palette as pal
from cenergia.features.matrix import BREAK_TS_UTC

# Ember and PSE never overlap except on the single hand-off day; prefer PSE
# there since it's the native-PLN source of record going forward.
_SOURCE_PRIORITY = {"pse": 0, "ember": 1}
_SEASON_ORDER = ("winter", "spring", "summer", "autumn")


def render(snap: Snapshot) -> None:
    st.header("Market overview")
    st.caption(f"Polish day-ahead price, PLN/MWh — snapshot as of {snap.as_of:%Y-%m-%d}")

    combined = _combine_price_daily(snap.price_daily)

    st.plotly_chart(_price_history_figure(combined), use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(_seasonal_heatmap_figure(snap.typical_shape), use_container_width=True)
    with col2:
        st.plotly_chart(_yearly_band_figure(combined), use_container_width=True)


def _combine_price_daily(price_daily: pd.DataFrame) -> pd.DataFrame:
    """Collapse the ember/pse split into one row per date."""
    out = price_daily.assign(_priority=price_daily["source"].map(_SOURCE_PRIORITY))
    out = out.sort_values(["date", "_priority"]).drop_duplicates("date", keep="first")
    return out.drop(columns="_priority").sort_values("date").reset_index(drop=True)


def _price_history_figure(combined: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=combined["date"],
            y=combined["avg_price"],
            mode="lines",
            line={"color": pal.BLUE, "width": 1.2},
            name="Daily avg price",
            hovertemplate="%{x|%Y-%m-%d}: %{y:,.0f} PLN/MWh<extra></extra>",
        )
    )

    y_max = float(combined["avg_price"].max()) if not combined.empty else 1.0

    peak_2022 = combined[combined["date"].dt.year == 2022]
    if not peak_2022.empty:
        peak_row = peak_2022.loc[peak_2022["avg_price"].idxmax()]
        fig.add_vrect(
            x0="2022-01-01",
            x1="2022-12-31",
            fillcolor=pal.ORANGE,
            opacity=0.10,
            line_width=0,
        )
        fig.add_annotation(
            x=peak_row["date"],
            y=peak_row["avg_price"],
            text=(
                f"2022 energy crisis<br>peak {peak_row['date']:%b %Y}: "
                f"{peak_row['avg_price']:,.0f} PLN/MWh"
            ),
            showarrow=True,
            arrowhead=2,
            arrowcolor=pal.INK_MUTED,
            font={"color": pal.INK_SECONDARY, "size": 11},
            ax=0,
            ay=-40,
        )

    negative_dates = combined.loc[combined["min_price"] < 0, "date"]
    if not negative_dates.empty:
        first_negative = negative_dates.min()
        fig.add_vline(x=first_negative, line={"color": pal.RED, "width": 1, "dash": "dot"})
        fig.add_annotation(
            x=first_negative,
            y=y_max * 0.35,
            text=f"first negative-price day<br>{first_negative:%Y-%m-%d}",
            showarrow=False,
            font={"color": pal.RED, "size": 11},
            xanchor="left",
        )

    break_date = pd.Timestamp(BREAK_TS_UTC.date())
    fig.add_vline(x=break_date, line={"color": pal.RED, "width": 1.4, "dash": "dash"})
    fig.add_annotation(
        x=break_date,
        y=y_max * 0.85,
        text="15-min settlement starts",
        showarrow=False,
        font={"color": pal.RED, "size": 11},
        xanchor="right",
    )

    fig.update_layout(
        title="11 years of Polish day-ahead prices",
        xaxis_title="Date",
        yaxis_title="Avg daily price (PLN/MWh)",
        plot_bgcolor=pal.PLOT_BGCOLOR,
        font={"color": pal.FONT_COLOR},
        margin={"l": 40, "r": 20, "t": 50, "b": 40},
        showlegend=False,
    )
    return fig


def _seasonal_heatmap_figure(typical_shape: pd.DataFrame) -> go.Figure:
    pivot = (
        typical_shape.groupby(["season", "hour_local"])["avg_price"]
        .mean()
        .unstack("hour_local")
        .reindex(_SEASON_ORDER)
    )
    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.to_numpy(),
            x=pivot.columns.to_numpy(),
            y=pivot.index.to_numpy(),
            colorscale=pal.SEQUENTIAL_SCALE,
            colorbar={"title": "PLN/MWh"},
            hovertemplate="season=%{y} hour=%{x}: %{z:,.0f} PLN/MWh<extra></extra>",
        )
    )
    fig.update_layout(
        title="Typical daily shape by season",
        xaxis_title="Hour of day (local)",
        yaxis_title="Season",
        plot_bgcolor=pal.PLOT_BGCOLOR,
        font={"color": pal.FONT_COLOR},
        margin={"l": 40, "r": 20, "t": 50, "b": 40},
    )
    return fig


def _yearly_band_figure(combined: pd.DataFrame) -> go.Figure:
    yearly = (
        combined.assign(year=combined["date"].dt.year)
        .groupby("year")
        .agg(avg=("avg_price", "mean"), lo=("min_price", "min"), hi=("max_price", "max"))
        .reset_index()
    )

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=yearly["year"],
            y=yearly["hi"],
            mode="lines",
            line={"width": 0},
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=yearly["year"],
            y=yearly["lo"],
            mode="lines",
            line={"width": 0},
            fill="tonexty",
            fillcolor="rgba(42,120,214,0.15)",
            showlegend=False,
            hoverinfo="skip",
            name="Min-max range",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=yearly["year"],
            y=yearly["avg"],
            mode="lines+markers",
            line={"color": pal.BLUE, "width": 1.6},
            marker={"size": 5},
            name="Yearly avg",
            hovertemplate="%{x}: avg %{y:,.0f} PLN/MWh<extra></extra>",
        )
    )
    fig.update_layout(
        title="Yearly price range (min-max band) and average",
        xaxis_title="Year",
        yaxis_title="Price (PLN/MWh)",
        plot_bgcolor=pal.PLOT_BGCOLOR,
        font={"color": pal.FONT_COLOR},
        margin={"l": 40, "r": 20, "t": 50, "b": 40},
        showlegend=False,
    )
    return fig
