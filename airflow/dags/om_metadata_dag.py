"""
DAG: om_postgres_metadata
Purpose: Crawl demo_postgres (PostgreSQL) → tables/columns/schema → publish to OpenMetadata.
Schedule: Daily at 02:00 UTC.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.empty import EmptyOperator

SCRIPTS_DIR = "/opt/airflow/scripts"
INGESTION_DIR = "/opt/airflow/ingestion"

default_args = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="om_postgres_metadata",
    description="OpenMetadata — Metadata ingestion for demo_postgres (tables, columns, schema)",
    default_args=default_args,
    schedule="0 2 * * *",
    start_date=datetime(2026, 4, 18),
    catchup=False,
    tags=["openmetadata", "metadata", "postgres", "omega3"],
) as dag:

    start = EmptyOperator(task_id="start")

    ingest = BashOperator(
        task_id="ingest_metadata",
        bash_command=f"python3 {SCRIPTS_DIR}/run_om_ingestion.py -c {INGESTION_DIR}/postgres_metadata.yaml",
    )

    end = EmptyOperator(task_id="end")

    start >> ingest >> end
