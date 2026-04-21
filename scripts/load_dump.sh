#!/usr/bin/env bash
# =====================================================================
# load_dump.sh — загрузка дампа в Postgres (контейнер omega3-postgres)
#
# Поддерживает:
#   - plain SQL (с CREATE DATABASE и \connect) → psql -d postgres
#   - pg_dump custom format (binary)           → pg_restore -d <target>
#   - gzip для любого из двух
#
# Источник по умолчанию: /home/daurena2609/dumps/demo-20250901-2y.sql.gz
# Целевая БД для custom формата: demo (плейн-дамп создаст её сам)
# =====================================================================
set -euo pipefail

DUMP_FILE="${1:-/home/daurena2609/dumps/demo-20250901-2y.sql.gz}"
CONTAINER="omega3-postgres"
TARGET_DB="${TARGET_DB:-demo}"
PG_USER="postgres"

echo "==> Dump файл: $DUMP_FILE"
[[ -f "$DUMP_FILE" ]] || { echo "ERROR: Файл не найден"; exit 1; }

echo "==> Контейнер: $CONTAINER"
docker exec "$CONTAINER" pg_isready -U "$PG_USER" >/dev/null \
  || { echo "ERROR: Postgres не готов"; exit 1; }

# Определяем формат: читаем первые байты распакованного потока
HEAD=$(gunzip -c "$DUMP_FILE" 2>/dev/null | head -c 5 || true)
if [[ "$HEAD" == "PGDMP" ]]; then
  FORMAT="custom"
elif [[ "$HEAD" == "-- Po" || "$HEAD" == "-- Du" || "$HEAD" == "--"* || "$HEAD" == "SET "* || "$HEAD" == "CREATE"* ]]; then
  FORMAT="plain"
else
  FORMAT="plain"
  echo "==> ВНИМАНИЕ: не удалось определить формат, пробую как plain SQL (первые байты: '$HEAD')"
fi
echo "==> Формат: $FORMAT"

case "$FORMAT" in
  plain)
    # Plain SQL обычно сам создаёт БД через CREATE DATABASE + \connect
    echo "==> Загружаю plain SQL (через psql -d postgres, дамп сам создаст БД)..."
    gunzip -c "$DUMP_FILE" \
      | docker exec -i "$CONTAINER" psql -U "$PG_USER" -d postgres \
          -v ON_ERROR_STOP=0 --quiet 2>&1 \
      | tail -60
    ;;
  custom)
    echo "==> Создаю целевую БД $TARGET_DB (если нужно)..."
    docker exec "$CONTAINER" psql -U "$PG_USER" -d postgres -tc \
      "SELECT 1 FROM pg_database WHERE datname='$TARGET_DB'" | grep -q 1 \
      || docker exec "$CONTAINER" psql -U "$PG_USER" -d postgres -c \
           "CREATE DATABASE $TARGET_DB;"
    echo "==> Загружаю custom dump через pg_restore..."
    gunzip -c "$DUMP_FILE" \
      | docker exec -i "$CONTAINER" \
          pg_restore -U "$PG_USER" -d "$TARGET_DB" --no-owner --no-privileges -v 2>&1 \
      | tail -60
    ;;
esac

echo ""
echo "==> Грантую права demo_user на схему bookings (для dbt)..."
for stmt in \
  "GRANT CONNECT ON DATABASE demo TO demo_user" \
  "GRANT USAGE ON SCHEMA bookings TO demo_user" \
  "GRANT SELECT ON ALL TABLES IN SCHEMA bookings TO demo_user" \
  "ALTER DEFAULT PRIVILEGES IN SCHEMA bookings GRANT SELECT ON TABLES TO demo_user" \
  "CREATE SCHEMA IF NOT EXISTS public_staging AUTHORIZATION demo_user" \
  "CREATE SCHEMA IF NOT EXISTS public_marts   AUTHORIZATION demo_user" \
  "GRANT ALL ON SCHEMA public         TO demo_user" \
  "GRANT ALL ON SCHEMA public_staging TO demo_user" \
  "GRANT ALL ON SCHEMA public_marts   TO demo_user"
do
  docker exec "$CONTAINER" psql -U "$PG_USER" -d "$TARGET_DB" -c "$stmt;" 2>&1 | grep -v '^$' | head -2
done

echo ""
echo "==> Топ-10 таблиц по размеру в БД $TARGET_DB:"
docker exec "$CONTAINER" psql -U "$PG_USER" -d "$TARGET_DB" -c "
  SELECT n.nspname AS schema, c.relname AS table,
         pg_size_pretty(pg_total_relation_size(c.oid)) AS size,
         c.reltuples::bigint AS est_rows
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE c.relkind='r' AND n.nspname NOT IN ('pg_catalog','information_schema')
  ORDER BY pg_total_relation_size(c.oid) DESC
  LIMIT 10;
"

echo ""
echo "✅ Дамп загружен в БД $TARGET_DB"
