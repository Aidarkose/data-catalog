{{ config(materialized='table') }}

select
    date_series::date as date_day
from generate_series(
    '2015-01-01'::timestamp,
    '2027-12-31'::timestamp,
    '1 day'::interval
) t(date_series)
