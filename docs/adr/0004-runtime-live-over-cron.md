# ADR 0004: Runtime-live forecast, not a scheduled cron job

**Status:** accepted

## Context

The dashboard's third page shows tomorrow's forecast and a trailing 30-day
pseudo-out-of-sample accuracy view. Both need a recent window of PSE prices and Open-Meteo
weather, run through the committed model artifact. The conventional design is a scheduler
(cron/Airflow) that refreshes a materialized table on a timer. But the upstream APIs are
keyless and free, the app is deployed scale-to-zero on Fly with no always-on worker, and a
scheduled job introduces its own failure mode: a silently stale table when a run fails
unnoticed, plus infrastructure to babysit that has nothing to do with the analysis.

## Decision

Compute the live forecast at request time. Page 3 pulls the recent window from PSE and
Open-Meteo on demand, caches it with Streamlit's `st.cache_data(ttl=3600)`, and predicts
with the committed artifact. If any API call fails, serve the bundled snapshot marts
(committed parquet) behind a "data as of &lt;date&gt;" banner — graceful degradation, never a
broken page.

## Consequences

- Nothing to schedule and nothing to go stale: there is no cron job, no worker, and no
  materialized table that can silently fall behind.
- The live path reuses the exact same ingest clients and feature builder as the batch
  pipeline, so there is no second copy of the fetch-and-featurize logic to keep in sync.
- The snapshot fallback means the app still renders a complete, honest page even during an
  upstream outage — the failure is visible and labeled, not hidden.
- **Downside:** the first uncached visitor after the hourly TTL expires pays a few seconds
  of API latency while the window is fetched (on top of the scale-to-zero cold start).
  Acceptable for a portfolio dashboard; a high-traffic service would want a warm cache or a
  background refresh instead.
