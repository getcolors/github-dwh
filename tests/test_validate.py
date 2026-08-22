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
