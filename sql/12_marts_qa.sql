-- sql/12_marts_qa.sql
-- Cross-source QA: Ember(EUR->PLN via NBP mid) vs PSE CSDAC on overlapping hours.
-- Residual gap expected: market-coupling FX differs from NBP mid — documented, not hidden.
create or replace table marts.qa_overlap as
select e.ts_utc,
       e.price_eur_mwh * f.eur_pln as ember_pln,
       p.price_pln_mwh as pse_pln,
       abs(e.price_eur_mwh * f.eur_pln - p.price_pln_mwh) as abs_diff
from raw.ember_pl e
join staging.fx_daily f on f.date = cast(e.ts_utc as date)
join staging.price_pse_hourly p on p.ts_utc = e.ts_utc;
