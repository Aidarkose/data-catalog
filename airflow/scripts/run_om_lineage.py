#!/usr/bin/env python3
"""Run OpenMetadata lineage (usage) workflow."""
from __future__ import annotations

import argparse, base64, json, os, sys, urllib.request
import yaml

def get_token() -> str:
    tok = os.environ.get("OM_JWT_TOKEN")
    if tok:
        return tok
    server = os.environ.get("OPENMETADATA_SERVER_URL", "http://openmetadata-server:8585/api").rstrip("/")
    b64 = base64.b64encode(os.environ.get("OM_ADMIN_PASSWORD", "admin").encode()).decode()
    req = urllib.request.Request(
        f"{server}/v1/users/login",
        data=json.dumps({"email": os.environ.get("OM_ADMIN_EMAIL", "admin@open-metadata.org"), "password": b64}).encode(),
        method="POST", headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)["accessToken"]

parser = argparse.ArgumentParser()
parser.add_argument("-c", "--config", required=True)
args = parser.parse_args()

with open(args.config) as f:
    config = yaml.safe_load(f)

sec = config.setdefault("workflowConfig", {}).setdefault("openMetadataServerConfig", {}).setdefault("securityConfig", {})
if not sec.get("jwtToken"):
    sec["jwtToken"] = get_token()

from metadata.workflow.usage import UsageWorkflow
from metadata.workflow.workflow_output_handler import WorkflowResultStatus
workflow = UsageWorkflow.create(config)
workflow.execute()
workflow.print_status()
status = workflow.result_status()
sys.exit(0 if status == WorkflowResultStatus.SUCCESS else 1)
