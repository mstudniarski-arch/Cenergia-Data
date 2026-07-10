-- sql/06_staging_res.sql
create or replace table staging.res_hourly as
with q as (
    select coalesce(try_strptime(dtime_utc, '%Y-%m-%d %H:%M:%S'),
                    try_strptime(dtime_utc, '%Y-%m-%d %H:%M'))
               - interval 15 minute as ts_utc,
           cast(wi as double) as wind_mw,
           cast(pv as double) as pv_mw
    from raw.pse_his_wlk_cal
)
select date_trunc('hour', ts_utc) as ts_utc,
       avg(wind_mw) as wind_mw,
       avg(pv_mw) as pv_mw
from q
where ts_utc is not null
group by 1;
