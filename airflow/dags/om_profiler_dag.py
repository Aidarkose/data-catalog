"""
DAG: om_postgres_profiler
Purpose: Column-level statistics for demo_postgres → publish to OpenMetadata.
Schedule: Weekly on Sunday at 04:00 UTC (5% sample due to large tables).
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
    "retry_delay": timedelta(minutes=10),
}

with DAG(
    dag_id="om_postgres_profiler",
    description="OpenMetadata — Profiler for demo_postgres (column statistics, 5% sample)",
    default_args=default_args,
    schedule="0 4 * * 0",
    start_date=datetime(2026, 4, 18),
    catchup=False,
    tags=["openmetadata", "profiler", "statistics", "postgres", "omega3"],
) as dag:

    start = EmptyOperator(task_id="start")

    profile = BashOperator(
        task_id="run_profiler",
        bash_command=f"python3 {SCRIPTS_DIR}/run_om_profiler.py -c {INGESTION_DIR}/postgres_profiler.yaml",
        execution_timeout=timedelta(hours=2),
    )

    end = EmptyOperator(task_id="end")

    start >> profile >> end
