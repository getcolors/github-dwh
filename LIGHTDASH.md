# Lightdash implementation and handoff

This document records the desired Lightdash feature, the implementation as of
2026-08-22, what is live, and what remains broken. It is intended to let another
agent resume without reconstructing the deployment history.

## Goal

Add a self-hosted analytics experience for the existing GitHub warehouse while
preserving the system's ownership boundaries:

- Blue/dlt/dbt runs the complete warehouse workflow.
- ClickHouse owns warehouse data.
- Lightdash provides the semantic layer, charts, and dashboards.
- PostgreSQL stores Lightdash metadata.
- PocketBase continues to schedule and record only whole Blue workflows.
- systemd supervises workflow processes; journald stores full logs.
- Git remains the desired-state source.

The analytics URL is:

- <https://analytics.github-dwh.bigconfig.space>

The initial dashboard is intended to show repository activity, commit counts,
workflow outcomes, and Package Skill metadata coverage across `getcolors`.

## Implemented architecture

Everything runs on the existing Vultr host.

- Lightdash `1.237.0`
- PostgreSQL `16.10-bookworm` for Lightdash metadata
- Cloudflare R2 for Lightdash's required S3-compatible object storage
  (desired state as of 2026-08-22; the last production convergence still ran
  the MinIO it replaced — see "R2 migration" below)
- ClickHouse `25.8`, shared with the warehouse
- A dedicated read-only ClickHouse user for Lightdash
- Caddy HTTPS reverse proxy
- Unproxied Cloudflare A record for the analytics host

The analytics DNS record must remain unproxied unless a Cloudflare certificate
that covers the two-label name is installed. Cloudflare Universal SSL does not
cover `analytics.github-dwh.bigconfig.space`; proxying it caused a TLS handshake
failure. Caddy obtains and serves the public certificate directly.

Persistent data is stored under:

- `/var/lib/github-dwh/lightdash-postgres`
- the R2 bucket named by `lightdash-r2-bucket` (previously
  `/var/lib/github-dwh/lightdash-minio` on the host)

The Compose and Ansible desired state is under:

- `src/package_github_dwh_blue/resources/runtime/docker-compose.yml`
- `src/package_github_dwh_blue/resources/ansible/create.yml`
- `src/package_github_dwh_blue/resources/tofu/main.tf`

## Implemented warehouse and semantic content

The dbt project now includes Lightdash metadata and these relevant marts:

- `marts.repository_health`
- `marts.package_skill_coverage`

The workflow runs Lightdash synchronization only after dbt models and tests
succeed. The synchronization implementation is:

- `src/package_github_dwh_blue/resources/runtime/lightdash_bootstrap.py`
- `src/package_github_dwh_blue/resources/runtime/lightdash_content.json`

The bootstrap is designed to be idempotent. It:

1. Creates or updates the read-only ClickHouse account.
2. Registers or logs in the Lightdash administrator.
3. Creates the `getcolors` organization when needed.
4. Creates or finds the `getcolors GitHub analytics` project.
5. Refreshes Lightdash's dbt metadata when the two marts exist.
6. Uploads the space, charts, and dashboard through Lightdash content-as-code
   APIs.

The control plane has an Analytics link and Lightdash, PostgreSQL, and MinIO log
sources. Documentation, validation, recovery instructions, fixtures, golden
files, and tests were also updated.

## Secrets

Secret values are in the ignored `github-dwh-vultr/.envrc.private`. Do not print,
commit, or copy their values into this document. The added variable names are
validated by the package and include credentials for:

- Lightdash administrator login
- Lightdash encryption
- Lightdash PostgreSQL
- Lightdash's read-only ClickHouse user
- Lightdash's R2 object storage (`COLORS_PAR_LIGHTDASH_R2_ACCESS_KEY_ID`,
  `COLORS_PAR_LIGHTDASH_R2_SECRET_ACCESS_KEY`; these replaced
  `COLORS_PAR_LIGHTDASH_S3_PASSWORD`)
- the R2 state backend (`COLORS_PAR_R2_ACCESS_KEY_ID`,
  `COLORS_PAR_R2_SECRET_ACCESS_KEY`) when `provider-backend` is `r2`

Use the existing deployment environment rather than creating replacement values
unless recovery explicitly requires rotation.

