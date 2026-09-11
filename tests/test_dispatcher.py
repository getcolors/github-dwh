import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests


RUNTIME = Path(__file__).parents[1] / "src/package_github_dwh_blue/resources/runtime"


def load(name):
    spec = importlib.util.spec_from_file_location(f"github_dwh_{name}", RUNTIME / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dispatcher = load("dispatcher")
worker = load("run")
NOW = datetime.now(timezone.utc)


@pytest.fixture
def warehouse(monkeypatch):
    rows = {
        "old": {"id": "old", "pipeline": "github", "status": "launching", "started": (NOW - timedelta(minutes=5)).isoformat()},
        "next": {"id": "next", "pipeline": "github", "status": "queued"},
    }

    def records(collection, **params):
        if collection == "schedules":
            return []
        query = params["filter"]
        if query.startswith('id="'):
            return [dict(rows[query[4:-1]])]
        return [dict(row) for row in rows.values() if f'status="{row["status"]}"' in query]

    def patch(collection, rid, body):
        rows[rid].update(body)
        return dict(rows[rid])

    monkeypatch.setattr(dispatcher, "records", records)
    monkeypatch.setattr(dispatcher, "patch", patch)
    monkeypatch.setattr(dispatcher, "s", SimpleNamespace(headers={}, post=lambda *a, **kw: response()))
    monkeypatch.setenv("POCKETBASE_SUPERUSER_EMAIL", "test@example.com")
    monkeypatch.setenv("COLORS_PAR_POCKETBASE_SUPERUSER_PASSWORD", "test-password")
    return rows


def response():
    return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"token": "test"})


@pytest.mark.parametrize("status", ["launching", "running"])
@pytest.mark.parametrize("load_state,state", [("not-found", "inactive"), ("loaded", "failed"), ("loaded", "inactive")])
def test_dead_worker_releases_pipeline_and_launches_next(monkeypatch, warehouse, status, load_state, state):
    warehouse["old"]["status"] = status
    commands = []

    def command(args, **kwargs):
        commands.append(args)
        return SimpleNamespace(returncode=0, stdout=f"LoadState={load_state}\nActiveState={state}\n", stderr="")

    monkeypatch.setattr(dispatcher.subprocess, "run", command)
    dispatcher.main()
    assert warehouse["old"]["status"] == "failed"
    assert warehouse["old"]["finished"]
    assert warehouse["next"]["status"] == "launching"
    assert warehouse["next"]["started"]
    launch = next(cmd for cmd in commands if cmd[0] == "systemd-run")
    assert "--property=KillMode=control-group" in launch
    assert "--property=TimeoutStopSec=30s" in launch
    # A second timer tick must respect the newly launched worker's grace.
    dispatcher.main()
    assert sum(cmd[0] == "systemd-run" for cmd in commands) == 1
    assert warehouse["next"]["status"] == "launching"


@pytest.mark.parametrize("state", ["active", "activating", "deactivating", "reloading", None])
def test_existing_or_unknown_worker_holds_pipeline(monkeypatch, warehouse, state):
    monkeypatch.setattr(dispatcher, "unit_state", lambda unit: state)
    launch = Mock()
    monkeypatch.setattr(dispatcher.subprocess, "run", launch)
    dispatcher.main()
    assert warehouse["old"]["status"] == "launching"
    assert warehouse["next"]["status"] == "queued"
    launch.assert_not_called()


def test_launch_grace_expires(monkeypatch, warehouse):
    warehouse["old"]["started"] = NOW.isoformat()
    monkeypatch.setattr(dispatcher, "unit_state", lambda unit: "inactive")
    assert dispatcher.reconcile(NOW + timedelta(seconds=119)) == {"github"}
    assert dispatcher.reconcile(NOW + timedelta(seconds=120)) == set()
    assert warehouse["old"]["status"] == "failed"


@pytest.mark.parametrize("started", ["", "invalid", None])
def test_legacy_or_invalid_launch_time_is_recovered(monkeypatch, warehouse, started):
    warehouse["old"]["started"] = started
    monkeypatch.setattr(dispatcher, "unit_state", lambda unit: "inactive")
    assert dispatcher.reconcile(NOW) == set()
    assert warehouse["old"]["status"] == "failed"


def test_worker_terminal_write_during_check_is_preserved(monkeypatch, warehouse):
    def state(unit):
        warehouse["old"]["status"] = "succeeded"
        return "inactive"

    monkeypatch.setattr(dispatcher, "unit_state", state)
    assert dispatcher.reconcile(NOW) == set()
    assert warehouse["old"]["status"] == "succeeded"


@pytest.mark.parametrize("status", ["launching", "running"])
def test_cancel_waits_for_whole_unit_to_stop(monkeypatch, warehouse, status):
    warehouse["old"].update(status=status, cancellation_requested=True, started=NOW.isoformat())
    states = iter(["active", "inactive"])
    monkeypatch.setattr(dispatcher, "unit_state", lambda unit: next(states))
    stop = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(dispatcher.subprocess, "run", stop)
    assert dispatcher.reconcile(NOW) == set()
    assert warehouse["old"]["status"] == "canceled"
    assert warehouse["old"]["exit"] == 143
    assert stop.call_args.args[0] == ["systemctl", "stop", "github-dwh-run-old.service"]


