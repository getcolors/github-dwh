# Recovery

## Control-plane and warehouse data

The Vultr instance has daily provider backups enabled. ClickHouse data is under `/var/lib/github-dwh/clickhouse`, PocketBase state under `/var/lib/github-dwh/pocketbase`, Lightdash metadata PostgreSQL under `/var/lib/github-dwh/lightdash-postgres`, and dlt incremental state under `/var/lib/github-dwh/dlt`. Lightdash object storage is the Cloudflare R2 bucket named by `lightdash-r2-bucket`; it holds no data the host must back up.

For whole-host recovery, restore the latest Vultr backup as a replacement instance, verify the attached firewall and `github-dwh.bigconfig.space` A record, then run the Package Skill `create` event to reconverge software and systemd units. OpenTofu state lives in the shared R2 bucket keyed `<profile>/tofu.tfstate` and survives the host. Do not run `delete` as a recovery operation.

## Rebuilding analytical data

GitHub is the source of truth for repositories, commits, workflow runs, and Package Skill metadata. After restoring or replacing ClickHouse, create a new whole-workflow run from PocketBase. dlt reloads source records and dbt rebuilds `analytics` and `marts`.

GitHub organization events are a recent, bounded feed and cannot be reconstructed beyond GitHub's retention window. Recover these from the ClickHouse backup when historical continuity matters.

## PocketBase and Lightdash access

The shared admin email is non-secret desired state. Passwords remain only in the deployment's `.envrc.private` and `/etc/github-dwh/environment` on the host. To rotate the PocketBase password, update its local private value and run `create`; Ansible upserts the PocketBase superuser and rewrites the protected environment file.

Lightdash encryption depends on a stable `COLORS_PAR_LIGHTDASH_SECRET`; restore it together with the PostgreSQL data or stored warehouse credentials cannot be decrypted. Restore `COLORS_PAR_LIGHTDASH_ADMIN_PASSWORD`, `COLORS_PAR_LIGHTDASH_POSTGRES_PASSWORD`, `COLORS_PAR_LIGHTDASH_CLICKHOUSE_PASSWORD`, `COLORS_PAR_LIGHTDASH_R2_ACCESS_KEY_ID`, and `COLORS_PAR_LIGHTDASH_R2_SECRET_ACCESS_KEY` before running `create`. The bootstrap converges the read-only ClickHouse user, semantic project, and dashboard. Changing the Lightdash admin password in desired state does not rotate an existing Lightdash account; rotate that password in Lightdash first, then update the private environment.

## Diagnostics

```sh
systemctl status github-dwh-dispatch.timer
systemctl status github-dwh-dispatch.service
journalctl -u github-dwh-run-<run-id>.service
docker compose -f /opt/github-dwh/docker-compose.yml ps
curl http://127.0.0.1:8090/api/health
curl http://127.0.0.1:8123/ping
curl http://127.0.0.1:8080/api/v1/health
```

Retry failures by creating a new complete run. Do not edit run steps or add task-level retry state to PocketBase.
