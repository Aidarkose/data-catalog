-- Mart: daily snapshot of table statistics (row counts, size)
-- Lightweight metric: counts tables per schema + estimates size
-- Lineage: stg_table_catalog → daily_table_stats
--
-- This model is designed to work immediately after dump load.
-- It uses pg_stat_user_tables for real row estimates.

with catalog as (
    select * from {{ ref('stg_table_catalog') }}
    where table_type = 'BASE TABLE'
),

pg_stats as (
    select
        schemaname   as schema_name,
        relname      as table_name,
        n_live_tup   as estimated_row_count,
        pg_total_relation_size(
            quote_ident(schemaname) || '.' || quote_ident(relname)
        )            as total_bytes
    from pg_stat_user_tables
),

final as (
    select
        c.database_name,
        c.schema_name,
        c.table_name,
        c.full_table_name,
        coalesce(s.estimated_row_count, 0)                  as estimated_row_count,
        coalesce(s.total_bytes, 0)                          as total_size_bytes,
        round(coalesce(s.total_bytes, 0) / 1024.0 / 1024.0, 2) as total_size_mb,
        date_trunc('day', current_timestamp)::date          as snapshot_date,
        current_timestamp                                   as refreshed_at
    from catalog c
    left join pg_stats s
        on c.schema_name = s.schema_name
        and c.table_name = s.table_name
)

select * from final
order by total_size_bytes desc
