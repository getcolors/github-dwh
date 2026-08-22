# Implementation plan

## Goal

Deliver `github-dwh` as a Blue Package Skill and `github-dwh-vultr` as its live single-host deployment at `github-dwh.bigconfig.space`.

## Architecture

1. OpenTofu manages one Vultr instance, its dedicated SSH key, firewall, and the Cloudflare A record.
2. Ansible installs Docker, ClickHouse, PocketBase, Caddy, the application runtime, and two systemd timers.
3. The dispatcher timer translates PocketBase schedules and queued manual requests into transient systemd units.
4. A run wrapper records provenance and invokes exactly one `./blue run` process.
5. Blue validates configuration, invokes dlt, runs dbt-clickhouse, tests models, and publishes a secret-safe summary.
6. ClickHouse owns raw and analytical data; PocketBase stores only control-plane intent and workflow-level evidence; journald stores logs.

## Data scope

All repositories accessible to the GitHub credential in the `getcolors` organization:

- repository inventory;
- commit summaries;
- recent organization events;
- GitHub Actions workflow runs;
- selected Package Skill and lockfile paths.

Loads merge on stable GitHub IDs or commit SHA. Events overlap and deduplicate by event ID because GitHub retains only a recent window.

## Acceptance criteria

- `build` and `create --dry-run` work without provider credentials or side effects;
- validation reports all configuration errors with exit 2;
- generated artifacts are deterministic and golden-tested;
- unit tests stub subprocesses and HTTP;
- launcher payload equals the root launcher;
- a real create converges and a second create remains convergent;
- DNS, HTTPS, PocketBase health, ClickHouse health, systemd timers, and one real warehouse run pass;
- no secret, generated output, or private SSH key is tracked.

## Explicit non-goals

No task collections, step queues, sensors, XComs, worker pools, cross-pipeline dependencies, step retries, or backfill scheduler. A retry is a new whole-workflow run.
