# ADR 0002: Plain ordered SQL files, not dbt

**Status:** accepted

## Context

The transformation layer is ten `.sql` files in `sql/`: seven staging models that clean,
UTC-normalize, and hourly-aggregate each source, and three marts (modeling table,
dashboard views, QA cross-check). dbt is the obvious default for a SQL warehouse, but its
value — a compiled DAG, Jinja templating, ref-based lineage, package management, a
generated docs site — is priced for projects with dozens to hundreds of interdependent
models and several people editing them. At ten files with a linear dependency order, that
machinery would be more surface area than the transformations themselves.

## Decision

Keep the transformations as plain SQL executed in filename order by a ~15-line Python
runner (`cenergia.warehouse`). Each file is `CREATE OR REPLACE` and therefore idempotent;
the numeric filename prefix (`01_`, `02_`, …) is the dependency order.

## Consequences

- The transformation logic is readable as-is: open the `.sql` file and it is exactly what
  runs, with no compilation step or Jinja to mentally expand.
- No dependency: the pipeline pulls in DuckDB and pandas, not a dbt install and its
  adapter, which keeps the Fly image and CI lean.
- Correctness is enforced by pytest against DuckDB in-memory (`tests/unit/sql/`) — tiny
  fixture inputs asserting exact staging/marts outputs, including the 2025-10-01
  settlement break and DST edge rows.
- **Downside:** no auto-generated lineage graph or docs site, and ordering is a naming
  convention rather than a resolved DAG. Mitigated by the small file count, the numeric
  prefixes, and the SQL tests; at ~30+ models this trade-off would flip toward dbt.
