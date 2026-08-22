from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from blue import dry_run, progress, tofu
from blue.cli import par_name, read_pars
from blue.lifecycle import preflight
from blue.runtime import runtime
from blue.workflow import advice_add, workflow

from . import tools
from .extract import load
from .validate import secret_errors, state_errors


async def start_step(original: dict) -> dict:
    async def after(opts, _env, context):
        if context["real"] and context["event"] == "create":
            return await tools.ensure_ssh_key(opts)
        return {**opts, "blue/exit": 0, "github-dwh/public-key": tools.PLACEHOLDER_PUBLIC_KEY}

    def safety(opts, _env, context):
        if context["real"] and context["event"] == "delete" and opts.get("compute-prevent-destroy"):
            return [f"compute destruction is protected; set {par_name('compute-prevent-destroy')}=false to delete"]
        return []

    return await preflight(original, defaults={"compute-prevent-destroy": True, "provider-compute": "vultr", "provider-dns": "cloudflare", "provider-backend": "local"}, overlay=read_pars, validators=[lambda o, _e, _c: state_errors(o), lambda o, _e, c: secret_errors(o, c["event"]) if c["real"] and c["event"] in ("create", "delete", "run") else [], safety], after_validate=after)


async def tofu_step(opts: dict) -> dict:
    result = await tools.tofu_infra(opts)
    if opts.get("blue/event") == "build" or (result.get("blue/exit") or 0) > 0:
        return {**result, "github-dwh/infra": {"ip": "192.168.0.1"}}
    if opts.get("blue/event") == "delete":
        return result
    return {**result, "github-dwh/infra": (result.get("tofu/outputs") or {}).get("infra", {})}


async def ansible_step(opts: dict) -> dict:
    return await tools.ansible_host(opts)


async def dlt_step(opts: dict) -> dict:
    try:
        summary = await asyncio.to_thread(load, dict(opts))
        return {**opts, "blue/exit": 0, "github-dwh/load": summary}
    except Exception as exc:
        return {**opts, "blue/exit": 1, "blue/err": f"dlt load failed: {exc}"}


async def dbt_step(opts: dict, command: str) -> dict:
    project = tools.runtime_project(opts)
    env = {"CLICKHOUSE_USER": str(opts["clickhouse-user"]), "CLICKHOUSE_PASSWORD": str(opts["clickhouse-password"]), "CLICKHOUSE_RAW_DATABASE": str(opts["clickhouse-raw-database"]), "CLICKHOUSE_ANALYTICS_DATABASE": str(opts["clickhouse-analytics-database"]), "CLICKHOUSE_MARTS_DATABASE": str(opts["clickhouse-marts-database"])}
    dbt = str(Path(sys.executable).with_name("dbt"))
    result = await runtime.exec([dbt, command, "--project-dir", project, "--profiles-dir", project], env=env)
    if result.exit:
        return {**opts, "blue/exit": result.exit, "blue/err": f"dbt {command} failed: {result.err or result.out}"}
    return {**opts, "blue/exit": 0, f"github-dwh/dbt-{command}": "succeeded"}


async def dbt_run_step(opts): return await dbt_step(opts, "run")
async def dbt_test_step(opts): return await dbt_step(opts, "test")


def wire_fn(step: str, run_opts: dict):
    event = run_opts.get("blue/event")
    if event == "run":
        return {"github-dwh/start": (start_step, "github-dwh/dlt"), "github-dwh/dlt": (dlt_step, "github-dwh/dbt-run"), "github-dwh/dbt-run": (dbt_run_step, "github-dwh/dbt-test"), "github-dwh/dbt-test": (dbt_test_step,)}.get(step)
    if event == "delete":
        return {"github-dwh/start": (start_step, "github-dwh/ansible"), "github-dwh/ansible": (ansible_step, "github-dwh/tofu"), "github-dwh/tofu": (tofu_step,)}.get(step)
    return {"github-dwh/start": (start_step, "github-dwh/tofu"), "github-dwh/tofu": (tofu_step, "github-dwh/ansible"), "github-dwh/ansible": (ansible_step,)}.get(step)


def create_workflow():
    wf = workflow(start="github-dwh/start", wire_fn=wire_fn)
    wf = advice_add(wf, "github-dwh/tofu", "before", "github-dwh/backend", tofu.local_backend_advice(lambda o: tools.tool_dir(o, "tofu")))
    wf = progress.advise(wf)
    return dry_run.advise(wf, ["github-dwh/tofu", "github-dwh/ansible", "github-dwh/dlt", "github-dwh/dbt-run", "github-dwh/dbt-test"])


github_dwh_workflow = create_workflow()
