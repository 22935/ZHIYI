"""Startup ordering and diagnostics without touching live services or databases."""
import json
import sys
import threading
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'windows/native'))
import persistent_runtime as runtime


def configure_startup(monkeypatch, tmp_path, fail_at=None):
    for name in ('postgres', 'redis', 'temp', 'logs', 'workspace', 'data'):
        (tmp_path / name).mkdir()
    (tmp_path / 'postgres/PG_VERSION').write_text('15')
    entry = tmp_path / 'apps/backend-ts/dist/main.js'
    entry.parent.mkdir(parents=True)
    entry.touch()
    monkeypatch.setattr(runtime, 'ROOT', tmp_path)
    info = {'workspace': str((tmp_path / 'workspace').resolve()), 'backendEntry': str(entry),
            'postgresBin': str(tmp_path), 'memurai': 'memurai', 'initialized': True}
    state = {'processes': {}}
    events, environments, commands = [], {}, {}
    state['commands'] = commands
    monkeypatch.setattr(runtime, 'manifest', lambda home: info)
    monkeypatch.setattr(runtime, 'state_for', lambda home: state)
    monkeypatch.setattr(runtime.native, 'credentials', lambda home: {'redis': 'test-only'})
    monkeypatch.setattr(runtime, 'env_for', lambda *args: {'PATH': 'test', 'AI_INTERNAL_TOKEN': 'private'})
    monkeypatch.setattr(runtime, 'backend_environment', lambda *args: {})
    monkeypatch.setattr(runtime, 'prepare_platform', lambda *args: {})
    monkeypatch.setattr(runtime.native, 'port_free', Mock())
    monkeypatch.setattr(runtime, 'save', Mock())
    monkeypatch.setattr(runtime, 'sql', lambda *args, **kwargs: '1')
    monkeypatch.setattr(runtime, 'redis_client', lambda *args, **kwargs: Mock(ping=Mock(return_value=True)))
    monkeypatch.setattr(runtime.native, 'health', lambda *args: {'status': 'UP'})
    monkeypatch.setattr(runtime, 'status', lambda home: {'status': 'UP'})

    def spawn(home, name, command, env):
        service = name.rsplit('/', 1)[-1]
        events.append(('spawn', service))
        environments[service] = env
        commands[service] = command
        return {'pid': len(events), 'name': service}

    def wait(check, record, timeout):
        events.append(('ready', record['name']))
        if record['name'] == 'ai':
            command = commands['ai']
            release = Path(command[command.index('--release-file') + 1])
            assert release.read_text() == command[command.index('--nonce') + 1]
            assert ('schema', 'inspect') in events and ('grants', 'project') in events
        if fail_at == record['name']:
            raise RuntimeError('test readiness failure')
        assert check()

    def inspect(*args):
        events.append(('schema', 'inspect'))
        if fail_at == 'schema':
            raise RuntimeError('test schema failure')

    monkeypatch.setattr(runtime.native, 'spawn', spawn)
    monkeypatch.setattr(runtime.desktop, 'wait_until', wait)
    monkeypatch.setattr(runtime, 'schema', inspect)
    def grants(*args):
        events.append(('grants', 'project'))
        if fail_at == 'grants':
            raise RuntimeError('test grants failure')
    monkeypatch.setattr(runtime, 'prepare_workspace_grants', grants)
    monkeypatch.setattr(runtime.terminal_service, 'start', Mock())
    monkeypatch.setattr(runtime, 'start_hands', lambda home, info, creds, state, env, start: start('host', ['node'], env))
    monkeypatch.setattr(runtime.terminal_service, 'desktop_environment', lambda *args: {})
    monkeypatch.setattr(runtime.desktop_shell, 'desktop_command', lambda *args, **kwargs: (['electron'], tmp_path))
    monkeypatch.setattr(runtime.desktop_shell, 'ready_check', lambda port: lambda: True)
    monkeypatch.setattr(runtime.desktop, 'spawn_app', lambda *args: spawn(args[0], 'desktop', args[2], args[3]))
    monkeypatch.setattr(runtime.desktop, 'show_desktop', lambda *args: [{'visible': True}])
    cleanup = Mock(side_effect=lambda home: state.update(cleanupGateOpen=bool(list((home / 'temp').glob('ai-start-*.ready')))))
    monkeypatch.setattr(runtime, 'down', cleanup)
    return state, events, environments, cleanup


