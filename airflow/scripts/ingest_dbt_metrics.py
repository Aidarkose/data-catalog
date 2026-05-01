#!/usr/bin/env python3
"""
Ingest dbt MetricFlow metrics from semantic_manifest.json into OpenMetadata.

Reads target/semantic_manifest.json, maps each MetricFlow metric to an OM Metric
entity, and upserts it via the OM Python SDK.

Usage (inside omega3-airflow-apiserver container):
    python3 /opt/airflow/scripts/ingest_dbt_metrics.py \
        --semantic-manifest /opt/airflow/dbt/target/semantic_manifest.json
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.request

METRIC_TYPE_MAP = {
    "count": "COUNT",
    "sum": "SUM",
    "average": "AVERAGE",
    "min": "MIN",
    "max": "MAX",
    "count_distinct": "COUNT",
}

GRANULARITY_MAP = {
    "day": "DAY",
    "week": "WEEK",
    "month": "MONTH",
    "quarter": "QUARTER",
    "year": "YEAR",
    "hour": "HOUR",
    "minute": "MINUTE",
    "second": "SECOND",
}

SQL_AGG_MAP = {
    "count": "COUNT",
    "sum": "SUM",
    "average": "AVG",
    "min": "MIN",
    "max": "MAX",
    "count_distinct": "COUNT DISTINCT",
}


def login_and_get_token(server: str, email: str, password: str) -> str:
    b64 = base64.b64encode(password.encode()).decode()
    url = f"{server}/v1/users/login"
    body = json.dumps({"email": email, "password": b64}).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)["accessToken"]


def get_token(server: str) -> str:
    tok = os.environ.get("OM_JWT_TOKEN")
    if tok:
        return tok
    email = os.environ.get("OM_ADMIN_EMAIL", "admin@open-metadata.org")
    password = os.environ.get("OM_ADMIN_PASSWORD", "admin")
    return login_and_get_token(server, email, password)


def om_request(server: str, token: str, method: str, path: str, body=None):
    url = f"{server}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {method} {url}: {err_body}") from exc


def resolve_measure_agg(semantic_models: list, measure_name: str) -> tuple[str, str]:
    """Return (agg_type, expr) for the given measure name."""
    for sm in semantic_models:
        for measure in sm.get("measures", []):
            if measure["name"] == measure_name:
                return measure.get("agg", "OTHER"), measure.get("expr", measure_name)
    return "OTHER", measure_name


def metric_type_from_agg(agg: str, metric_type: str) -> str:
    if metric_type == "ratio":
        return "RATIO"
    if metric_type == "derived":
        return "OTHER"
    return METRIC_TYPE_MAP.get(agg.lower(), "OTHER")


def metric_expression(agg: str, expr: str) -> str:
    sql_agg = SQL_AGG_MAP.get(agg.lower(), agg.upper())
    return f"{sql_agg}({expr})"


def build_create_payload(metric: dict, semantic_models: list) -> dict:
    name = metric["name"]
    label = metric.get("label") or name.replace("_", " ").title()
    description = (metric.get("description") or "").strip()
    mtype = metric.get("type", "simple")

    measure_name = (
        (metric.get("type_params") or {})
        .get("measure", {})
        .get("name") or ""
    )
    agg, expr = resolve_measure_agg(semantic_models, measure_name)

    om_metric_type = metric_type_from_agg(agg, mtype)
    sql_expr = metric_expression(agg, expr) if measure_name else name

    time_granularity = metric.get("time_granularity") or "day"
    om_granularity = GRANULARITY_MAP.get(time_granularity.lower(), "DAY")

    payload: dict = {
        "name": name,
        "displayName": label,
        "description": description,
        "metricType": om_metric_type,
        "granularity": om_granularity,
        "metricExpression": {
            "language": "SQL",
            "code": sql_expr,
        },
    }
    return payload


def upsert_metric(server: str, token: str, payload: dict) -> dict:
    # PUT /v1/metrics is the upsert endpoint — it creates or updates by name.
    # The CreateMetricRequest schema does NOT accept an 'id' field.
    name = payload["name"]
    result = om_request(server, token, "PUT", "/v1/metrics", payload)
    print(f"  Upserted metric: {name} (id={result['id']})")
    return result


def main():
    parser = argparse.ArgumentParser(description="Ingest dbt MetricFlow metrics into OpenMetadata")
    parser.add_argument(
        "--semantic-manifest",
        default="/opt/airflow/dbt/target/semantic_manifest.json",
        help="Path to dbt semantic_manifest.json",
    )
    args = parser.parse_args()

    server = os.environ.get(
        "OPENMETADATA_SERVER_URL", "http://openmetadata-server:8585/api"
    ).rstrip("/")

    print(f"Loading semantic manifest from: {args.semantic_manifest}")
    with open(args.semantic_manifest) as f:
        sm = json.load(f)

    metrics = sm.get("metrics", [])
    semantic_models = sm.get("semantic_models", [])

    if not metrics:
        print("No MetricFlow metrics found in semantic_manifest.json — nothing to ingest.")
        sys.exit(0)

    print(f"Found {len(metrics)} metric(s): {[m['name'] for m in metrics]}")

    token = get_token(server)
    print(f"Authenticated against {server}")

    for metric in metrics:
        payload = build_create_payload(metric, semantic_models)
        upsert_metric(server, token, payload)

    print(f"\nDone: {len(metrics)} metric(s) ingested into OpenMetadata.")


if __name__ == "__main__":
    main()
