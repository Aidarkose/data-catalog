"""
DAG: om_ingestion_dag
Purpose: Ingest PostgreSQL metadata + dbt lineage into OpenMetadata (1.12).
Schedule: Daily at 07:00 UTC (after dbt_daily_run at 06:00).
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.empty import EmptyOperator

INGESTION_DIR = "/opt/airflow/ingestion"
SCRIPTS_DIR = "/opt/airflow/scripts"

default_args = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="om_ingestion_dag",
    description="Ingest Postgres metadata + dbt lineage into OpenMetadata",
    default_args=default_args,
    schedule="0 7 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["openmetadata", "ingestion", "lineage", "omega3"],
) as dag:

    start = EmptyOperator(task_id="start")
    end = EmptyOperator(task_id="end")

    ingest_postgres = BashOperator(
        task_id="ingest_postgres_metadata",
        bash_command=(
            f"python3 {SCRIPTS_DIR}/run_om_ingestion.py "
            f"-c {INGESTION_DIR}/postgres_service.yaml"
        ),
    )
    ingest_dbt_lineage = BashOperator(
        task_id="ingest_dbt_lineage",
        bash_command=(
            f"python3 {SCRIPTS_DIR}/run_dbt_ingestion.py "
            f"-c {INGESTION_DIR}/dbt_lineage.yaml"
        ),
    )

    start >> ingest_postgres >> ingest_dbt_lineage >> end
