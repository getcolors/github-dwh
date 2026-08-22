#!/usr/bin/env python3
import os
import subprocess
from datetime import datetime, timedelta, timezone
import requests

BASE = os.environ.get("POCKETBASE_URL", "http://127.0.0.1:8090")
EMAIL = os.environ["POCKETBASE_SUPERUSER_EMAIL"]
PASSWORD = os.environ["COLORS_PAR_POCKETBASE_SUPERUSER_PASSWORD"]
NOW = datetime.now(timezone.utc)

s = requests.Session()
r = s.post(f"{BASE}/api/collections/_superusers/auth-with-password", json={"identity": EMAIL, "password": PASSWORD}, timeout=20); r.raise_for_status()
s.headers["Authorization"] = r.json()["token"]


def records(collection, **params):
    r = s.get(f"{BASE}/api/collections/{collection}/records", params={"perPage": 200, **params}, timeout=20); r.raise_for_status(); return r.json()["items"]


def patch(collection, rid, body):
    r = s.patch(f"{BASE}/api/collections/{collection}/records/{rid}", json=body, timeout=20); r.raise_for_status(); return r.json()


def create(collection, body):
    r = s.post(f"{BASE}/api/collections/{collection}/records", json=body, timeout=20)
    if r.status_code not in (200, 201) and r.status_code != 400: r.raise_for_status()
    return r.json() if r.status_code in (200, 201) else None

# Materialize due slots. The unique idempotency key makes timer restarts safe.
for schedule in records("schedules", filter="enabled=true", expand="pipeline"):
    interval = max(1, int(schedule.get("interval_minutes") or 60))
    last = schedule.get("last_enqueued")
    last_dt = datetime.fromisoformat(last.replace("Z", "+00:00")) if last else None
    if last_dt and NOW < last_dt + timedelta(minutes=interval):
        continue
    slot = NOW.replace(second=0, microsecond=0)
    key = f"{schedule['id']}:{slot.isoformat()}"
    create("runs", {"pipeline": schedule["pipeline"], "schedule": schedule["id"], "event": schedule["event"], "trigger": "schedule", "status": "queued", "scheduled_for": slot.isoformat(), "idempotency_key": key})
    patch("schedules", schedule["id"], {"last_enqueued": slot.isoformat()})

# Honor cancellation without teaching PocketBase process semantics.
for run in records("runs", filter='status="running" && cancellation_requested=true'):
    unit = run.get("systemd_unit")
    if unit:
        subprocess.run(["systemctl", "stop", unit], check=False)
    patch("runs", run["id"], {"status": "canceled", "finished": NOW.isoformat(), "exit": 143})

active = {row["pipeline"] for row in records("runs", filter='status="launching" || status="running"')}
for run in records("runs", filter='status="queued"', sort="created"):
    if run["pipeline"] in active:
        continue
    unit = f"github-dwh-run-{run['id']}.service"
    patch("runs", run["id"], {"status": "launching", "systemd_unit": unit})
    command = ["systemd-run", "--unit", unit.removesuffix(".service"), "--collect", "--property=EnvironmentFile=/etc/github-dwh/environment", "--property=WorkingDirectory=/opt/github-dwh", "/opt/github-dwh/.venv/bin/python", "/opt/github-dwh/run.py", run["id"]]
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        patch("runs", run["id"], {"status": "failed", "finished": NOW.isoformat(), "exit": result.returncode, "error_summary": (result.stderr or result.stdout)[-1000:]})
    else:
        active.add(run["pipeline"])
