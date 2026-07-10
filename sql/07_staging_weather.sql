-- sql/07_staging_weather.sql
-- Weighted multi-city aggregate; weights renormalized over cities present that hour.
create or replace table staging.weather_hourly as
select w.ts_utc,
       sum(w.temp_c * c.weight) / sum(c.weight) as temp_c,
       sum(w.wind_ms * c.weight) / sum(c.weight) as wind_ms,
       sum(w.ghi_wm2 * c.weight) / sum(c.weight) as ghi_wm2,
       sum(w.cloud_pct * c.weight) / sum(c.weight) as cloud_pct
from raw.weather_history w
join raw.weather_cities c using (city)
group by 1;
