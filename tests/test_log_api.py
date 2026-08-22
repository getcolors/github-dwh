import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


MODULE = Path(__file__).parents[1] / "src/package_github_dwh_blue/resources/runtime/log_api.py"
spec = importlib.util.spec_from_file_location("github_dwh_log_api", MODULE)
log_api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(log_api)


def test_redact_replaces_environment_and_credential_shapes(monkeypatch):
    monkeypatch.setattr(log_api, "SECRET_VALUES", ("exact-secret-value",))
    text = "token=abc123 password: hidden exact-secret-value github_pat_abcdefghijklmnopqrstuvwxyz"
    redacted = log_api.redact(text)
    assert "abc123" not in redacted
    assert "hidden" not in redacted
    assert "exact-secret-value" not in redacted
    assert "github_pat_" not in redacted
    assert redacted.count("[REDACTED]") == 4


def test_journal_command_restricts_selector_and_cursors():
    command = log_api.journal_command(("unit", "github-dwh-run-abc.service"), 20, before=2_000_000, after=1_000_000)
    assert command[command.index("--unit") + 1] == "github-dwh-run-abc.service"
    assert command[command.index("-n") + 1] == "21"
    assert command[command.index("--until") + 1] == "@1.999999"
    assert command[command.index("--since") + 1] == "@1.000001"


def test_read_logs_orders_redacts_and_reports_older(monkeypatch):
    rows = [
        {"__REALTIME_TIMESTAMP": "3000000", "MESSAGE": "done", "PRIORITY": "6", "SYSLOG_IDENTIFIER": "python"},
        {"__REALTIME_TIMESTAMP": "2000000", "MESSAGE": "password=unsafe", "PRIORITY": "3", "SYSLOG_IDENTIFIER": "python"},
        {"__REALTIME_TIMESTAMP": "1000000", "MESSAGE": "older", "PRIORITY": "4", "SYSLOG_IDENTIFIER": "python"},
    ]
    monkeypatch.setattr(log_api.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="\n".join(json.dumps(row) for row in rows), stderr=""))
    result = log_api.read_logs(("unit", "example.service"), 2)
    assert result["has_more"] is True
    assert [line["cursor"] for line in result["lines"]] == [2_000_000, 3_000_000]
    assert result["lines"][0]["priority"] == "error"
    assert "unsafe" not in result["lines"][0]["message"]


def test_run_selector_only_accepts_record_unit(monkeypatch):
    response = SimpleNamespace(ok=True, json=lambda: {"systemd_unit": "github-dwh-run-abcdefghijklmno.service"})
    monkeypatch.setattr(log_api.requests, "get", lambda *args, **kwargs: response)
    assert log_api.run_selector("abcdefghijklmno", "token") == ("unit", "github-dwh-run-abcdefghijklmno.service")
    assert log_api.run_selector("../docker", "token") is None
