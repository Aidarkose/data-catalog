"""
This file has been generated from dag_runner.j2
"""
from airflow import DAG
from openmetadata_managed_apis.workflows import workflow_factory

workflow = workflow_factory.WorkflowFactory.create("/opt/airflow/dag_generated_configs/56a3198c-c11d-48f1-96d6-01117fe6bccd.json")
workflow.generate_dag(globals())
dag = workflow.get_dag()