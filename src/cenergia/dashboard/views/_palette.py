"""Shared chart palette, kept in lockstep with the muted, colorblind-checked
categorical palette defined in `notebooks/01-market-eda.ipynb` /
`notebooks/02-price-drivers.ipynb`, so a color means the same thing in the
notebooks and the dashboard. Not importable from the notebooks themselves
(they're `.ipynb`, not package code), so the hex values are duplicated here
verbatim rather than shared by import.
"""

from __future__ import annotations

BLUE = "#2a78d6"
AQUA = "#1baf7a"
AMBER = "#eda100"
GREEN = "#008300"
VIOLET = "#4a3aa7"
RED = "#d03b3b"
MAGENTA = "#e87ba4"
ORANGE = "#eb6834"

INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"

# Sequential scale for heatmaps: muted paper -> amber -> red, echoing the
# ORANGE/RED intensity story used for the price regimes in the notebooks.
SEQUENTIAL_SCALE: list[list[float | str]] = [
    [0.0, GRID],
    [0.5, AMBER],
    [1.0, RED],
]

PLOT_BGCOLOR = "white"
FONT_COLOR = INK_SECONDARY
