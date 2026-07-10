-- sql/05_staging_gen.sql
-- ENTSO-E fuel codes -> readable names; unmapped codes pooled as 'other'.
create or replace table staging.gen_mix_hourly as
with q as (
    select coalesce(try_strptime(dtime_utc, '%Y-%m-%d %H:%M:%S'),
                    try_strptime(dtime_utc, '%Y-%m-%d %H:%M'))
               - interval 15 minute as ts_utc,
           case alias_entsoe
               when 'B02' then 'lignite'
               when 'B05' then 'hard_coal'
               when 'B04' then 'gas'
               when 'B16' then 'solar'
               when 'B19' then 'wind_onshore'
               when 'B01' then 'biomass'
               when 'B10' then 'pumped_storage'
               when 'B11' then 'hydro_ror'
               when 'B12' then 'hydro_res'
               else 'other'
           end as fuel,
           cast(value as double) as gen_mw
    from raw.pse_his_gen_pal
),
per_quarter as (
    select ts_utc, fuel, sum(gen_mw) as gen_mw from q where ts_utc is not null group by 1, 2
)
select date_trunc('hour', ts_utc) as ts_utc, fuel, avg(gen_mw) as gen_mw
from per_quarter
group by 1, 2;
