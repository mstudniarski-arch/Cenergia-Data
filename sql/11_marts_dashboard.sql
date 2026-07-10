-- sql/11_marts_dashboard.sql
create or replace table marts.price_daily as
select cast(ts_utc as date) as date,
       source,
       avg(price_pln_mwh) as avg_price,
       min(price_pln_mwh) as min_price,
       max(price_pln_mwh) as max_price
from staging.price_hourly
group by 1, 2;

create or replace table marts.typical_shape as
with local_ts as (
    select timezone('Europe/Warsaw', ts_utc::timestamptz)::timestamp as ts_local,
           price_pln_mwh
    from staging.price_hourly
)
select case when extract(month from ts_local) in (12, 1, 2) then 'winter'
            when extract(month from ts_local) in (3, 4, 5) then 'spring'
            when extract(month from ts_local) in (6, 7, 8) then 'summer'
            else 'autumn' end as season,
       extract(year from ts_local) as year,
       extract(hour from ts_local) as hour_local,
       avg(price_pln_mwh) as avg_price
from local_ts
group by 1, 2, 3;

create or replace table marts.merit_order as
select p.ts_utc,
       p.price_pln_mwh,
       r.wind_mw + r.pv_mw as res_mw,
       l.load_mw,
       (r.wind_mw + r.pv_mw) / nullif(l.load_mw, 0) as res_share
from staging.price_hourly p
join staging.res_hourly r using (ts_utc)
join staging.load_hourly l using (ts_utc)
where p.source = 'pse' and l.load_mw is not null;
