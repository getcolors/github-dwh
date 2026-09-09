# github-dwh

A Blue Package Skill that provisions and operates a single-host warehouse for every repository accessible to a GitHub organization credential:

- ClickHouse stores raw GitHub records and dbt models;
- dlt extracts repositories, commits, organization events, Actions runs, and Package Skill manifests;
- dbt-clickhouse builds repository-health marts;
- PocketBase provides authenticated schedules, run-now, cancellation requests, and run history;
- Lightdash serves repository, workflow, commit, and Package Skill analytics from read-only ClickHouse marts;
- a fixed systemd timer dispatches complete Blue workflow invocations.

PocketBase is not the workflow engine. One run record maps to one `./blue run`; Blue owns `extract -> transform -> test -> Lightdash sync`, systemd owns process supervision, and journald owns full logs.

```sh
./blue build
./blue create --dry-run
./blue create
./blue run
./blue delete
```

The control plane is served from `github-dwh.bigconfig.space` and analytics from `analytics.github-dwh.bigconfig.space`. Desired state is `colors.yml`; secrets are matching `COLORS_PAR_*` variables. The `colors-compute` library owns singleton compute, provider-backed daily backups, disabled IPv6, SSH keys and remote R2/S3 state. Compute uses `<profile>/compute/shared.tfstate` and `<profile>/compute/nodes/0.tfstate`; DNS uses `<profile>/dns.tfstate`. Managed SSH keys are profile-named under `~/.ssh/`. Cloudflare R2 also holds Lightdash's object storage (a dedicated bucket with separately scoped credentials). Generated `.colors/` output must not be committed. Operators start recurring or manual production loads through PocketBase; the installed host launcher executes them under transient systemd units. See [RECOVERY.md](RECOVERY.md) for backup, rebuild, rotation, and diagnostic procedures. The current Lightdash implementation status and resume procedure are recorded in [LIGHTDASH.md](LIGHTDASH.md).

Existing combined `<profile>/tofu.tfstate` deployments require an explicit reviewed migration. Normal create/delete refuses that state instead of guessing ownership or recreating resources. The current backup/IPv6 capability is implemented for Vultr; other provider selections fail until the library supplies those requested capabilities.
