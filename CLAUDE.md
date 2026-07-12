# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

End-to-end data project on the Polish electricity market: four public APIs → a DuckDB
warehouse → a leakage-guarded feature matrix → a walk-forward day-ahead price forecaster →
three narrative notebooks + a live Streamlit dashboard. Python 3.13, `uv`, `mypy --strict`.
Deployed on Fly.io (scale-to-zero). Design rationale for the non-obvious calls lives in
`docs/adr/`; the reader-facing story is in `README.md`.

## Commands

```bash
uv sync --all-groups                 # environment (run everything through `uv run`)

# Quality gate — mirrors CI exactly; run all four before pushing:
uv run ruff check .
uv run ruff format --check .         # CI enforces formatting — this bites if you skip it
uv run mypy src tests
uv run pytest -q                     # 98 tests
uv run pytest tests/unit/features/test_leakage.py -q   # single file/test

# Data pipeline (DuckDB warehouse at data/warehouse.duckdb, gitignored):
uv run python -m cenergia.pipeline ingest --start 2024-06-14   # fetch raw from the 4 APIs
uv run python -m cenergia.pipeline transform                   # run sql/ staging → marts
uv run python -m cenergia.pipeline backtest --months 6         # walk-forward → results/
uv run python -m cenergia.pipeline train-artifact --holdout-days 30
uv run python -m cenergia.pipeline snapshot                    # dashboard parquet snapshot
uv run python -m cenergia.pipeline validate                    # real-data threshold checks
# (Makefile wraps each of these: make test / lint / ingest / transform / backtest / snapshot)

uv run streamlit run src/cenergia/dashboard/app.py            # dashboard locally
```

## Architecture

```
ingest/ (4 keyless API clients) → data/raw/ → warehouse (DuckDB) → features/ → models/ → dashboard/
  pse · ember · nbp · openmeteo              raw.* → staging.* → marts.*   matrix   lgbm      Streamlit
```

- **Ingest** (`src/cenergia/ingest/`): four clients — `pse`, `ember`, `nbp`, `openmeteo`.
  All are **keyless public APIs** — there are no API keys anywhere in this project; don't add
  key-based auth. Each client has recorded-fixture tests (`tests/fixtures/`) pinning its
  documented quirks (DST rows, comma-decimal values, unit conversions) — preserve those.
- **Warehouse** (`src/cenergia/warehouse/`): a single DuckDB file. Transforms are **plain
  ordered `.sql` files in `sql/`** (staging `01–07`, marts `10–12`), run top-to-bottom by a
  ~15-line Python runner — not dbt (see ADR 0002).
- **Features** (`src/cenergia/features/matrix.py`): builds the modeling matrix under a
  **leakage cutoff** — only data available at day-ahead prediction time may enter a row. The
  rule is enforced by `tests/unit/features/test_leakage.py`, not just a comment.
- **Models** (`src/cenergia/models/`): naive + seasonal-naive baselines and a deterministic
  LightGBM wrapper, evaluated by `backtest.py` (walk-forward, monthly refit). Output is a
  committed `results/backtest.csv` + a text model artifact — no MLflow (ADR 0003).
- **Dashboard** (`src/cenergia/dashboard/`): Streamlit. Reads a parquet **snapshot** for the
  historical pages and computes tomorrow's forecast **live at request time** (ADR 0004).

## Conventions

- **TDD**, small commits, conventional messages. Comments/commits in English.
- `ruff` (line-length 100) + `mypy --strict` over `src` and `tests` — both are CI gates.
- The model trains **only on the PSE era (2024-06 → now)**, where the full covariate set
  exists. Ember supplies the eleven-year analyst history (notebooks 01/02) but not model
  features — a cross-source QA check confirms Ember ≈ PSE at r = 0.99999 on the overlap.
- Notebooks (`01`-eda, `02`-drivers, `03`-forecasting) are narrative deliverables with
  committed outputs; every figure/number is computed from the warehouse or committed results.

## Gotchas

- **`CENERGIA_SNAPSHOT_DIR`** — the dashboard resolves its snapshot directory as: explicit arg
  > this env var > `paths.SNAPSHOT`. On Fly it points at the baked-in snapshot. It is a path
  override, **not** a credential.
- **rMAE is a ratio — always read it next to the raw MAE it's built from.** Feb 2026 shows
  rMAE > 1 not because the model degraded (its MAE stays in-band) but because the naive
  baseline had an unusually easy month, collapsing the denominator. Don't report rMAE alone.
- **Scale-to-zero on Fly**: the first request cold-starts the machine (~6 s) — not a bug. The
  live forecast panel only populates after PSE publishes tomorrow's day-ahead auction (early
  afternoon CET); before that the page shows the trailing-accuracy view.
- **CI runs with no secrets** and no network to the real APIs — tests use recorded fixtures.