def test_frontend_preparation_overlaps_backends_but_desktop_waits_for_all_gates(monkeypatch, tmp_path):
    state, events, environments, cleanup = configure_startup(monkeypatch, tmp_path)
    assert runtime.up(tmp_path, True)['status'] == 'UP'
    assert events.index(('spawn', 'frontend')) < events.index(('schema', 'inspect'))
    assert events.index(('spawn', 'frontend')) < events.index(('spawn', 'ai'))
    assert events.index(('spawn', 'redis')) < events.index(('ready', 'postgres'))
    assert events.index(('spawn', 'ai')) < events.index(('schema', 'inspect'))
    assert events.index(('grants', 'project')) < events.index(('ready', 'ai'))
    assert events.index(('ready', 'ai')) < events.index(('ready', 'frontend')) < events.index(('spawn', 'desktop'))
    assert state['commands']['ai'][2] == 'app.native_startup'
    assert not list((tmp_path / 'temp').glob('ai-start-*'))
    assert 'AI_INTERNAL_TOKEN' not in environments['frontend']
    assert environments['frontend']['DEV_BACKEND_PROXY_TARGET'] == 'http://127.0.0.1:18080'
    cleanup.assert_not_called()
    timings = json.loads(next((tmp_path / 'logs').glob('*/startup-timings.json')).read_text())
    assert all(stage['status'] == 'DONE' and stage['durationSeconds'] >= 0 for stage in timings['stages'])


@pytest.mark.parametrize('failure', ['schema', 'grants', 'ai', 'backend', 'frontend'])
def test_failed_gate_cleans_up_early_frontend_and_never_opens_desktop(monkeypatch, tmp_path, failure):
    state, events, _, cleanup = configure_startup(monkeypatch, tmp_path, failure)
    with pytest.raises(RuntimeError, match='test .* failure'):
        runtime.up(tmp_path, True)
    assert 'frontend' in state['processes']
    assert ('spawn', 'desktop') not in events
    cleanup.assert_called_once_with(tmp_path)
    timings = json.loads(next((tmp_path / 'logs').glob('*/startup-timings.json')).read_text())
    assert any(stage['status'] == 'FAILED' for stage in timings['stages'])
    assert 'ai' in state['processes']
    assert not list((tmp_path / 'temp').glob('ai-start-*'))
    if failure in ('schema', 'grants'):
        assert state['cleanupGateOpen'] is False


def test_schema_and_grants_overlap_and_both_finish_before_ai_release(monkeypatch, tmp_path):
    _, events, _, _ = configure_startup(monkeypatch, tmp_path)
    barrier = threading.Barrier(2, timeout=5)
    def inspect(*args):
        barrier.wait()
        events.append(('schema', 'inspect'))
    def grants(*args):
        barrier.wait()
        events.append(('grants', 'project'))
    monkeypatch.setattr(runtime, 'schema', inspect)
    monkeypatch.setattr(runtime, 'prepare_workspace_grants', grants)
    assert runtime.up(tmp_path, True)['status'] == 'UP'


@pytest.mark.parametrize('failed', ['postgres', 'redis', 'backend'])
def test_health_checks_do_not_mark_other_services_down(monkeypatch, tmp_path, failed):
    processes = {name: {'name': name} for name in ('postgres', 'redis', 'backend')}
    monkeypatch.setattr(runtime, 'manifest', lambda home: {'workspace': str(home), 'redisLicense': 'test'})
    monkeypatch.setattr(runtime, 'state_for', lambda home: {'processes': processes})
    monkeypatch.setattr(runtime, 'alive', lambda record: record)
    monkeypatch.setattr(runtime.native, 'snapshot', lambda state: {'coreReady': True})
    monkeypatch.setattr(runtime.native, 'credentials', lambda home: {})

    def probe(name):
        if name == failed:
            raise OSError('test health failure')
        return True

    monkeypatch.setattr(runtime, 'sql', lambda *args, **kwargs: '1' if probe('postgres') else '')
    redis = Mock(ping=lambda: probe('redis'))
    monkeypatch.setattr(runtime, 'redis_client', lambda *args, **kwargs: redis)
    monkeypatch.setattr(runtime.native, 'health', lambda *args: {'status': 'UP' if probe('backend') else 'DOWN'})
    result = runtime.status(tmp_path)
    for name in processes:
        assert result[name + 'Ready'] is (name != failed)
    assert result['status'] == 'DOWN'
    redis.close.assert_called_once()


