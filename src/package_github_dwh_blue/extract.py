from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import dlt
import requests

API = "https://api.github.com"


class GitHub:
    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})

    def pages(self, path: str, params: dict | None = None) -> Iterator[dict]:
        url = path if path.startswith("http") else API + path
        query = {"per_page": 100, **(params or {})}
        while url:
            response = self.session.get(url, params=query if "?" not in url else None, timeout=60)
            response.raise_for_status()
            data = response.json()
            rows = data if isinstance(data, list) else data.get("workflow_runs", [])
            yield from rows
            url = response.links.get("next", {}).get("url")
            query = None

    def json(self, path: str) -> Any:
        response = self.session.get(API + path, timeout=60)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()


def _stamp(row: dict, repo: str | None = None) -> dict:
    return {**row, **({"repository_name": repo} if repo else {}), "extracted_at": datetime.now(timezone.utc).isoformat()}


@dlt.resource(name="repositories", primary_key="id", write_disposition="merge")
def repositories(client: GitHub, org: str):
    for row in client.pages(f"/orgs/{org}/repos", {"type": "all", "sort": "full_name"}):
        yield _stamp(row)


@dlt.resource(name="commits", primary_key="sha", write_disposition="merge")
def commits(client: GitHub, org: str, names: list[str]):
    for repo in names:
        for row in client.pages(f"/repos/{org}/{repo}/commits"):
            yield _stamp(row, repo)


@dlt.resource(name="organization_events", primary_key="id", write_disposition="merge")
def organization_events(client: GitHub, org: str):
    yield from (_stamp(row) for row in client.pages(f"/orgs/{org}/events"))


@dlt.resource(name="workflow_runs", primary_key="id", write_disposition="merge")
def workflow_runs(client: GitHub, org: str, names: list[str]):
    for repo in names:
        for row in client.pages(f"/repos/{org}/{repo}/actions/runs"):
            yield _stamp(row, repo)


@dlt.resource(name="package_skills", primary_key=("repository_name", "path", "blob_sha"), write_disposition="merge")
def package_skills(client: GitHub, org: str, repos: list[dict]):
    wanted_names = {"SKILL.md", "skills-lock.json", "colors.yml"}
    for repo in repos:
        name, branch = repo["name"], repo.get("default_branch") or "main"
        tree = client.json(f"/repos/{org}/{name}/git/trees/{branch}?recursive=1") or {}
        for item in tree.get("tree", []):
            path = item.get("path", "")
            if item.get("type") != "blob" or (Path(path).name not in wanted_names and not path.startswith("skills/package-")):
                continue
            yield {"repository_name": name, "path": path, "blob_sha": item.get("sha"), "size": item.get("size"), "extracted_at": datetime.now(timezone.utc).isoformat()}


def load(opts: dict) -> dict:
    token, org = str(opts["github-token"]), str(opts["github-org"])
    client = GitHub(token)
    repo_rows = list(client.pages(f"/orgs/{org}/repos", {"type": "all", "sort": "full_name"}))
    names = [r["name"] for r in repo_rows if not r.get("archived")]
    enabled = set(opts.get("github-resources") or [])
    selected = []
    if "repositories" in enabled: selected.append(repositories(client, org))
    if "commits" in enabled: selected.append(commits(client, org, names))
    if "organization-events" in enabled: selected.append(organization_events(client, org))
    if "workflow-runs" in enabled: selected.append(workflow_runs(client, org, names))
    if "package-skills" in enabled: selected.append(package_skills(client, org, repo_rows))
    credentials = f"clickhouse://{opts['clickhouse-user']}:{opts['clickhouse-password']}@127.0.0.1:9000/{opts['clickhouse-raw-database']}"
    os.environ["DESTINATION__CLICKHOUSE__CREDENTIALS"] = credentials
    pipeline = dlt.pipeline(pipeline_name="github_dwh", destination="clickhouse", dataset_name=str(opts["clickhouse-raw-database"]), pipelines_dir=os.environ.get("DLT_PIPELINES_DIR"))
    info = pipeline.run(selected)
    return {"loads_ids": list(info.loads_ids), "repositories": len(repo_rows)}
