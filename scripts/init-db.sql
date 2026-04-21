-- =====================================================================
-- OMEGA-3 Postgres initialization
--   - Creates metadata users & DBs for Airflow and OpenMetadata
--   - Source DB `demo` is created by the dump (bookings schema) during
--     scripts/load_dump.sh — we only pre-create a helper user for dbt.
-- =====================================================================

CREATE USER airflow      WITH PASSWORD 'airflow_secret_2024';
CREATE USER openmetadata WITH PASSWORD 'openmetadata_secret_2024';
CREATE USER demo_user    WITH PASSWORD 'demo_secret_2024';

CREATE DATABASE airflow_db      OWNER airflow;
CREATE DATABASE openmetadata_db OWNER openmetadata;

GRANT ALL PRIVILEGES ON DATABASE airflow_db      TO airflow;
GRANT ALL PRIVILEGES ON DATABASE openmetadata_db TO openmetadata;

-- demo_user is granted SELECT on source schemas AFTER dump load
-- (see scripts/load_dump.sh which runs the GRANT block post-restore).
