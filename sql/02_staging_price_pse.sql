-- sql/02_staging_price_pse.sql
-- 15-min CSDAC -> hourly. dtime_utc parsed defensively (with/without seconds),
-- shifted -15min (interval END -> START). dtime is never touched (DST '02a' strings).
create or replace table staging.price_pse_hourly as
with q as (
    select coalesce(try_strptime(dtime_utc, '%Y-%m-%d %H:%M:%S'),
                    try_strptime(dtime_utc, '%Y-%m-%d %H:%M'))
               - interval 15 minute as ts_utc,
           cast(csdac_pln as double) as price
    from raw.pse_csdac_pln
)
select date_trunc('hour', ts_utc) as ts_utc,
       avg(price) as price_pln_mwh,
       count(*) as n_quarters
from q
where ts_utc is not null
group by 1;
