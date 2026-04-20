"""
DAG: dbt_daily_run
Purpose: Run dbt models daily and emit OpenLineage events to OpenMetadata.
Schedule: Daily at 06:00 UTC
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.dummy import DummyOperator

DBT_PROJECT_DIR = os.getenv("DBT_PROJECT_DIR", "/opt/airflow/dbt")
DBT_PROFILES_DIR = os.getenv("DBT_PROFILES_DIR", "/opt/airflow/dbt")
DBT_THREADS = os.getenv("DBT_THREADS", "8")
DBT_TARGET = os.getenv("DBT_TARGET", "prod")

# OpenLineage is picked up automatically via OPENLINEAGE_URL env var
DBT_BASE_CMD = (
    f"dbt --no-use-colors "
    f"--project-dir {DBT_PROJECT_DIR} "
    f"--profiles-dir {DBT_PROFILES_DIR} "
    f"--target {DBT_TARGET} "
    f"--threads {DBT_THREADS}"
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
    schedule_interval="0 6 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["dbt", "data-catalog", "lineage"],
    doc_md="""
    ## dbt Daily Run

    Runs the full dbt pipeline daily:
    1. `dbt deps` — install packages
    2. `dbt run --select staging` — build staging views
    3. `dbt run --select marts` — build mart tables
    4. `dbt test` — run data quality tests
    5. `dbt docs generate` — generate docs + manifest.json for lineage

    OpenLineage events are automatically sent to OpenMetadata via
    `OPENLINEAGE_URL` environment variable.
    """,
) as dag:

    start = DummyOperator(task_id="start")
    end = DummyOperator(task_id="end")

    dbt_deps = BashOperator(
        task_id="dbt_deps",
        bash_command=f"{DBT_BASE_CMD} deps",
        env={**os.environ, "DBT_PROFILES_DIR": DBT_PROFILES_DIR},
    )

    dbt_run_staging = BashOperator(
        task_id="dbt_run_staging",
        bash_command=f"{DBT_BASE_CMD} run --select staging",
        env={**os.environ, "DBT_PROFILES_DIR": DBT_PROFILES_DIR},
    )

    dbt_run_marts = BashOperator(
        task_id="dbt_run_marts",
        bash_command=f"{DBT_BASE_CMD} run --select marts",
        env={**os.environ, "DBT_PROFILES_DIR": DBT_PROFILES_DIR},
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"{DBT_BASE_CMD} test",
        env={**os.environ, "DBT_PROFILES_DIR": DBT_PROFILES_DIR},
        # Don't fail the DAG on test failure — just report
        trigger_rule="all_done",
    )

    dbt_docs_generate = BashOperator(
        task_id="dbt_docs_generate",
        bash_command=f"{DBT_BASE_CMD} docs generate",
        env={**os.environ, "DBT_PROFILES_DIR": DBT_PROFILES_DIR},
    )

    # Task order
    start >> dbt_deps >> dbt_run_staging >> dbt_run_marts >> dbt_test >> dbt_docs_generate >> end
