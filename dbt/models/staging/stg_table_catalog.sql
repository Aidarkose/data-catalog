-- Staging: extract all user tables from the database catalog
-- Source: information_schema.tables (always available in PostgreSQL)
-- Lineage: information_schema.tables → stg_table_catalog → marts.daily_table_stats

with source as (
    select
        table_catalog,
        table_schema,
        table_name,
        table_type
    from information_schema.tables
    where
        table_schema not in ('pg_catalog', 'information_schema', 'pg_toast')
        and table_type in ('BASE TABLE', 'VIEW')
),

renamed as (
    select
        table_catalog   as database_name,
        table_schema    as schema_name,
        table_name,
        table_type,
        table_schema || '.' || table_name as full_table_name,
        current_timestamp                 as extracted_at
    from source
)

select * from renamed
