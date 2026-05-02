"""
DAG: krisha_om_ingestion_dag
Purpose: Ingest KRISHA_DWH (внешний postgres :5433) metadata + dbt lineage в OpenMetadata.
         KRISHA_DWH — отдельный проект (~/KRISHA_DWH), его dbt target/ примонтирован
         в /opt/airflow/krisha_dbt:ro через docker-compose.yml.
Schedule: Daily at 07:30 UTC — после krisha_dwh own DAG'ов и после omega3 om_ingestion_dag.
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
    dag_id="krisha_om_ingestion_dag",
    description="Ingest KRISHA_DWH Postgres metadata + dbt lineage into OpenMetadata",
    default_args=default_args,
    schedule="30 7 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["openmetadata", "ingestion", "lineage", "krisha_dwh"],
) as dag:

    start = EmptyOperator(task_id="start")
    end = EmptyOperator(task_id="end")

    ingest_krisha_postgres = BashOperator(
        task_id="ingest_krisha_postgres_metadata",
        bash_command=(
            f"python3 {SCRIPTS_DIR}/run_om_ingestion.py "
            f"-c {INGESTION_DIR}/krisha_postgres_metadata.yaml"
        ),
    )

    ingest_krisha_dbt_lineage = BashOperator(
        task_id="ingest_krisha_dbt_lineage",
        bash_command=(
            f"python3 {SCRIPTS_DIR}/run_dbt_ingestion.py "
            f"-c {INGESTION_DIR}/krisha_dbt_lineage.yaml"
        ),
    )

    start >> ingest_krisha_postgres >> ingest_krisha_dbt_lineage >> end
