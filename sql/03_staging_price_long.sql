-- sql/03_staging_price_long.sql
-- Long hourly PLN series: Ember (EUR->PLN via NBP) before PSE data starts, PSE after.
-- is_15min_regime: delivery day 2025-10-01 Europe/Warsaw == 2025-09-30 22:00 UTC.
create or replace table staging.price_hourly as
with pse_bounds as (
    select min(ts_utc) as pse_start from staging.price_pse_hourly
),
ember_pln as (
    select e.ts_utc, e.price_eur_mwh * f.eur_pln as price_pln_mwh
    from raw.ember_pl e
    join staging.fx_daily f on f.date = cast(e.ts_utc as date)
)
select ts_utc, price_pln_mwh, 'ember' as source,
       ts_utc >= timestamp '2025-09-30 22:00:00' as is_15min_regime
from ember_pln, pse_bounds
where ts_utc < pse_start
union all
select ts_utc, price_pln_mwh, 'pse' as source,
       ts_utc >= timestamp '2025-09-30 22:00:00' as is_15min_regime
from staging.price_pse_hourly, pse_bounds;