def test_progress_is_immediate_on_stderr_and_records_failed_stage(tmp_path, capsys):
    path = tmp_path / 'timings.json'
    with pytest.raises(RuntimeError):
        with runtime.StartupProgress(path).stage('Schema inspection'):
            assert 'Schema inspection...' in capsys.readouterr().err
            raise RuntimeError('test')
    output = capsys.readouterr()
    assert output.out == ''
    assert 'FAILED' in output.err
    assert json.loads(path.read_text())['stages'][0]['status'] == 'FAILED'


def test_postgres_health_probe_bounds_connection_and_process_time(monkeypatch, tmp_path):
    run = Mock(return_value=Mock(returncode=0, stdout='1\n'))
    monkeypatch.setattr(runtime.subprocess, 'run', run)
    monkeypatch.setattr(runtime, 'pg_env', lambda creds: {})
    assert runtime.sql({'postgresBin': str(tmp_path)}, {}, 'SELECT 1;', timeout=5) == '1'
    assert run.call_args.kwargs['timeout'] == 5
    assert run.call_args.kwargs['env']['PGCONNECT_TIMEOUT'] == '3'


def test_timing_write_error_does_not_replace_startup_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime.native, 'write_json', Mock(side_effect=OSError('test disk failure')))
    with pytest.raises(RuntimeError, match='original startup failure'):
        with runtime.StartupProgress(tmp_path / 'timings.json').stage('Schema inspection'):
            raise RuntimeError('original startup failure')


def test_shutdown_uses_dependencies_instead_of_parallel_spawn_order(monkeypatch, tmp_path):
    (tmp_path / 'logs').mkdir()
    (tmp_path / 'temp').mkdir()
    names = ('postgres', 'redis', 'backend', 'frontend', 'ai', 'terminal', 'host', 'desktop')
    state = {'processes': {name: {'name': name} for name in names}, 'desktop': True}
    stopped = []
    redis_stopped = False
    monkeypatch.setattr(runtime, 'manifest', lambda home: {'postgresBin': str(home)})
    monkeypatch.setattr(runtime, 'state_for', lambda home: state)
    monkeypatch.setattr(runtime.native, 'credentials', lambda home: {})
    monkeypatch.setattr(runtime, 'alive', lambda record: None if record['name'] == 'redis' and redis_stopped else record)
    monkeypatch.setattr(runtime.native, 'stop', lambda record: stopped.append(record['name']) or 'graceful')
    monkeypatch.setattr(runtime.desktop, 'close_desktop', Mock())
    monkeypatch.setattr(runtime.subprocess, 'run', lambda *args, **kwargs: stopped.append('postgres'))
    def shutdown(**kwargs):
        nonlocal redis_stopped
        stopped.append('redis')
        redis_stopped = True
    client = Mock(shutdown=shutdown)
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(runtime, 'redis_client', lambda *args, **kwargs: client)
    monkeypatch.setattr(runtime.native, 'port_free', Mock())
    cleanup = Mock(return_value={'status': 'PASS'})
    monkeypatch.setattr(runtime.native, 'down', cleanup)
    assert runtime.down(tmp_path)['status'] == 'PASS'
    assert stopped == ['desktop', 'frontend', 'ai', 'host', 'terminal', 'backend', 'redis', 'postgres']
    assert cleanup.call_args.kwargs['preserve_credentials'] is True


@pytest.mark.parametrize('available', [True, False])
def test_grant_projection_waits_for_committed_authority_table(monkeypatch, tmp_path, available):
    probes = []
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, query):
            probes.append(query)
            table = 'local_workspace_authorizations' if available and len(probes) > 1 else None
            return Mock(fetchone=Mock(return_value=(table,)))
    connect = Mock(return_value=Connection())
    monkeypatch.setitem(sys.modules, 'psycopg', SimpleNamespace(connect=connect))
    def wait(check, record, timeout):
        assert record == {'pid': 1} and timeout == 150
        assert not check()
        if not check():
            raise RuntimeError('authority table unavailable')
    monkeypatch.setattr(runtime.desktop, 'wait_until', wait)
    project = Mock()
    monkeypatch.setattr(runtime.subprocess, 'run', project)
    args = (tmp_path, {'workspace': str(tmp_path)}, {'AGENTOS_WORKSPACE_DATABASE_URL': 'test-only'}, {'pid': 1})
    if available:
        runtime.prepare_workspace_grants(*args)
        project.assert_called_once()
        assert len(probes) == 3
    else:
        with pytest.raises(RuntimeError, match='authority table unavailable'):
            runtime.prepare_workspace_grants(*args)
        project.assert_not_called()
    assert all(call.kwargs['connect_timeout'] == 5 for call in connect.call_args_list)
