# ADR 0003: LightGBM as the modeling ceiling, a committed CSV instead of MLflow

**Status:** accepted

## Context

The forecasting target is 24 hourly day-ahead prices with tabular features — price lags,
a load forecast, weather forecasts, and calendar terms. The electricity-price-forecasting
literature is consistent that on this kind of tabular problem an honestly evaluated
gradient-boosted tree is a strong, hard-to-beat baseline, and that the choice of honest
baselines and leakage discipline matters far more than model architecture. Deep sequence
models add training complexity and a much larger serving footprint for gains that this
~2-year covariate history cannot reliably support. Separately, the project runs a single
walk-forward backtest producing one results table — not a sweep of hundreds of runs.

## Decision

Use LightGBM as the single learned model, benchmarked against naive and seasonal-naive
baselines with a walk-forward backtest. Track results as a committed `results/backtest.csv`
(plus per-hour CSV and a predictions parquet) — no MLflow, no experiment-tracking server.

## Consequences

- The comparison that matters is in version control: the backtest numbers live in the git
  history next to the code that produced them, diffable across commits.
- One trained artifact (`data/model_lgbm.txt`, LightGBM's text format) is committed and
  reused verbatim by both the backtest notebook and the live dashboard — one source of
  truth, no training at serve time.
- Onboarding is trivial: there is no tracking server to stand up, authenticate, or keep
  running for anyone to reproduce the result.
- **Downside:** no run-comparison UI, parameter-sweep dashboard, or artifact registry. At
  this scale a CSV is enough; a project doing systematic hyperparameter search across many
  runs would outgrow it and want MLflow (or similar) back.
