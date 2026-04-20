-- Mart: daily flight statistics by status
-- Lightweight metric: GROUP BY flight_date + status (no full table scan of tickets)
-- Lineage: stg_flights → daily_flight_stats
-- Threads: 8 (configured in profiles.yml)

with flights as (
    select * from {{ ref('stg_flights') }}
),

daily_stats as (
    select
        flight_date,
        status,
        count(*)                                                    as flight_count,
        count(*) filter (where is_active)                          as active_count,
        round(avg(departure_delay_min) filter (
            where departure_delay_min is not null), 1)             as avg_delay_min,
        max(departure_delay_min)                                   as max_delay_min,
        current_timestamp                                          as refreshed_at
    from flights
    group by flight_date, status
)

select * from daily_stats
order by flight_date desc, flight_count desc