@pytest.mark.parametrize("failure", ["exit", "timeout", "missing", "still-active", "unknown"])
def test_cancellation_failure_keeps_pipeline_blocked(monkeypatch, warehouse, failure):
    warehouse["old"]["cancellation_requested"] = True
    states = iter(["active", None if failure == "unknown" else "deactivating"])
    monkeypatch.setattr(dispatcher, "unit_state", lambda unit: next(states))

    def stop(*args, **kwargs):
        if failure == "timeout":
            raise dispatcher.subprocess.TimeoutExpired(args[0], 45)
        if failure == "missing":
            raise OSError("systemctl unavailable")
        return SimpleNamespace(returncode=1 if failure == "exit" else 0)

    monkeypatch.setattr(dispatcher.subprocess, "run", stop)
    assert dispatcher.reconcile(NOW) == {"github"}
    assert warehouse["old"]["status"] == "launching"


@pytest.mark.parametrize("result", [
    SimpleNamespace(returncode=1, stdout="LoadState=loaded\nActiveState=inactive\n"),
    SimpleNamespace(returncode=0, stdout=""),
    SimpleNamespace(returncode=0, stdout="LoadState=error\nActiveState=inactive\n"),
    OSError("bus unavailable"),
    dispatcher.subprocess.TimeoutExpired("systemctl", 20),
])
def test_systemd_query_errors_are_unknown(monkeypatch, result):
    def command(*args, **kwargs):
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(dispatcher.subprocess, "run", command)
    assert dispatcher.unit_state("example.service") is None


@pytest.fixture
def worker_session(monkeypatch, warehouse):
    session = SimpleNamespace(headers={}, post=Mock(return_value=response()), patch=Mock(return_value=response()))
    monkeypatch.setattr(worker.requests, "Session", lambda: session)
    return session


def test_authentication_failure_is_recovered_next_dispatch(monkeypatch, warehouse, worker_session):
    worker_session.post.side_effect = requests.HTTPError("authentication unavailable")
    workflow = Mock()
    monkeypatch.setattr(worker.subprocess, "run", workflow)
    with pytest.raises(requests.HTTPError):
        worker.main("old")
    workflow.assert_not_called()
    worker_session.patch.assert_not_called()
    monkeypatch.setattr(dispatcher, "unit_state", lambda unit: "inactive")
    assert dispatcher.reconcile(NOW) == set()
    assert warehouse["old"]["status"] == "failed"


def test_workflow_spawn_failure_records_failure(monkeypatch, worker_session):
    monkeypatch.setattr(worker.subprocess, "run", Mock(side_effect=FileNotFoundError("python missing")))
    with pytest.raises(FileNotFoundError):
        worker.main("old")
    assert worker_session.patch.call_args.kwargs["json"]["status"] == "failed"


def test_running_status_write_failure_does_not_start_workflow(monkeypatch, worker_session):
    worker_session.patch.side_effect = requests.ConnectionError("database unavailable")
    workflow = Mock()
    monkeypatch.setattr(worker.subprocess, "run", workflow)
    with pytest.raises(requests.ConnectionError):
        worker.main("old")
    workflow.assert_not_called()


def test_terminal_write_failure_is_recovered(monkeypatch, warehouse, worker_session):
    warehouse["old"]["status"] = "running"
    worker_session.patch.side_effect = [response(), requests.ConnectionError("database unavailable")]
    monkeypatch.setattr(worker.subprocess, "run", Mock(return_value=SimpleNamespace(returncode=0)))
    with pytest.raises(requests.ConnectionError):
        worker.main("old")
    monkeypatch.setattr(dispatcher, "unit_state", lambda unit: "inactive")
    assert dispatcher.reconcile(NOW) == set()
    assert warehouse["old"]["status"] == "failed"


@pytest.mark.parametrize("code,status", [(0, "succeeded"), (7, "failed")])
def test_worker_records_workflow_result(monkeypatch, worker_session, code, status):
    monkeypatch.setattr(worker.subprocess, "run", Mock(return_value=SimpleNamespace(returncode=code)))
    assert worker.main("old") == code
    result = worker_session.patch.call_args.kwargs["json"]
    assert result["status"] == status
    assert result["exit"] == code


def test_legacy_recent_creation_gets_launch_grace(monkeypatch, warehouse):
    warehouse["old"].update(started="", created=NOW.isoformat())
    monkeypatch.setattr(dispatcher, "unit_state", lambda unit: "inactive")
    assert dispatcher.reconcile(NOW) == {"github"}
    assert dispatcher.reconcile(NOW + timedelta(minutes=3)) == set()


def test_mutable_unit_name_cannot_stop_another_service(monkeypatch, warehouse):
    warehouse["old"].update(systemd_unit="docker.service", cancellation_requested=True)
    commands = []

    def command(args, **kwargs):
        commands.append(args)
        state = "inactive" if len(commands) == 3 else "active"
        return SimpleNamespace(returncode=0, stdout=f"LoadState=loaded\nActiveState={state}\n")

    monkeypatch.setattr(dispatcher.subprocess, "run", command)
    assert dispatcher.reconcile(NOW) == set()
    assert len(commands) == 3
    assert all("github-dwh-run-old.service" in cmd for cmd in commands)
    assert all("docker.service" not in cmd for cmd in commands)
