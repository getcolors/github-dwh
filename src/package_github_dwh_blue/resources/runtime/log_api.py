#!/usr/bin/env python3
"""Authenticated, read-only journald gateway for the GitHub DWH control plane."""
from __future__ import annotations

import json
import os
import re
import socketserver
import subprocess
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import requests

POCKETBASE_URL = os.environ.get("POCKETBASE_URL", "http://127.0.0.1:8090")
SOCKET_PATH = Path(os.environ.get("LOG_API_SOCKET", "/run/github-dwh/log-api.sock"))
MAX_LINES = 2000
SOURCES = {
    "dispatcher": ("unit", "github-dwh-dispatch.service"),
    "docker": ("unit", "docker.service"),
    "caddy": ("container", "github-dwh-caddy-1"),
    "pocketbase": ("container", "github-dwh-pocketbase-1"),
    "clickhouse": ("container", "github-dwh-clickhouse-1"),
}
PRIORITIES = {"0": "emergency", "1": "alert", "2": "critical", "3": "error", "4": "warning", "5": "notice", "6": "info", "7": "debug"}
SECRET_KEYS = ("COLORS_PAR_GITHUB_TOKEN", "COLORS_PAR_CLICKHOUSE_PASSWORD", "CLICKHOUSE_PASSWORD", "COLORS_PAR_POCKETBASE_SUPERUSER_PASSWORD")
SECRET_VALUES = tuple(value for key in SECRET_KEYS if (value := os.environ.get(key)))
REDACTIONS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)((?:password|passwd|token|secret|api[_-]?key)\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"\b(?:github_pat_|gh[oprsu]_)[A-Za-z0-9_]{12,}\b"),
)


def redact(value: object) -> str:
    text = str(value or "")
    for secret in SECRET_VALUES:
        text = text.replace(secret, "[REDACTED]")
    for pattern in REDACTIONS:
        text = pattern.sub(lambda match: (match.group(1) if match.lastindex else "") + "[REDACTED]", text)
    return text


def authenticated(token: str) -> bool:
    if not token:
        return False
    try:
        response = requests.post(
            f"{POCKETBASE_URL}/api/collections/_superusers/auth-refresh",
            headers={"Authorization": token},
            timeout=10,
        )
        return response.ok
    except requests.RequestException:
        return False


def run_selector(run_id: str, token: str) -> tuple[str, str] | None:
    if not re.fullmatch(r"[A-Za-z0-9]{15}", run_id):
        return None
    try:
        response = requests.get(
            f"{POCKETBASE_URL}/api/collections/runs/records/{run_id}",
            headers={"Authorization": token},
            timeout=10,
        )
        if not response.ok:
            return None
        unit = response.json().get("systemd_unit")
    except (requests.RequestException, ValueError):
        return None
    expected = f"github-dwh-run-{run_id}.service"
    return ("unit", unit) if unit == expected else None


def journal_command(selector: tuple[str, str], limit: int, before: int | None = None, after: int | None = None) -> list[str]:
    command = ["journalctl", "--quiet", "--output=json", "--no-pager", "--reverse", "-n", str(limit + 1)]
    kind, value = selector
    command.extend(["--unit", value] if kind == "unit" else [f"CONTAINER_NAME={value}"])
    if before:
        command.extend(["--until", f"@{max(0, before - 1) / 1_000_000:.6f}"])
    if after:
        command.extend(["--since", f"@{(after + 1) / 1_000_000:.6f}"])
    return command


def read_logs(selector: tuple[str, str], limit: int, before: int | None = None, after: int | None = None) -> dict:
    result = subprocess.run(journal_command(selector, limit, before, after), text=True, capture_output=True, timeout=20, check=False)
    if result.returncode not in (0, 1):
        raise RuntimeError(redact(result.stderr.strip() or "journalctl failed"))
    parsed = []
    for raw in result.stdout.splitlines():
        try:
            row = json.loads(raw)
            cursor = int(row.get("__REALTIME_TIMESTAMP", 0))
        except (ValueError, TypeError, json.JSONDecodeError):
            continue
        if after and cursor <= after:
            continue
        parsed.append({
            "cursor": cursor,
            "timestamp": datetime.fromtimestamp(cursor / 1_000_000, timezone.utc).isoformat(),
            "message": redact(row.get("MESSAGE", "")),
            "priority": PRIORITIES.get(str(row.get("PRIORITY", "6")), "info"),
            "stream": redact(row.get("SYSLOG_IDENTIFIER") or row.get("CONTAINER_NAME") or row.get("_COMM") or "process"),
        })
    has_more = not after and len(parsed) > limit
    parsed = parsed[:limit]
    parsed.sort(key=lambda line: line["cursor"])
    return {"lines": parsed, "has_more": has_more, "before": parsed[0]["cursor"] if parsed else None}


class LogHandler(BaseHTTPRequestHandler):
    server_version = "github-dwh-logs"

    def log_message(self, _format, *_args):
        return

    def send_json(self, status: HTTPStatus, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        authorization = self.headers.get("Authorization", "")
        token = authorization.removeprefix("Bearer ").strip()
        if not authenticated(token):
            self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "A valid PocketBase superuser session is required."})
            return
        parsed = urlparse(self.path)
        parts = [unquote(part) for part in parsed.path.strip("/").split("/")]
        selector = None
        label = None
        if len(parts) == 4 and parts[:3] == ["control", "logs", "runs"]:
            selector = run_selector(parts[3], token)
            label = f"Run {parts[3]}"
        elif len(parts) == 4 and parts[:3] == ["control", "logs", "sources"] and parts[3] in SOURCES:
            selector = SOURCES[parts[3]]
            label = parts[3].capitalize()
        if not selector:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Log source not found."})
            return
        query = parse_qs(parsed.query)
        try:
            limit = min(MAX_LINES, max(1, int(query.get("limit", [MAX_LINES])[0])))
            before = int(query["before"][0]) if query.get("before") else None
            after = int(query["after"][0]) if query.get("after") else None
        except (ValueError, TypeError):
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid log cursor or limit."})
            return
        try:
            body = read_logs(selector, limit, before, after)
            self.send_json(HTTPStatus.OK, {"source": label, **body})
        except (OSError, subprocess.SubprocessError, RuntimeError) as error:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": redact(error)})


class UnixHTTPServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def main() -> None:
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    SOCKET_PATH.unlink(missing_ok=True)
    with UnixHTTPServer(str(SOCKET_PATH), LogHandler) as server:
        SOCKET_PATH.chmod(0o666)
        server.serve_forever()


if __name__ == "__main__":
    main()
