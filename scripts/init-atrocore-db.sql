-- =====================================================================
-- AtroCore — создание пользователя и БД в существующем omega3-postgres.
-- Идемпотентный скрипт: можно запускать многократно.
--
-- Применение на живом стеке:
--   docker exec -i omega3-postgres psql -U postgres -f - \
--     < scripts/init-atrocore-db.sql
-- =====================================================================

DO
$$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'atrocore') THEN
      CREATE ROLE atrocore LOGIN PASSWORD 'atrocore_secret_2026';
   END IF;
END
$$;

SELECT 'CREATE DATABASE atrocore_db OWNER atrocore'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'atrocore_db')\gexec

GRANT ALL PRIVILEGES ON DATABASE atrocore_db TO atrocore;

\connect atrocore_db
GRANT ALL ON SCHEMA public TO atrocore;
