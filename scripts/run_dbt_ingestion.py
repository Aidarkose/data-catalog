#!/usr/bin/env python3
"""
Run OpenMetadata dbt lineage ingestion — same patches as run_om_ingestion.py.
"""
import importlib.metadata
import metadata.ingestion.connections.headers as _hdrs

_orig_render = _hdrs.render_query_header

def _safe_inject(conn, cursor, statement, parameters, context, executemany):
    try:
        version = importlib.metadata.version("openmetadata-ingestion")
        return _orig_render(version) + "\n" + statement, parameters
    except Exception:
        return statement, parameters

_hdrs.inject_query_header = _safe_inject

import metadata.ingestion.source.database.common_db_source as _cdb
_cdb.CommonDbSourceService.test_connection = lambda self: None

import yaml, argparse
from metadata.workflow.metadata import MetadataWorkflow

parser = argparse.ArgumentParser()
parser.add_argument('-c', '--config', required=True)
args = parser.parse_args()

with open(args.config) as f:
    config = yaml.safe_load(f)

workflow = MetadataWorkflow.create(config)
workflow.execute()
workflow.print_status()
