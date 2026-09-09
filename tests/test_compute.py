from pathlib import Path
import yaml
from package_github_dwh_blue import compute, tools


def fixture(tmp_path):
    opts = yaml.safe_load((Path(__file__).parents[1] / 'test/fixtures/colors.yml').read_text())
    return {**opts, 'workdir': str(tmp_path), 'blue/event': 'build'}


async def test_singleton_plan_preserves_backup_ipv6_and_public_firewall(tmp_path):
    result = await compute.compute_step(fixture(tmp_path))
    assert result['blue/exit'] == 0
    assert result['github-dwh/infra']['name'] == 'github-dwh-test'
    assert result['github-dwh/infra']['node_id'] == '0'
    import json
    node = json.loads((tmp_path / 'github-dwh-test/compute/nodes/0/node-none.tf.json').read_text())
    resource = node['resource']['vultr_instance']['node']
    assert resource['backups'] == 'enabled'
    assert resource['backups_schedule'] == [{'type': 'daily', 'hour': 3}]
    assert resource['enable_ipv6'] is False
    assert 'vpc_ids' not in resource and 'vpc2_ids' not in resource
    assert result['github-dwh/private-key'] == '$HOME/.ssh/github-dwh-test'
    assert compute.requirements(result)['legacy_state_keys'] == ['github-dwh-test/tofu.tfstate']


async def test_failure_does_not_invent_inventory_or_run_dns(tmp_path, monkeypatch):
    async def refuse(*args): return {'status': 'error', 'errors': ['owned compute conflict']}
    monkeypatch.setattr(compute, 'orchestrate', refuse)
    result = await compute.compute_step({**fixture(tmp_path), 'blue/event': 'create'})
    assert result['blue/exit'] == 1
    assert result['blue/err'] == 'owned compute conflict'
    assert 'github-dwh/infra' not in result


async def test_dns_uses_only_selected_address_and_own_credentials(tmp_path, monkeypatch):
    captured = {}
    async def fake(opts, specs, **kwargs):
        captured.update(kwargs)
        assert 'vultr_instance' not in specs[0]['template']['content']
        return opts
    monkeypatch.setattr(tools.tofu, 'tofu_with_spec', fake)
    opts = {**fixture(tmp_path), 'github-dwh/infra': {'ip': '203.0.113.7'}, 'vultr-api-key': 'compute-secret', 'r2-access-key-id': 'backend-id', 'r2-secret-access-key': 'backend-secret'}
    await tools.tofu_infra(opts)
    assert 'VULTR_API_KEY' not in captured['env']
    assert captured['env']['AWS_ACCESS_KEY_ID'] == 'backend-id'


def test_unsupported_backup_provider_fails_before_execution(tmp_path):
    opts = fixture(tmp_path)
    opts.update({'provider-compute':'digitalocean','digitalocean-region':'nyc3','digitalocean-size':'s-2vcpu-4gb','digitalocean-image':'ubuntu-24-04-x64'})
    assert compute.errors(opts)
