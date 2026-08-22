#!/usr/bin/env python3
"""Converge Lightdash access, semantic project, and initial analytics dashboard."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

LIGHTDASH_URL = os.environ.get("LIGHTDASH_URL", "http://127.0.0.1:8080")
CLICKHOUSE_URL = os.environ.get("CLICKHOUSE_URL", "http://127.0.0.1:8123")
ADMIN_EMAIL = os.environ["LIGHTDASH_ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["COLORS_PAR_LIGHTDASH_ADMIN_PASSWORD"]
LIGHTDASH_CLICKHOUSE_USER = os.environ["LIGHTDASH_CLICKHOUSE_USER"]
LIGHTDASH_CLICKHOUSE_PASSWORD = os.environ["COLORS_PAR_LIGHTDASH_CLICKHOUSE_PASSWORD"]
CONTENT = Path(os.environ.get("LIGHTDASH_CONTENT", "/opt/github-dwh/lightdash_content.json"))


def checked(response: requests.Response) -> dict:
    try:
        body = response.json()
    except ValueError:
        body = {}
    if not response.ok:
        message = body.get("error", {}).get("message") if isinstance(body.get("error"), dict) else body.get("error")
        raise RuntimeError(message or f"request failed with HTTP {response.status_code}")
    return body


def clickhouse(query: str, parameters: dict | None = None) -> str:
    response = requests.post(
        CLICKHOUSE_URL,
        params={"query": query, **{f"param_{key}": value for key, value in (parameters or {}).items()}},
        auth=(os.environ["CLICKHOUSE_USER"], os.environ["COLORS_PAR_CLICKHOUSE_PASSWORD"]),
        timeout=30,
    )
    response.raise_for_status()
    return response.text.strip()


def converge_clickhouse_user() -> None:
    clickhouse(
        f"CREATE USER IF NOT EXISTS {LIGHTDASH_CLICKHOUSE_USER} IDENTIFIED WITH sha256_password BY {{password:String}}",
        {"password": LIGHTDASH_CLICKHOUSE_PASSWORD},
    )
    clickhouse(
        f"ALTER USER {LIGHTDASH_CLICKHOUSE_USER} IDENTIFIED WITH sha256_password BY {{password:String}}",
        {"password": LIGHTDASH_CLICKHOUSE_PASSWORD},
    )
    for database in (os.environ["CLICKHOUSE_ANALYTICS_DATABASE"], os.environ["CLICKHOUSE_MARTS_DATABASE"]):
        clickhouse(f"GRANT SELECT ON {database}.* TO {LIGHTDASH_CLICKHOUSE_USER}")


def wait_for_lightdash() -> None:
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        try:
            if requests.get(f"{LIGHTDASH_URL}/api/v1/health", timeout=10).ok:
                return
        except requests.RequestException:
            pass
        time.sleep(3)
    raise RuntimeError("Lightdash did not become healthy")


def login() -> requests.Session:
    session = requests.Session()
    register = session.post(
        f"{LIGHTDASH_URL}/api/v1/user",
        json={"firstName": "getcolors", "lastName": "admin", "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    if register.ok:
        return session
    response = session.post(
        f"{LIGHTDASH_URL}/api/v1/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    checked(response)
    return session


def wait_for_job(session: requests.Session, job_uuid: str) -> None:
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        result = checked(session.get(f"{LIGHTDASH_URL}/api/v1/jobs/{job_uuid}", timeout=30))["results"]
        status = result.get("status")
        if status == "DONE":
            return
        if status == "ERROR":
            raise RuntimeError("Lightdash dbt compilation failed")
        time.sleep(3)
    raise RuntimeError("Lightdash dbt compilation timed out")


def project_uuid(session: requests.Session) -> str:
    projects = checked(session.get(f"{LIGHTDASH_URL}/api/v1/org/projects", timeout=30))["results"]
    existing = next((project for project in projects if project.get("name") == "getcolors GitHub analytics"), None)
    if existing:
        return existing["projectUuid"]
    body = {
        "name": "getcolors GitHub analytics",
        "type": "DEFAULT",
        "dbtVersion": "v1.9",
        "dbtConnection": {"type": "dbt", "project_dir": "/usr/app/dbt", "target": "prod", "selector": "tag:lightdash"},
        "warehouseConnection": {
            "type": "clickhouse",
            "host": "clickhouse",
            "port": 8123,
            "user": LIGHTDASH_CLICKHOUSE_USER,
            "password": LIGHTDASH_CLICKHOUSE_PASSWORD,
            "schema": os.environ["CLICKHOUSE_ANALYTICS_DATABASE"],
            "secure": False,
        },
        "tableConfiguration": "all",
    }
    return checked(session.post(f"{LIGHTDASH_URL}/api/v1/org/projects", json=body, timeout=60))["results"]["projectUuid"]


def refresh_project(session: requests.Session, project: str) -> None:
    result = checked(session.post(f"{LIGHTDASH_URL}/api/v1/projects/{project}/refresh", timeout=60))["results"]
    wait_for_job(session, result["jobUuid"])


def converge_content(session: requests.Session, project: str) -> None:
    content = json.loads(CONTENT.read_text())
    checked(session.post(f"{LIGHTDASH_URL}/api/v1/projects/{project}/code/spaces", json=content["space"], timeout=60))
    for chart in content["charts"]:
        checked(session.post(f"{LIGHTDASH_URL}/api/v1/projects/{project}/code/charts/{chart['slug']}", json=chart, timeout=60))
    dashboard = content["dashboard"]
    checked(session.post(f"{LIGHTDASH_URL}/api/v1/projects/{project}/code/dashboards/{dashboard['slug']}", json=dashboard, timeout=60))


def main() -> None:
    converge_clickhouse_user()
    wait_for_lightdash()
    session = login()
    project = project_uuid(session)
    required_tables = ("repository_health", "package_skill_coverage")
    tables_ready = all(clickhouse(f"EXISTS TABLE {os.environ['CLICKHOUSE_MARTS_DATABASE']}.{table}") == "1" for table in required_tables)
    if tables_ready:
        refresh_project(session, project)
        converge_content(session, project)
        print(f"Lightdash project and dashboard converged: {project}")
    else:
        print(f"Lightdash project registered; dashboard waits for the first complete warehouse run: {project}")


if __name__ == "__main__":
    main()
