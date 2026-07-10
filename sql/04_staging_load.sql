-- sql/04_staging_load.sql
create or replace table staging.load_hourly as
with q as (
    select coalesce(try_strptime(dtime_utc, '%Y-%m-%d %H:%M:%S'),
                    try_strptime(dtime_utc, '%Y-%m-%d %H:%M'))
               - interval 15 minute as ts_utc,
           cast(load_actual as double) as load_mw,
           cast(load_fcst as double) as load_fcst_mw
    from raw.pse_kse_load
)
select date_trunc('hour', ts_utc) as ts_utc,
       avg(load_mw) as load_mw,          -- NULL when all quarters null (future rows)
       avg(load_fcst_mw) as load_fcst_mw
from q
where ts_utc is not null
group by 1;
