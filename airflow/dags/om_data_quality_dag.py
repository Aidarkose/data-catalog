"""
DAG: om_postgres_data_quality
Purpose: Execute data quality test cases for all 5 tables in demo_postgres → publish results to OpenMetadata.
Schedule: Daily at 05:00 UTC.
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

DQ_TABLES = [
    ("flights", "postgres_data_quality.yaml"),
    ("bookings", "postgres_dq_bookings.yaml"),
    ("airports_data", "postgres_dq_airports_data.yaml"),
    ("segments", "postgres_dq_segments.yaml"),
    ("tickets", "postgres_dq_tickets.yaml"),
]

with DAG(
    dag_id="om_postgres_data_quality",
    description="OpenMetadata — Data Quality test suites for demo_postgres (5 tables)",
    default_args=default_args,
    schedule="0 5 * * *",
    start_date=datetime(2026, 4, 18),
    catchup=False,
    tags=["openmetadata", "data-quality", "testing", "postgres", "omega3"],
) as dag:

    start = EmptyOperator(task_id="start")
    end = EmptyOperator(task_id="end")

    prev = start
    for table_name, yaml_file in DQ_TABLES:
        task = BashOperator(
            task_id=f"dq_{table_name}",
            bash_command=f"python3 {SCRIPTS_DIR}/run_om_data_quality.py -c {INGESTION_DIR}/{yaml_file}",
        )
        prev >> task
        prev = task

    prev >> end
