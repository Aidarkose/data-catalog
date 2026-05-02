"""
DAG: atrocore_om_ingestion_dag
Purpose: Ingest AtroCore (Reference Data Management) metadata в OpenMetadata.
         AtroCore хранит справочники в БД atrocore_db в omega3-postgres.
         Каждая Entity AtroCore = таблица в public-схеме.
Schedule: Daily at 08:00 UTC — после krisha_om_ingestion_dag (07:30) и
         dbt_daily_run (06:00).
"""
from __future__ import annotations

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
    dag_id="atrocore_om_ingestion_dag",
    description="Ingest AtroCore RDM (atrocore_db) metadata into OpenMetadata",
    default_args=default_args,
    schedule="0 8 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["openmetadata", "ingestion", "atrocore", "rdm"],
) as dag:

    start = EmptyOperator(task_id="start")
    end = EmptyOperator(task_id="end")

    ingest_atrocore = BashOperator(
        task_id="ingest_atrocore_metadata",
        bash_command=(
            f"python3 {SCRIPTS_DIR}/run_om_ingestion.py "
            f"-c {INGESTION_DIR}/atrocore_postgres_metadata.yaml"
        ),
    )

    start >> ingest_atrocore >> end
