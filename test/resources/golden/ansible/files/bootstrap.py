#!/usr/bin/env python3
import os
import requests

BASE = os.environ.get("POCKETBASE_URL", "http://127.0.0.1:8090")
EMAIL = os.environ["POCKETBASE_SUPERUSER_EMAIL"]
PASSWORD = os.environ["POCKETBASE_SUPERUSER_PASSWORD"]

session = requests.Session()
auth = session.post(f"{BASE}/api/collections/_superusers/auth-with-password", json={"identity": EMAIL, "password": PASSWORD}, timeout=30)
auth.raise_for_status()
session.headers["Authorization"] = auth.json()["token"]


def collections():
    response = session.get(f"{BASE}/api/collections", params={"perPage": 200}, timeout=30)
    response.raise_for_status()
    return {row["name"]: row for row in response.json()["items"]}


def ensure(name, fields, indexes=None):
    existing = collections()
    if name in existing:
        return existing[name]
    body = {"name": name, "type": "base", "fields": fields, "indexes": indexes or [], "listRule": "@request.auth.id != ''", "viewRule": "@request.auth.id != ''", "createRule": "@request.auth.id != ''", "updateRule": None, "deleteRule": None}
    response = session.post(f"{BASE}/api/collections", json=body, timeout=30)
    response.raise_for_status()
    return response.json()

text = lambda name, required=False: {"name": name, "type": "text", "required": required}
boolf = lambda name: {"name": name, "type": "bool"}
number = lambda name: {"name": name, "type": "number"}
date = lambda name: {"name": name, "type": "date"}
jsonf = lambda name: {"name": name, "type": "json"}
select = lambda name, values: {"name": name, "type": "select", "required": True, "maxSelect": 1, "values": values}
relation = lambda name, cid, required=False: {"name": name, "type": "relation", "collectionId": cid, "required": required, "maxSelect": 1, "cascadeDelete": True}

pipelines = ensure("pipelines", [text("name", True), text("checkout_key", True), jsonf("allowed_events"), boolf("enabled"), number("max_active_runs")], ["CREATE UNIQUE INDEX idx_pipelines_name ON pipelines (name)"])
schedules = ensure("schedules", [relation("pipeline", pipelines["id"], True), select("event", ["run"]), number("interval_minutes"), text("timezone"), boolf("enabled"), date("last_enqueued")])
runs = ensure("runs", [relation("pipeline", pipelines["id"], True), relation("schedule", schedules["id"]), select("event", ["run"]), select("trigger", ["manual", "schedule", "api"]), select("status", ["queued", "launching", "running", "succeeded", "failed", "canceled"]), date("scheduled_for"), text("systemd_unit"), text("git_sha"), boolf("git_dirty"), date("started"), date("finished"), number("exit"), text("error_summary"), jsonf("safe_result"), text("idempotency_key"), boolf("cancellation_requested")], ["CREATE UNIQUE INDEX idx_runs_idempotency ON runs (idempotency_key) WHERE idempotency_key != ''"])

response = session.get(f"{BASE}/api/collections/pipelines/records", params={"filter": 'name="github-getcolors"'}, timeout=30)
response.raise_for_status()
items = response.json()["items"]
if items:
    pipeline = items[0]
else:
    response = session.post(f"{BASE}/api/collections/pipelines/records", json={"name": "github-getcolors", "checkout_key": "github-dwh", "allowed_events": ["run"], "enabled": True, "max_active_runs": 1}, timeout=30)
    response.raise_for_status(); pipeline = response.json()
response = session.get(f"{BASE}/api/collections/schedules/records", params={"filter": f'pipeline="{pipeline["id"]}"'}, timeout=30)
response.raise_for_status()
if not response.json()["items"]:
    response = session.post(f"{BASE}/api/collections/schedules/records", json={"pipeline": pipeline["id"], "event": "run", "interval_minutes": 60, "timezone": "UTC", "enabled": True}, timeout=30)
    response.raise_for_status()
