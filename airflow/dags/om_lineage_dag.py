"""
DAG: om_postgres_lineage
Purpose: Extract query-based lineage from demo_postgres → publish to OpenMetadata.
Schedule: Daily at 03:00 UTC.
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
    dag_id="om_postgres_lineage",
    description="OpenMetadata — Lineage ingestion for demo_postgres (query-based lineage)",
    default_args=default_args,
    schedule="0 3 * * *",
    start_date=datetime(2026, 4, 18),
    catchup=False,
    tags=["openmetadata", "lineage", "postgres", "omega3"],
) as dag:

    start = EmptyOperator(task_id="start")

    ingest = BashOperator(
        task_id="ingest_lineage",
        bash_command=f"python3 {SCRIPTS_DIR}/run_om_lineage.py -c {INGESTION_DIR}/postgres_lineage.yaml",
    )

    end = EmptyOperator(task_id="end")

    start >> ingest >> end
