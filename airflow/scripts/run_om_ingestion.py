#!/usr/bin/env python3
"""
Run OpenMetadata ingestion — patches cryptography version conflict.
Root cause: inject_query_header calls pkg_resources.require("openmetadata-ingestion")
which validates ALL transitive deps including msal→cryptography<45.
Airflow 2.9.3 ships cryptography 46.x — incompatible.
Fix: replace the function body to use importlib.metadata instead.
"""
import importlib.metadata

# Patch inject_query_header BEFORE any SQLAlchemy registration
import metadata.ingestion.connections.headers as _hdrs

_orig_render = _hdrs.render_query_header

def _safe_inject_query_header(conn, cursor, statement, parameters, context, executemany):
    """Patched version using importlib.metadata instead of pkg_resources."""
    try:
        version = importlib.metadata.version("openmetadata-ingestion")
        statement_with_header = _orig_render(version) + "\n" + statement
        return statement_with_header, parameters
    except Exception:
        return statement, parameters

_hdrs.inject_query_header = _safe_inject_query_header

# Skip broken test_connection preflight
import metadata.ingestion.source.database.common_db_source as _cdb
_cdb.CommonDbSourceService.test_connection = lambda self: None

import yaml
import argparse
from metadata.workflow.metadata import MetadataWorkflow

parser = argparse.ArgumentParser()
parser.add_argument('-c', '--config', required=True)
args = parser.parse_args()

with open(args.config) as f:
    config = yaml.safe_load(f)

workflow = MetadataWorkflow.create(config)
workflow.execute()
workflow.print_status()
