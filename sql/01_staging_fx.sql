-- sql/01_staging_fx.sql
-- Daily EUR/PLN with calendar spine + forward fill (NBP publishes business days only).
create or replace table staging.fx_daily as
with bounds as (
    select min(cast(date as date)) as d0, max(cast(date as date)) as d1 from raw.nbp_fx
),
spine as (
    select unnest(generate_series(d0, d1 + interval 14 day, interval 1 day))::date as date
    from bounds
),
joined as (
    select s.date, f.eur_pln
    from spine s
    left join raw.nbp_fx f on cast(f.date as date) = s.date
),
filled as (
    select date,
           last_value(eur_pln ignore nulls)
               over (order by date rows between unbounded preceding and current row) as eur_pln
    from joined
)
select date, eur_pln
from filled
where eur_pln is not null;
