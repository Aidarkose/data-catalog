-- Staging: clean and type-cast flights source table
-- Lineage: bookings.flights → stg_flights → marts.daily_flight_stats

with source as (
    select * from {{ source('bookings', 'flights') }}
),

staged as (
    select
        flight_id,
        route_no,
        status,
        scheduled_departure,
        scheduled_arrival,
        actual_departure,
        actual_arrival,
        -- derived
        scheduled_departure::date                          as flight_date,
        extract(hour from scheduled_departure)::int        as departure_hour,
        case when actual_departure is not null
             then extract(epoch from (actual_departure - scheduled_departure)) / 60
        end::numeric(8,1)                                  as departure_delay_min,
        case when status in ('Arrived', 'Departed', 'On Time', 'Boarding', 'Scheduled')
             then true else false
        end                                                as is_active
    from source
)

select * from staged
