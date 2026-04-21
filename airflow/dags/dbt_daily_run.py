"""
DAG: dbt_daily_run
Purpose: Run dbt models daily and emit OpenLineage events to OpenMetadata.
Schedule: Daily at 06:00 UTC
Airflow: 3.0.x (uses EmptyOperator, `schedule=`, new provider paths).
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.empty import EmptyOperator

DBT_PROJECT_DIR = os.getenv("DBT_PROJECT_DIR", "/opt/airflow/dbt")
DBT_PROFILES_DIR = os.getenv("DBT_PROFILES_DIR", "/opt/airflow/dbt")
DBT_THREADS = os.getenv("DBT_THREADS", "8")
DBT_TARGET = os.getenv("DBT_TARGET", "prod")

DBT_BASE_CMD = (
    f"dbt --no-use-colors "
    f"--project-dir {DBT_PROJECT_DIR} "
    f"--profiles-dir {DBT_PROFILES_DIR} "
)

default_args = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="dbt_daily_run",
    description="Daily dbt run: staging → marts with OpenLineage to OpenMetadata",
    default_args=default_args,
    schedule="0 6 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["dbt", "omega3", "lineage"],
    doc_md="""
    ## dbt Daily Run (OMEGA-3)

    Runs the dbt pipeline daily:
    1. `dbt deps` — install packages
    2. `dbt run --select staging` — build staging views
    3. `dbt run --select marts` — build mart tables
    4. `dbt test` — run data quality tests
    5. `dbt docs generate` — refresh manifest.json + catalog.json

    OpenLineage events are forwarded to OpenMetadata via the transport
    configured in `AIRFLOW__OPENLINEAGE__TRANSPORT`.
    """,
) as dag:

    start = EmptyOperator(task_id="start")
    end = EmptyOperator(task_id="end")

    dbt_deps = BashOperator(
        task_id="dbt_deps",
        bash_command=f"{DBT_BASE_CMD} deps",
    )
    dbt_run_staging = BashOperator(
        task_id="dbt_run_staging",
        bash_command=f"{DBT_BASE_CMD} run --target {DBT_TARGET} --threads {DBT_THREADS} --select staging",
    )
    dbt_run_marts = BashOperator(
        task_id="dbt_run_marts",
        bash_command=f"{DBT_BASE_CMD} run --target {DBT_TARGET} --threads {DBT_THREADS} --select marts",
    )
    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"{DBT_BASE_CMD} test --target {DBT_TARGET} --threads {DBT_THREADS}",
        trigger_rule="all_done",
    )
    dbt_docs_generate = BashOperator(
        task_id="dbt_docs_generate",
        bash_command=f"{DBT_BASE_CMD} docs generate --target {DBT_TARGET} --threads {DBT_THREADS}",
    )

    start >> dbt_deps >> dbt_run_staging >> dbt_run_marts >> dbt_test >> dbt_docs_generate >> end
