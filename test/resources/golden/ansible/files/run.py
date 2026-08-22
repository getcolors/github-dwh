#!/usr/bin/env python3
import os
import subprocess
import sys
from datetime import datetime, timezone
import requests

run_id = sys.argv[1]
base = os.environ.get("POCKETBASE_URL", "http://127.0.0.1:8090")
s = requests.Session()
r = s.post(f"{base}/api/collections/_superusers/auth-with-password", json={"identity": os.environ["POCKETBASE_SUPERUSER_EMAIL"], "password": os.environ["COLORS_PAR_POCKETBASE_SUPERUSER_PASSWORD"]}, timeout=20); r.raise_for_status()
s.headers["Authorization"] = r.json()["token"]
url = f"{base}/api/collections/runs/records/{run_id}"
started = datetime.now(timezone.utc).isoformat()
s.patch(url, json={"status": "running", "started": started, "git_sha": "UNPINNED", "git_dirty": False}, timeout=20).raise_for_status()
result = subprocess.run(["/opt/github-dwh/.venv/bin/python", "-m", "package_github_dwh_blue", "run", "-f", "/etc/github-dwh/colors.yml"])
finished = datetime.now(timezone.utc).isoformat()
status = "succeeded" if result.returncode == 0 else "failed"
summary = {"status": status, "exit": result.returncode, "source": "getcolors", "warehouse": "clickhouse"}
s.patch(url, json={"status": status, "finished": finished, "exit": result.returncode, "safe_result": summary, "error_summary": "" if result.returncode == 0 else "Blue workflow failed; inspect journald for this unit"}, timeout=20).raise_for_status()
raise SystemExit(result.returncode)
