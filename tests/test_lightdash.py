import json
from pathlib import Path

from package_github_dwh_blue.workflow import wire_fn


ROOT = Path(__file__).parents[1]
CONTENT = ROOT / "src/package_github_dwh_blue/resources/runtime/lightdash_content.json"


def test_lightdash_content_references_declared_charts():
    content = json.loads(CONTENT.read_text())
    slugs = {chart["slug"] for chart in content["charts"]}
    assert len(slugs) == len(content["charts"])
    assert content["space"]["slug"] == content["dashboard"]["spaceSlug"]
    references = {
        tile["properties"]["chartSlug"]
        for tile in content["dashboard"]["tiles"]
        if tile["type"] == "saved_chart"
    }
    assert references == slugs
    assert all(chart["spaceSlug"] == content["space"]["slug"] for chart in content["charts"])


def test_run_workflow_finishes_with_lightdash_sync():
    dbt_test = wire_fn("github-dwh/dbt-test", {"blue/event": "run"})
    assert dbt_test[1] == "github-dwh/lightdash"
    lightdash = wire_fn("github-dwh/lightdash", {"blue/event": "run"})
    assert len(lightdash) == 1
