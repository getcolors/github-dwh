from pathlib import Path
from package_github_dwh_blue.cli import run


async def test_build_is_offline_and_renders(tmp_path, monkeypatch):
    fixture = Path(__file__).parents[1] / "test/fixtures/colors.yml"
    state = tmp_path / "colors.yml"
    state.write_text(fixture.read_text())
    result = await run("build", "-f", str(state))
    assert result["blue/exit"] == 0
    assert (tmp_path / ".colors/github-dwh-test/tofu/main.tf").exists()
    assert (tmp_path / ".colors/github-dwh-test/ansible/create.yml").exists()


async def test_dry_run_is_offline(tmp_path):
    fixture = Path(__file__).parents[1] / "test/fixtures/colors.yml"
    state = tmp_path / "colors.yml"
    state.write_text(fixture.read_text())
    result = await run("create", "--dry-run", "-f", str(state))
    assert result["blue/exit"] == 0