## What works now

The following was confirmed on the production host before the R2 migration
below; the MinIO items describe the configuration that was then live:

- Lightdash, PostgreSQL, and MinIO containers start.
- The MinIO bucket initialization completes.
- `https://analytics.github-dwh.bigconfig.space/api/v1/health` returns healthy
  for Lightdash `1.237.0`.
- Public HTTPS works after changing the analytics DNS record to unproxied and
  restarting Caddy.
- The Lightdash administrator can register/log in.
- The `getcolors` organization exists.
- The `getcolors GitHub analytics` project exists.
- Both required ClickHouse marts exist; `EXISTS TABLE` returned `1` for each.
- The dedicated ClickHouse access is converged by the bootstrap.
- Caddy is explicitly restarted during convergence so a changed mounted
  Caddyfile is loaded.
- Compose rendering validates.
- The package test suite passes: `12 passed`.
- Golden output checks pass.

## Current blocker

`./blue create` still fails at the Ansible task:

```text
Converge Lightdash project and dashboard
```

The task has `no_log: true`, so Ansible intentionally hides its output.

There were several successive causes during implementation:

1. Lightdash would not start because version `1.237.0` requires S3-compatible
   object storage. MinIO fixed this.
2. Bootstrap authentication over internal HTTP failed because secure session
   cookies are only sent over HTTPS. Bootstrap now uses the public HTTPS URL.
3. The nested analytics name could not use Cloudflare Universal SSL while
   proxied. The record is now unproxied.
4. Initial Lightdash registration created the user before creating an
   organization. Bootstrap now creates the organization.
5. Project creation response parsing expected `results.projectUuid`; the actual
   shape is `results.project.projectUuid`. This is fixed.
6. A project refresh job remained pending because `SCHEDULER_ENABLED` was
   `false`. It is now `true`.

After all of those fixes, the root cause surfaced on 2026-08-22 (7): Lightdash
runs the project's dbt compilation in a subprocess that does not inherit the
container environment, so `env_var('CLICKHOUSE_RAW_DATABASE')` in
`models/sources.yml` failed to render. The fix allowlists that variable through
`ALLOW_DBT_COMMANDS_ACCESS_TO_ENV_VARS` on the `lightdash` service. Allowlisted
values become viewer-visible explore metadata, so only the non-secret raw
database name is listed — never credentials.

`wait_for_job()` and the workflow's `_sync_lightdash` now include each job
step's `stepError` in their exception instead of the generic
`Lightdash dbt compilation failed`.

An earlier refresh job UUID observed while the scheduler was disabled was:

```text
c36287c9-aad9-4d40-9341-aaf9bf965949
```

It may be stale and should not be assumed to be the latest job.

The dashboard/content upload has not yet been confirmed. Do not report the
feature complete until the dashboard opens and queries ClickHouse successfully.

## R2 migration (2026-08-22, desired state only — not yet deployed)

The package now uses Cloudflare R2 twice, and neither use has been converged
to production yet:

1. **Lightdash object storage.** The MinIO and mc-init services are gone from
   the Compose desired state. Lightdash's `S3_ENDPOINT`, `S3_REGION`, and
   `S3_BUCKET` come from the new `lightdash-r2-bucket`,
   `lightdash-r2-endpoint`, and `lightdash-r2-region` keys; `S3_ACCESS_KEY`
   and `S3_SECRET_KEY` come from `COLORS_PAR_LIGHTDASH_R2_ACCESS_KEY_ID` and
   `COLORS_PAR_LIGHTDASH_R2_SECRET_ACCESS_KEY` via `/etc/github-dwh/environment`.
2. **OpenTofu state backend.** `provider-backend: r2` is now accepted and the
   deployment sets it, with the workspace's shared state bucket and the key
   `github-dwh-vultr/tofu.tfstate`. Credentials are
   `COLORS_PAR_R2_ACCESS_KEY_ID` / `COLORS_PAR_R2_SECRET_ACCESS_KEY`.

Before the next real `create`:

- Create the dedicated Lightdash bucket (deployment value:
  `github-dwh-lightdash`) in the same account/jurisdiction as its configured
  endpoint, and mint an R2 API token scoped to that bucket only.
