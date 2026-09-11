#!/usr/bin/env python3
import os
import subprocess
from datetime import datetime, timedelta, timezone
import requests

BASE = os.environ.get("POCKETBASE_URL", "http://127.0.0.1:8090")
LAUNCH_GRACE = timedelta(minutes=2)
s = requests.Session()


def records(collection, **params):
    r = s.get(f"{BASE}/api/collections/{collection}/records", params={"perPage": 200, **params}, timeout=20); r.raise_for_status(); return r.json()["items"]


def patch(collection, rid, body):
    r = s.patch(f"{BASE}/api/collections/{collection}/records/{rid}", json=body, timeout=20); r.raise_for_status(); return r.json()


def create(collection, body):
    r = s.post(f"{BASE}/api/collections/{collection}/records", json=body, timeout=20)
    if r.status_code not in (200, 201) and r.status_code != 400: r.raise_for_status()
    return r.json() if r.status_code in (200, 201) else None


def unit_state(unit):
    """Return None when systemd cannot give an authoritative answer."""
    try:
        result = subprocess.run(
            ["systemctl", "show", unit, "--property=LoadState,ActiveState"],
            text=True, capture_output=True, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode:
        return None
    properties = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    if properties.get("LoadState") not in ("loaded", "not-found"):
        return None
    return properties.get("ActiveState")


def reconcile(now):
    active = set()
    for run in records("runs", filter='status="launching" || status="running"'):
        # Record IDs are assigned by PocketBase. Do not trust an editable unit name.
        unit = f"github-dwh-run-{run['id']}.service"
        state = unit_state(unit)
        canceled = run.get("cancellation_requested", False)
        if canceled and state not in ("inactive", "failed"):
            try:
                result = subprocess.run(["systemctl", "stop", unit], capture_output=True, timeout=45)
                state = unit_state(unit) if result.returncode == 0 else None
            except (OSError, subprocess.TimeoutExpired):
                state = None
        if state not in ("inactive", "failed"):
            active.add(run["pipeline"])
            continue
        # Use the existing started field for the launch attempt. The worker
        # replaces it with its actual start time after authentication.
        launched = run.get("started") or run.get("created")
        if run["status"] == "launching" and launched:
            try:
                started = datetime.fromisoformat(launched.replace("Z", "+00:00"))
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                if now < started + LAUNCH_GRACE and not canceled:
                    active.add(run["pipeline"])
                    continue
            except ValueError:
                pass
        # The worker may have written its terminal status after our first read.
        current = records("runs", filter=f'id="{run["id"]}"')
        if not current or current[0]["status"] not in ("launching", "running"):
            continue
        canceled = current[0].get("cancellation_requested", False)
        patch("runs", run["id"], {
            "status": "canceled" if canceled else "failed",
            "finished": now.isoformat(), "exit": 143 if canceled else 1,
            "error_summary": "" if canceled else "Worker stopped without recording a result; inspect journald for this unit",
        })
    return active


def main():
    NOW = datetime.now(timezone.utc)
    r = s.post(f"{BASE}/api/collections/_superusers/auth-with-password", json={
        "identity": os.environ["POCKETBASE_SUPERUSER_EMAIL"],
        "password": os.environ["COLORS_PAR_POCKETBASE_SUPERUSER_PASSWORD"],
    }, timeout=20)
    r.raise_for_status()
    s.headers["Authorization"] = r.json()["token"]

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

    active = reconcile(NOW)
    for run in records("runs", filter='status="queued"'):
        if run["pipeline"] in active:
            continue
        unit = f"github-dwh-run-{run['id']}.service"
        patch("runs", run["id"], {"status": "launching", "systemd_unit": unit, "started": datetime.now(timezone.utc).isoformat()})
        command = ["systemd-run", "--unit", unit.removesuffix(".service"), "--collect", "--property=KillMode=control-group", "--property=TimeoutStopSec=30s", "--property=EnvironmentFile=/etc/github-dwh/environment", "--property=WorkingDirectory=/opt/github-dwh", "/opt/github-dwh/.venv/bin/python", "/opt/github-dwh/run.py", run["id"]]
        result = subprocess.run(command, text=True, capture_output=True)
        if result.returncode:
            patch("runs", run["id"], {"status": "failed", "finished": NOW.isoformat(), "exit": result.returncode, "error_summary": (result.stderr or result.stdout)[-1000:]})
        else:
            active.add(run["pipeline"])


if __name__ == "__main__":
    main()
