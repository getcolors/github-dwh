import json
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


import pytest
@pytest.mark.parametrize('managed', [True, False])
async def test_singleton_artifacts_and_owned_ssh_block(tmp_path, managed):
    opts = {**fixture(tmp_path), 'workdir': str(tmp_path/'render'), 'blue/event':'build'}
    if not managed: opts['vultr-ssh-keys'] = ['existing-key']
    result = await compute.compute_step(opts)
    assert result['blue/exit'] == 0
    node = result['github-dwh/infra']
    assert node['ip'] == '192.0.2.10' and node['vpc_ip'] is None
    await tools.ansible_local_step(result)
    play = yaml.safe_load((tmp_path/'render/github-dwh-test/ansible-local/main.yml').read_text())
    assert play[0]['vars']['colors_keygen'] is managed
    code = play[0]['tasks'][0]['ansible.builtin.command']['argv'][-1]
    scope = {'__name__':'copied_updater'}
    exec(compile(code, '<packaged-ssh-updater>', 'exec'), scope)
    home = tmp_path/'home'; home.mkdir()
    payload = {'host_alias': opts['profile'], 'ssh_hosts':[{'name':opts['profile'],'ip':node['ip'],'user':node['user']}], 'keygen':managed, 'block_state':'present'}
    assert scope['update'](payload, home)
    config = (home/'.ssh/config').read_text()
    assert 'Host github-dwh-test\n' in config and 'HostName 192.0.2.10' in config
    assert ('IdentityFile ~/.ssh/github-dwh-test' in config) is managed
    assert not scope['update'](payload, home)
    assert scope['update']({**payload,'block_state':'absent'}, home)
    (home/'.ssh/config').write_text('Host=github-dwh-test\n HostName 198.51.100.8\n')
    with pytest.raises(ValueError): scope['update'](payload,home)
    assert '198.51.100.8' in (home/'.ssh/config').read_text()
    docs=json.loads((tmp_path/'render/github-dwh-test/compute/nodes/0/node-none.tf.json').read_text())
    assert 'provisioner' not in json.dumps(docs)


async def test_external_private_path_is_forwarded(tmp_path, monkeypatch):
    captured = {}
    async def fake(opts, specs, **kwargs):
        captured.update(kwargs)
        return opts
    monkeypatch.setattr(tools, 'ansible_with_spec', fake)
    opts = {**fixture(tmp_path), 'github-dwh/infra': {'ip':'192.0.2.10','user':'ubuntu'}, 'github-dwh/private-key':'/selected/key'}
    await tools.ansible_host(opts)
    assert captured['private_key'] == '/selected/key'
    await tools.ansible_host({**opts, 'github-dwh/private-key':None})
    assert captured['private_key'] is None

async def test_pending_migration_guard_reaches_library_without_fallback(tmp_path, monkeypatch):
    async def guarded(opts, topology, requirements):
        assert opts['compute-require-existing-state'] is True
        assert requirements['legacy_state_keys'] == ['github-dwh-test/tofu.tfstate']
        return {'status': 'error'}
    monkeypatch.setattr(compute, 'orchestrate', guarded)
    result = await compute.compute_step({**fixture(tmp_path), 'blue/event': 'create',
                                         'compute-require-existing-state': True})
    assert result['blue/exit'] == 1
    assert 'github-dwh/infra' not in result
