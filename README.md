# github-dwh

A Blue Package Skill that provisions and operates a single-host warehouse for every repository accessible to a GitHub organization credential:

- ClickHouse stores raw GitHub records and dbt models;
- dlt extracts repositories, commits, organization events, Actions runs, and Package Skill manifests;
- dbt-clickhouse builds repository-health marts;
- PocketBase provides authenticated schedules, run-now, cancellation requests, and run history;
- a fixed systemd timer dispatches complete Blue workflow invocations.

PocketBase is not the workflow engine. One run record maps to one `./blue run`; Blue owns `extract -> transform -> test`, systemd owns process supervision, and journald owns full logs.

```sh
./blue build
./blue create --dry-run
./blue create
./blue run
./blue delete
```

Desired state is `colors.yml`; secrets are matching `COLORS_PAR_*` variables. Generated `.colors/` output and OpenTofu state must not be committed. Operators start recurring or manual production loads through PocketBase; the installed host launcher executes them under transient systemd units. See [RECOVERY.md](RECOVERY.md) for backup, rebuild, rotation, and diagnostic procedures.
