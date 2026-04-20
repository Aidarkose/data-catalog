-- Initialize project databases
CREATE USER airflow WITH PASSWORD 'airflow_secret_2024';
CREATE USER openmetadata WITH PASSWORD 'openmetadata_secret_2024';
CREATE USER demo_user WITH PASSWORD 'demo_secret_2024';

CREATE DATABASE airflow_db OWNER airflow;
CREATE DATABASE openmetadata_db OWNER openmetadata;
CREATE DATABASE demo_db OWNER demo_user;

GRANT ALL PRIVILEGES ON DATABASE airflow_db TO airflow;
GRANT ALL PRIVILEGES ON DATABASE openmetadata_db TO openmetadata;
GRANT ALL PRIVILEGES ON DATABASE demo_db TO demo_user;
-- Postgres superuser also needs access for dump loading
GRANT ALL PRIVILEGES ON DATABASE demo_db TO postgres;
