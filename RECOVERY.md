# Recovery

## Control-plane and warehouse data

The Vultr instance has daily provider backups enabled. ClickHouse data is under `/var/lib/github-dwh/clickhouse`, PocketBase state under `/var/lib/github-dwh/pocketbase`, and dlt incremental state under `/var/lib/github-dwh/dlt`.

For whole-host recovery, restore the latest Vultr backup as a replacement instance, verify the attached firewall and `github-dwh.bigconfig.space` A record, then run the Package Skill `create` event to reconverge software and systemd units. Do not run `delete` as a recovery operation.

## Rebuilding analytical data

GitHub is the source of truth for repositories, commits, workflow runs, and Package Skill metadata. After restoring or replacing ClickHouse, create a new whole-workflow run from PocketBase. dlt reloads source records and dbt rebuilds `analytics` and `marts`.

GitHub organization events are a recent, bounded feed and cannot be reconstructed beyond GitHub's retention window. Recover these from the ClickHouse backup when historical continuity matters.

## PocketBase access

The superuser email is non-secret desired state. Its password remains only in the deployment's `.envrc.private` and `/etc/github-dwh/environment` on the host. To rotate it, update the local private value and run `create`; Ansible upserts the PocketBase superuser and rewrites the protected environment file.

## Diagnostics

```sh
systemctl status github-dwh-dispatch.timer
systemctl status github-dwh-dispatch.service
journalctl -u github-dwh-run-<run-id>.service
docker compose -f /opt/github-dwh/docker-compose.yml ps
curl http://127.0.0.1:8090/api/health
curl http://127.0.0.1:8123/ping
```

Retry failures by creating a new complete run. Do not edit run steps or add task-level retry state to PocketBase.
