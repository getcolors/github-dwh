from __future__ import annotations

REQUIRED = {
    "profile": str,
    "control-plane-host": str,
    "github-org": str,
    "clickhouse-raw-database": str,
    "clickhouse-analytics-database": str,
    "clickhouse-marts-database": str,
    "clickhouse-user": str,
    "pocketbase-superuser-email": str,
    "vultr-name": str,
    "vultr-region": str,
    "vultr-plan": str,
    "vultr-os-id": int,
    "vultr-ssh-key-name": str,
    "ssh-private-key": str,
}

CREATE_SECRETS = ("vultr-api-key", "cloudflare-api-token", "clickhouse-password", "pocketbase-superuser-password", "github-token")
RUN_SECRETS = ("github-token", "clickhouse-password")


def state_errors(opts: dict) -> list[str]:
    errors = []
    for key, kind in REQUIRED.items():
        value = opts.get(key)
        if value is None or value == "":
            errors.append(f"required configuration is not set: {key}")
        elif not isinstance(value, kind):
            errors.append(f"invalid configuration type for {key}: expected {kind.__name__}")
    if opts.get("provider-compute") not in (None, "vultr"):
        errors.append("provider-compute must be vultr")
    if opts.get("provider-dns") not in (None, "cloudflare"):
        errors.append("provider-dns must be cloudflare")
    if opts.get("provider-backend") not in (None, "local"):
        errors.append("provider-backend must be local")
    host = str(opts.get("control-plane-host") or "")
    if host and "." not in host:
        errors.append("control-plane-host must be a fully qualified domain name")
    resources = opts.get("github-resources")
    if not isinstance(resources, list) or not resources:
        errors.append("github-resources must be a non-empty list")
    return errors


def secret_errors(opts: dict, event: str) -> list[str]:
    required = RUN_SECRETS if event == "run" else CREATE_SECRETS
    return [f"required credential is not set: COLORS_PAR_{key.upper().replace('-', '_')}" for key in required if not opts.get(key)]
