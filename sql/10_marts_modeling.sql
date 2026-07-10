-- sql/10_marts_modeling.sql
-- One row per PSE-era delivery hour; the feature builder (Python) adds lags/calendar.
create or replace table marts.modeling_hourly as
select p.ts_utc,
       p.price_pln_mwh,
       l.load_fcst_mw,
       w.temp_c, w.wind_ms, w.ghi_wm2, w.cloud_pct,
       r.wind_mw, r.pv_mw,
       p.is_15min_regime
from staging.price_hourly p
left join staging.load_hourly l using (ts_utc)
left join staging.weather_hourly w using (ts_utc)
left join staging.res_hourly r using (ts_utc)
where p.source = 'pse';
