#!/usr/bin/env python3
"""Run OpenMetadata Auto Classification workflow (collects sample data)."""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.request
import yaml


def login_and_get_token() -> str:
    server = os.environ.get("OPENMETADATA_SERVER_URL", "http://openmetadata-server:8585/api").rstrip("/")
    email = os.environ.get("OM_ADMIN_EMAIL", "admin@open-metadata.org")
    password = os.environ.get("OM_ADMIN_PASSWORD", "admin")
    b64 = base64.b64encode(password.encode()).decode()
    req = urllib.request.Request(
        f"{server}/v1/users/login",
        data=json.dumps({"email": email, "password": b64}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)["accessToken"]


def get_token() -> str:
    return os.environ.get("OM_JWT_TOKEN") or login_and_get_token()


parser = argparse.ArgumentParser()
parser.add_argument("-c", "--config", required=True)
args = parser.parse_args()

with open(args.config) as f:
    config = yaml.safe_load(f)

config.setdefault("workflowConfig", {}).setdefault("openMetadataServerConfig", {}).setdefault(
    "securityConfig", {}
)["jwtToken"] = get_token()

from metadata.workflow.classification import AutoClassificationWorkflow  # noqa: E402

workflow = AutoClassificationWorkflow.create(config)
workflow.execute()
workflow.print_status()
sys.exit(0 if workflow.result_status().value == 0 else 1)
