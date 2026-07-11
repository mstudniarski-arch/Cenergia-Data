# ADR 0001: DuckDB as the analytical warehouse, not Postgres

**Status:** accepted

## Context

Cenergia is a single-writer batch pipeline: ingest clients pull from four APIs, a
loader writes raw tables, and ordered SQL builds staging and marts. The workload is
analytical (scan-heavy aggregations over ~100k hourly rows and a wider PSE-era feature
frame), never transactional, and has exactly one process touching the store at a time.
The whole thing also has to run in CI on a fresh runner and inside a 512 MB Fly machine
with no attached database. A client/server RDBMS would mean provisioning, credentials,
and a network hop for what is fundamentally a local columnar scan.

## Decision

Use DuckDB as a single embedded file (`data/warehouse.duckdb`). Load raw parquet via
`read_parquet`, run the `sql/` files against it, and read marts back into pandas and the
dashboard. No server, no ORM, no connection pool.

## Consequences

- Zero infrastructure: the warehouse is a file. CI, local dev, and the Fly image all use
  the identical engine with nothing to provision or authenticate against.
- Columnar scans over the full history are fast enough that the notebooks compute every
  statistic live from the warehouse instead of caching hand-typed numbers.
- Reproducibility is a `git clone` away — the snapshot marts ship as committed parquet,
  so the dashboard runs without ever rebuilding the DB.
- **Downside:** DuckDB is single-writer and offers no concurrent-write story. That is a
  non-issue for a batch pipeline, but it rules DuckDB out for any future online-serving
  path with concurrent writers — that would be the moment to reach for Postgres.
