"""Dashboard entry point: `streamlit run src/cenergia/dashboard/app.py`
(or `make dashboard`).

Loads the snapshot once, then dispatches to a pure `render(snap)` view per
sidebar page. No data loading happens inside the views themselves.

The forecast page imports `cenergia.dashboard.live` lazily (inside the
`else` branch below, not at module scope) so that AppTest runs of the other
two pages never import `requests`/pull live PSE/Open-Meteo data.
"""

from __future__ import annotations

import streamlit as st

from cenergia.dashboard import data_access
from cenergia.dashboard.views import drivers, overview

_PAGES = ("Market overview", "Price drivers", "Tomorrow's forecast")


def main() -> None:
    st.set_page_config(
        page_title="Cenergia — Polish power market",
        page_icon="⚡",
        layout="wide",
    )

    snap = data_access.load_snapshot()

    st.sidebar.title("Cenergia")
    st.sidebar.caption("Polish day-ahead electricity market analytics")
    page = st.sidebar.radio("View", _PAGES)
    st.sidebar.caption(f"Snapshot as of {snap.as_of:%Y-%m-%d}")

    if page == "Market overview":
        overview.render(snap)
    elif page == "Price drivers":
        drivers.render(snap)
    else:
        from cenergia.dashboard import live
        from cenergia.dashboard.views import forecast

        forecast.render(live.get_live_forecast())


main()
