#!/usr/bin/env bash
# ===========================================================
# load_dump.sh — Load demo dump into PostgreSQL demo_db
# ===========================================================
set -euo pipefail

DUMP_FILE="${1:-/home/daurena2609/dumps/demo-20250901-2y.sql.gz}"
CONTAINER="dc-postgres"
DB_NAME="demo_db"
PG_USER="postgres"

echo "==> Checking dump file: $DUMP_FILE"
if [[ ! -f "$DUMP_FILE" ]]; then
  echo "ERROR: Dump file not found: $DUMP_FILE"
  exit 1
fi

echo "==> Container: $CONTAINER"
echo "==> Target DB: $DB_NAME"
echo ""

# Detect dump format
if file "$DUMP_FILE" | grep -q "PostgreSQL custom database dump"; then
  echo "==> Format: pg_dump custom (binary)"
  gunzip -c "$DUMP_FILE" | docker exec -i "$CONTAINER" \
    pg_restore -U "$PG_USER" -d "$DB_NAME" --no-owner --no-privileges -v
elif file "$DUMP_FILE" | grep -q "gzip" || [[ "$DUMP_FILE" == *.gz ]]; then
  echo "==> Format: gzipped SQL"
  gunzip -c "$DUMP_FILE" | docker exec -i "$CONTAINER" \
    psql -U "$PG_USER" -d "$DB_NAME" -v ON_ERROR_STOP=0
else
  echo "==> Format: plain SQL"
  cat "$DUMP_FILE" | docker exec -i "$CONTAINER" \
    psql -U "$PG_USER" -d "$DB_NAME" -v ON_ERROR_STOP=0
fi

echo ""
echo "==> Verifying load..."
docker exec "$CONTAINER" psql -U "$PG_USER" -d "$DB_NAME" -c "
  SELECT table_schema, table_name,
    pg_size_pretty(pg_total_relation_size(quote_ident(table_schema)||'.'||quote_ident(table_name))) AS size
  FROM information_schema.tables
  WHERE table_schema NOT IN ('pg_catalog','information_schema')
  ORDER BY pg_total_relation_size(quote_ident(table_schema)||'.'||quote_ident(table_name)) DESC
  LIMIT 20;
"

echo ""
echo "✅ Dump loaded. Run scripts/discover_schema.sh to update dbt sources."
