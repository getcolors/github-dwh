from __future__ import annotations

import json
import os
from pathlib import Path

from blue import tofu
from blue.ansible import ansible_with_spec
from blue.cli import stage_dir
from blue.runtime import runtime
from blue.scaffold import PRESERVE_JINJA_DELIMITERS

RESOURCE_ROOT = Path(__file__).parent / "resources"
PACKAGE_REVISION = "UNPINNED"
PLACEHOLDER_PUBLIC_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGl0aHViZHdoLXBsYWNlaG9sZGVy github-dwh-placeholder"


def tool_dir(opts: dict, tool: str) -> str:
    return stage_dir(opts, tool)


def runtime_project(opts: dict) -> str:
    override = os.environ.get("GITHUB_DWH_DBT_PROJECT")
    return override or "/opt/github-dwh/dbt"


def _template(path: str) -> dict:
    return {"name": path, "content": (RESOURCE_ROOT / path).read_text()}


def _spec(path: str, target: str, data: dict) -> dict:
    return {"template": _template(path), "target": target, "data": data, "opts": PRESERVE_JINJA_DELIMITERS}


def _state_root(opts: dict) -> Path:
    state_file = Path(str(opts.get("blue/state-file") or "colors.yml")).resolve()
    return state_file.parent


async def ensure_ssh_key(opts: dict) -> dict:
    private = Path(str(opts["ssh-private-key"]))
    if not private.is_absolute():
        private = _state_root(opts) / private
    public = Path(str(private) + ".pub")
    if not private.exists():
        private.parent.mkdir(parents=True, exist_ok=True)
        result = await runtime.exec(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", str(opts["vultr-ssh-key-name"]), "-f", str(private)])
        if result.exit:
            return {**opts, "blue/exit": result.exit, "blue/err": f"ssh-keygen failed: {result.err}"}
        private.chmod(0o600)
    return {**opts, "blue/exit": 0, "github-dwh/public-key": public.read_text().strip(), "github-dwh/private-key": str(private)}


def _terraform_data(opts: dict) -> dict:
    host = str(opts["control-plane-host"])
    zone = ".".join(host.rstrip(".").split(".")[-2:])
    return {**opts, "control-plane-zone": zone, "public-key-json": json.dumps(opts.get("github-dwh/public-key") or PLACEHOLDER_PUBLIC_KEY)}


async def tofu_infra(opts: dict) -> dict:
    directory = tool_dir(opts, "tofu")
    specs = [_spec("tofu/main.tf", f"{directory}/main.tf", _terraform_data(opts))]
    env = {"VULTR_API_KEY": str(opts.get("vultr-api-key") or ""), "CLOUDFLARE_API_TOKEN": str(opts.get("cloudflare-api-token") or "")}
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
    if not private:
        path = Path(str(opts["ssh-private-key"]))
        private = str(path if path.is_absolute() else _state_root(opts) / path)
    return {**opts, "server-ip": infra.get("ip") or "192.168.0.1", "github-dwh/private-key": private, "package-revision": os.environ.get("GITHUB_DWH_PACKAGE_REVISION", PACKAGE_REVISION)}


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
    inventory = f"[github_dwh]\ngithub-dwh ansible_host={data['server-ip']} ansible_user=root\n"
    specs.append({"target": f"{directory}/inventory.ini", "content": inventory, "data": {}})
    return specs


async def ansible_host(opts: dict) -> dict:
    directory, data = tool_dir(opts, "ansible"), _ansible_data(opts)
    result = await ansible_with_spec(opts, _ansible_specs(opts), dir=directory, inventory="inventory.ini", private_key=data["github-dwh/private-key"], playbooks={"create": "create.yml", "delete": "delete.yml"}, host_key_checking=False, extra_vars={"github_dwh_host": data["control-plane-host"]})
    return result
