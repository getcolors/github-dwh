from package_github_dwh_blue.validate import secret_errors, state_errors


def test_validation_reports_all_missing_fields():
    errors = state_errors({})
    assert len(errors) > 10
    assert "required configuration is not set: control-plane-host" in errors
    assert "github-resources must be a non-empty list" in errors


def test_run_requires_only_data_credentials():
    assert secret_errors({}, "run") == [
        "required credential is not set: COLORS_PAR_GITHUB_TOKEN",
        "required credential is not set: COLORS_PAR_CLICKHOUSE_PASSWORD",
        "required credential is not set: COLORS_PAR_LIGHTDASH_ADMIN_PASSWORD",
    ]


def test_r2_backend_requires_bucket_endpoint_and_credentials():
    errors = state_errors({"provider-backend": "r2"})
    assert "required configuration is not set: r2-bucket" in errors
    assert "required configuration is not set: r2-endpoint" in errors
    create = secret_errors({"provider-backend": "r2"}, "create")
    assert "required credential is not set: COLORS_PAR_R2_ACCESS_KEY_ID" in create
    assert "required credential is not set: COLORS_PAR_R2_SECRET_ACCESS_KEY" in create
    assert "required credential is not set: COLORS_PAR_R2_ACCESS_KEY_ID" not in secret_errors({"provider-backend": "local"}, "create")


def test_create_requires_lightdash_r2_credentials():
    create = secret_errors({}, "create")
    assert "required credential is not set: COLORS_PAR_LIGHTDASH_R2_ACCESS_KEY_ID" in create
    assert "required credential is not set: COLORS_PAR_LIGHTDASH_R2_SECRET_ACCESS_KEY" in create
