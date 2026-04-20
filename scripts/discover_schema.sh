#!/usr/bin/env bash
# ===========================================================
# discover_schema.sh — Inspect loaded DB and update dbt sources.yml
# Run AFTER load_dump.sh
# ===========================================================
set -euo pipefail

CONTAINER="dc-postgres"
DB_NAME="demo_db"
PG_USER="postgres"
SOURCES_FILE="dbt/models/staging/sources.yml"

echo "==> Discovering tables in $DB_NAME..."

TABLES=$(docker exec "$CONTAINER" psql -U "$PG_USER" -d "$DB_NAME" -t -A -c "
  SELECT table_name
  FROM information_schema.tables
  WHERE table_schema = 'public'
    AND table_type = 'BASE TABLE'
  ORDER BY table_name;
")

if [[ -z "$TABLES" ]]; then
  echo "WARNING: No tables found in public schema of $DB_NAME"
  exit 1
fi

echo "==> Found tables:"
echo "$TABLES"
echo ""

# Generate sources.yml
cat > "$SOURCES_FILE" << YAML_EOF
version: 2

sources:
  - name: raw
    description: "Raw source tables loaded from demo dump (demo-20250901-2y)"
    database: demo_db
    schema: public
    tables:
YAML_EOF

while IFS= read -r table; do
  [[ -z "$table" ]] && continue
  cat >> "$SOURCES_FILE" << YAML_EOF
      - name: $table
        description: "Raw table: $table"
YAML_EOF
done <<< "$TABLES"

echo "==> Updated $SOURCES_FILE"
echo ""

# Also show row counts for biggest tables
echo "==> Row count estimates (top 10 by size):"
docker exec "$CONTAINER" psql -U "$PG_USER" -d "$DB_NAME" -c "
  SELECT
    schemaname || '.' || relname AS table_name,
    n_live_tup AS est_rows,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||relname)) AS size
  FROM pg_stat_user_tables
  ORDER BY pg_total_relation_size(schemaname||'.'||relname) DESC
  LIMIT 10;
"

echo ""
echo "✅ Schema discovered. Now update dbt models if needed, then run:"
echo "   cd data-catalog && docker exec dc-airflow-webserver dbt run --project-dir /opt/airflow/dbt --profiles-dir /opt/airflow/dbt"
