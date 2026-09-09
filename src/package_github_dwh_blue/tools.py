from __future__ import annotations

import os
from pathlib import Path

from blue import tofu
from blue.ansible import ansible_with_spec
from blue.cli import stage_dir
from blue.scaffold import PRESERVE_JINJA_DELIMITERS

RESOURCE_ROOT = Path(__file__).parent / "resources"
PACKAGE_REVISION = "UNPINNED"


def tool_dir(opts: dict, tool: str) -> str:
    return stage_dir(opts, tool)


def runtime_project(opts: dict) -> str:
    override = os.environ.get("GITHUB_DWH_DBT_PROJECT")
    return override or "/opt/github-dwh/dbt"


def _template(path: str) -> dict:
    return {"name": path, "content": (RESOURCE_ROOT / path).read_text()}


def _spec(path: str, target: str, data: dict) -> dict:
    return {"template": _template(path), "target": target, "data": data, "opts": PRESERVE_JINJA_DELIMITERS}


def _terraform_data(opts: dict) -> dict:
    host = str(opts["control-plane-host"])
    zone = ".".join(host.rstrip(".").split(".")[-2:])
    return {**opts, "control-plane-zone": zone, "server-ip": _infra(opts)["ip"]}


async def tofu_infra(opts: dict) -> dict:
    if opts.get("github-dwh/already-destroyed"):
        return opts
    directory = tool_dir(opts, "dns")
    specs = [_spec("dns/main.tf", f"{directory}/main.tf", _terraform_data(opts))]
    env = {"CLOUDFLARE_API_TOKEN": str(opts.get("cloudflare-api-token") or "")}
    if opts.get("provider-backend") == "r2":
        # R2 state authenticates through the AWS chain; naming the credentials
        # in backend.tf.json would persist them under .terraform/.
        env["AWS_ACCESS_KEY_ID"] = str(opts.get("r2-access-key-id") or "")
        env["AWS_SECRET_ACCESS_KEY"] = str(opts.get("r2-secret-access-key") or "")
    return await tofu.tofu_with_spec(opts, specs, dir=directory, env=env)


def _infra(opts: dict) -> dict:
    return (opts.get("github-dwh/infra") or {})


def _ansible_data(opts: dict) -> dict:
    infra = _infra(opts)
    private = opts.get("github-dwh/private-key")
    if not infra.get("ip") or not infra.get("user"):
        raise ValueError("compute connection parameters unavailable")
    return {**opts, "server-ip": infra["ip"], "server-user": infra["user"], "github-dwh/private-key": private, "package-revision": os.environ.get("GITHUB_DWH_PACKAGE_REVISION", PACKAGE_REVISION)}



def _ansible_specs(opts: dict) -> list[dict]:
    directory, data = tool_dir(opts, "ansible"), _ansible_data(opts)
    targets = {
        "ansible/ansible.cfg": "ansible.cfg", "ansible/create.yml": "create.yml", "ansible/delete.yml": "delete.yml",
        "runtime/docker-compose.yml": "files/docker-compose.yml", "runtime/Dockerfile.pocketbase": "files/Dockerfile.pocketbase", "runtime/Caddyfile": "files/Caddyfile",
        "runtime/dispatcher.py": "files/dispatcher.py", "runtime/log_api.py": "files/log_api.py", "runtime/lightdash_bootstrap.py": "files/lightdash_bootstrap.py", "runtime/lightdash_content.json": "files/lightdash_content.json",
        "runtime/run.py": "files/run.py", "runtime/bootstrap.py": "files/bootstrap.py",
        "runtime/github-dwh-dispatch.service": "files/github-dwh-dispatch.service", "runtime/github-dwh-dispatch.timer": "files/github-dwh-dispatch.timer",
        "runtime/github-dwh-blue.service": "files/github-dwh-blue.service", "runtime/github-dwh-logs.service": "files/github-dwh-logs.service",
        "runtime/colors.yml": "files/colors.yml", "runtime/index.html": "files/index.html",
        "dbt/dbt_project.yml": "files/dbt/dbt_project.yml", "dbt/profiles.yml": "files/dbt/profiles.yml", "dbt/macros/generate_schema_name.sql": "files/dbt/macros/generate_schema_name.sql",
        "dbt/models/sources.yml": "files/dbt/models/sources.yml", "dbt/models/staging/stg_repositories.sql": "files/dbt/models/staging/stg_repositories.sql",
        "dbt/models/staging/stg_commits.sql": "files/dbt/models/staging/stg_commits.sql", "dbt/models/staging/stg_workflow_runs.sql": "files/dbt/models/staging/stg_workflow_runs.sql",
        "dbt/models/staging/stg_package_skills.sql": "files/dbt/models/staging/stg_package_skills.sql", "dbt/models/marts/repository_health.sql": "files/dbt/models/marts/repository_health.sql",
        "dbt/models/marts/package_skill_coverage.sql": "files/dbt/models/marts/package_skill_coverage.sql", "dbt/models/marts/schema.yml": "files/dbt/models/marts/schema.yml",
    }
    specs = [_spec(path, f"{directory}/{target}", data) for path, target in targets.items()]
    inventory = f"[github_dwh]\ngithub-dwh ansible_host={data['server-ip']} ansible_user={data['server-user']}\n"
    specs.append({"target": f"{directory}/inventory.ini", "content": inventory, "data": {}})
    return specs


async def ansible_host(opts: dict) -> dict:
    if opts.get("github-dwh/already-destroyed"):
        return opts
    directory, data = tool_dir(opts, "ansible"), _ansible_data(opts)
    result = await ansible_with_spec(opts, _ansible_specs(opts), dir=directory, inventory="inventory.ini", private_key=data["github-dwh/private-key"], playbooks={"create": "create.yml", "delete": "delete.yml"}, host_key_checking=False, extra_vars={"github_dwh_host": data["control-plane-host"]})
    return result


async def ansible_local_step(opts):
    if opts.get('github-dwh/already-destroyed'):
        return opts
    directory = tool_dir(opts, 'ansible-local')
    data = {**opts, 'ssh-keygen': opts.get('colors-compute/key', {}).get('mode') == 'managed'}
    node = _infra(opts)
    specs = [_spec('ansible-local/' + name, directory + '/' + name, data) for name in ['ansible.cfg', 'inventory.ini', 'main.yml']]
    return await ansible_with_spec(opts, specs, dir=directory, inventory='inventory.ini', playbooks={'create':'main.yml','delete':'main.yml'}, extra_vars={'host_alias':opts['profile'],'ip':node['ip'],'user':node['user'],'block_state':'absent' if opts.get('blue/event')=='delete' else 'present'})
