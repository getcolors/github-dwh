from __future__ import annotations

REQUIRED = {
    "profile": str,
    "control-plane-host": str,
    "analytics-host": str,
    "github-org": str,
    "clickhouse-raw-database": str,
    "clickhouse-analytics-database": str,
    "clickhouse-marts-database": str,
    "clickhouse-user": str,
    "lightdash-clickhouse-user": str,
    "lightdash-r2-bucket": str,
    "lightdash-r2-endpoint": str,
    "lightdash-r2-region": str,
    "pocketbase-superuser-email": str,
    "vultr-name": str,
    "vultr-region": str,
    "vultr-plan": str,
    "vultr-os-id": int,
    "vultr-ssh-key-name": str,
    "ssh-private-key": str,
}

CREATE_SECRETS = ("vultr-api-key", "cloudflare-api-token", "clickhouse-password", "pocketbase-superuser-password", "github-token", "lightdash-admin-password", "lightdash-secret", "lightdash-postgres-password", "lightdash-clickhouse-password", "lightdash-r2-access-key-id", "lightdash-r2-secret-access-key")
RUN_SECRETS = ("github-token", "clickhouse-password", "lightdash-admin-password")
BACKEND_SECRETS = ("r2-access-key-id", "r2-secret-access-key")


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
    if opts.get("provider-backend") not in (None, "local", "r2"):
        errors.append("provider-backend must be local or r2")
    if opts.get("provider-backend") == "r2":
        for key in ("r2-bucket", "r2-endpoint"):
            if not opts.get(key):
                errors.append(f"required configuration is not set: {key}")
    host = str(opts.get("control-plane-host") or "")
    analytics_host = str(opts.get("analytics-host") or "")
    if host and "." not in host:
        errors.append("control-plane-host must be a fully qualified domain name")
    if analytics_host and "." not in analytics_host:
        errors.append("analytics-host must be a fully qualified domain name")
    if host and analytics_host and host == analytics_host:
        errors.append("analytics-host must differ from control-plane-host")
    resources = opts.get("github-resources")
    if not isinstance(resources, list) or not resources:
        errors.append("github-resources must be a non-empty list")
    return errors


def secret_errors(opts: dict, event: str) -> list[str]:
    backend = BACKEND_SECRETS if opts.get("provider-backend") == "r2" else ()
    required = RUN_SECRETS if event == "run" else CREATE_SECRETS + backend
    return [f"required credential is not set: COLORS_PAR_{key.upper().replace('-', '_')}" for key in required if not opts.get(key)]


def env_errors(env: dict) -> list[str]:
    if env.get("COLORS_PAR_PROFILE"):
        return ["COLORS_PAR_PROFILE is set. This package takes its profile from colors.yml only: remote state is keyed by profile, so an overlay could redirect this deployment to another project's state."]
    return []