- Add the four new `COLORS_PAR_*` values to `github-dwh-vultr/.envrc.private`
  and remove `COLORS_PAR_LIGHTDASH_S3_PASSWORD`.
- Migrate the existing local state: in
  `github-dwh-vultr/.colors/github-dwh-vultr/tofu/`, after a `./blue build`
  has rewritten `backend.tf.json`, run `tofu init -migrate-state` with
  `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` set to the state credentials. A
  plain `create` fails on the changed backend until the state is migrated.
- The first converge runs `docker compose up` with `--remove-orphans`, which
  stops the MinIO containers. `/var/lib/github-dwh/lightdash-minio` remains on
  disk; remove it manually once the dashboard is confirmed against R2. Chart
  artifacts in MinIO are regenerated caches/exports and are not migrated.

## Resume procedure

Work in `github-dwh/` for package changes and `github-dwh-vultr/` for deployment
state. Read each repository's `CLAUDE.md` first.

1. Load the ignored deployment environment without displaying it.
2. Obtain the Vultr host IP through the API or existing generated inventory.
3. Run the bootstrap directly over SSH so its traceback is visible:

   ```sh
   set -a
   . /etc/github-dwh/environment
   set +a
   LIGHTDASH_URL=https://analytics.github-dwh.bigconfig.space \
     /opt/github-dwh/.venv/bin/python \
     /opt/github-dwh/lightdash_bootstrap.py
   ```

4. Inspect Lightdash logs and current jobs:

   ```sh
   cd /opt/github-dwh
   docker compose ps
   docker compose logs --tail=300 lightdash
   ```

5. Modify `wait_for_job()` to include safe job status/error fields in its
   exception. Do not include credentials, request headers, or warehouse
   passwords. Inspect the response schema before deciding which fields are safe.
6. Fix the dbt refresh or content-as-code payload indicated by the error.
7. Run the direct bootstrap until it exits successfully and prints the project
   UUID.
8. Run `./blue create` again and require a successful complete convergence.
9. Open Lightdash in a browser, sign in, and verify:
   - the project is compiled;
   - the analytics space exists;
   - all charts render;
   - the repository overview dashboard renders and returns real values.
10. Trigger one complete workflow from PocketBase and verify the final
    Lightdash synchronization step succeeds.
11. Re-run package tests, golden checks, Compose validation, a clean Tofu plan,
    HTTPS/security checks, and accessibility checks.
12. Confirm both repositories are clean and match `origin/main`.

## Useful production checks

These avoid exposing secrets:

```sh
curl -fsS https://analytics.github-dwh.bigconfig.space/api/v1/health

cd /opt/github-dwh
docker compose ps
docker compose logs --tail=200 lightdash
docker compose logs --tail=100 lightdash-db
```

On the host, table existence can be checked with the credentials already loaded
from `/etc/github-dwh/environment`:

```sh
for table in repository_health package_skill_coverage; do
  curl -fsS -u "$CLICKHOUSE_USER:$CLICKHOUSE_PASSWORD" \
    "http://127.0.0.1:8123/?query=EXISTS%20TABLE%20marts.$table"
done
```

## Repository state at handoff

The runtime implementation is committed and pushed.

`github-dwh` relevant commits:

- `76cb46d` — enable Lightdash background compilation and complete bootstrap
  organization/project handling
- `56c9fb0` — route bootstrap through public HTTPS and use direct TLS DNS
- `211c81e` — add required Lightdash object storage
- `4c127ec` — initial Lightdash analytics implementation

The package launcher pin commit is `43e0cf7`.

`github-dwh-vultr` is pushed at `f898c61`, with the installed launcher pointing
to package revision `76cb46d`.

A launcher pinning bug discovered during deployment was fixed in `5b26de6`:
`scripts/pin.py` now reads the Blue revision from `pyproject.toml` instead of the
unrelated current HEAD of the sibling `blue/` checkout.

## Separate unresolved issue

The earlier intermittent control-plane message

```text
The run was not queued. The github-getcolors pipeline is not registered.
```

has not been closed end to end. The PocketBase API did return a registered
`github-getcolors` pipeline during diagnosis. After Lightdash is complete, run a
manual workflow from the UI to reproduce or close this issue and verify the new
Lightdash sync step in the same run.
