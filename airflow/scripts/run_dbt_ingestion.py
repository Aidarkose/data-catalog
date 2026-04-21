#!/usr/bin/env python3
"""
Run OpenMetadata dbt lineage ingestion workflow (1.12).
Injects a fresh JWT token from $OM_JWT_TOKEN (or by logging in) into the YAML config.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.request
import yaml

try:
    import importlib.metadata
    import metadata.ingestion.connections.headers as _hdrs  # type: ignore

    _orig_render = _hdrs.render_query_header

    def _safe_inject(conn, cursor, statement, parameters, context, executemany):
        try:
            version = importlib.metadata.version("openmetadata-ingestion")
            return _orig_render(version) + "\n" + statement, parameters
        except Exception:
            return statement, parameters

    _hdrs.inject_query_header = _safe_inject
except Exception:
    pass


def login_and_get_token() -> str:
    server = os.environ.get("OPENMETADATA_SERVER_URL", "http://openmetadata-server:8585/api").rstrip("/")
    email = os.environ.get("OM_ADMIN_EMAIL", "admin@open-metadata.org")
    password = os.environ.get("OM_ADMIN_PASSWORD", "admin")
    b64 = base64.b64encode(password.encode()).decode()
    url = f"{server}/v1/users/login"
    body = json.dumps({"email": email, "password": b64}).encode()
    req = urllib.request.Request(
        url, data=body, method="POST", headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.load(resp)
    return data["accessToken"]


def get_token() -> str:
    tok = os.environ.get("OM_JWT_TOKEN")
    if tok:
        return tok
    return login_and_get_token()


parser = argparse.ArgumentParser()
parser.add_argument("-c", "--config", required=True)
args = parser.parse_args()

with open(args.config) as f:
    config = yaml.safe_load(f)

token = get_token()
config.setdefault("workflowConfig", {}).setdefault("openMetadataServerConfig", {}).setdefault(
    "securityConfig", {}
)["jwtToken"] = token

from metadata.workflow.metadata import MetadataWorkflow  # noqa: E402

workflow = MetadataWorkflow.create(config)
workflow.execute()
workflow.print_status()
sys.exit(workflow.result_status())
