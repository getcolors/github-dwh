# CLAUDE.md

## Repository

`github-dwh` is a Blue Package Skill for a single-host GitHub organization warehouse. OpenTofu provisions one Vultr VM and Cloudflare DNS; Ansible converges ClickHouse, PocketBase, Caddy, a systemd dispatcher, and the Blue/dlt/dbt runtime. Git owns desired state and the workflow graph. PocketBase owns schedules and whole-run history only.

## Commands

```sh
uv sync
uv run pytest
./scripts/golden.sh
./scripts/launcher.sh
./blue build
./blue create --dry-run
```

Never read `.envrc.private`, edit `.colors/`, export `COLORS_PAR_PROFILE`, or weaken `compute-prevent-destroy`. Real create/delete requires explicit authorization. `run` loads GitHub data and is a real external side effect unless `--dry-run` is present.

## Boundaries

One PocketBase run is one `./blue run`. PocketBase must never acquire task DAGs, per-step queues, sensors, XCom-like values, or retry policy. systemd supervises processes; Blue owns workflow routing; journald owns full logs.

## Git

Work on the current branch. Do not commit or push unless explicitly authorized.
