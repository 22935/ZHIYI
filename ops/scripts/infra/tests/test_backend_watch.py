"""Backend-only watcher activation preserves every other owned service."""
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'windows/native'))
import persistent_runtime as runtime


def configured(monkeypatch, tmp_path):
    root, home = tmp_path/'repo', tmp_path/'home'
    home.mkdir()
    entry = root/'apps/backend-ts/scripts/dev.mjs'
    entry.parent.mkdir(parents=True)
    entry.touch()
    compiler = root/'apps/backend-ts/node_modules/typescript/lib/typescript.js'
    compiler.parent.mkdir(parents=True)
    compiler.touch()
    node = str(tmp_path/'node.exe')
    old = {'pid': 10, 'command': [node, str(root/'apps/backend-ts/dist/main.js')]}
    state = {'session': 'test-session', 'processes': {
        'backend': old, 'ai': {'pid': 20}, 'frontend': {'pid': 30}, 'postgres': {'pid': 40}}}
    monkeypatch.setattr(runtime, 'ROOT', root)
    monkeypatch.setattr(runtime, 'manifest', lambda home: {})
    monkeypatch.setattr(runtime, 'state_for', lambda home: state)
    monkeypatch.setattr(runtime, 'save', Mock())
    monkeypatch.setattr(runtime, 'alive', lambda record: record)
    monkeypatch.setattr(runtime.shutil, 'which', lambda name: node)
    monkeypatch.setattr(runtime.native, 'credentials', Mock(return_value={}))
    monkeypatch.setattr(runtime, 'prepare_platform', Mock(return_value={'IDENTITY': 'unchanged'}))
    monkeypatch.setattr(runtime.native, 'health', Mock(return_value={'status': 'UP'}))
    monkeypatch.setattr(runtime.native, 'stop', Mock())
    monkeypatch.setattr(runtime.native, 'spawn', Mock(return_value={'pid': 50}))
    monkeypatch.setattr(runtime.desktop, 'wait_until', Mock())
    return home, state, entry, node, old


def test_only_the_recorded_backend_is_replaced(monkeypatch, tmp_path):
    home, state, entry, node, old = configured(monkeypatch, tmp_path)
    others = {name: value for name, value in state['processes'].items() if name != 'backend'}
    result = runtime.watch_backend(home)
    assert result['status'] == 'UP' and result['backendWatch'] and result['changed']
    assert state['processes']['backend']['pid'] == 50
    assert {name: value for name, value in state['processes'].items() if name != 'backend'} == others
    runtime.native.stop.assert_called_once_with(old, allow_terminate=False)
    assert runtime.native.spawn.call_args.args[2:] == ([node, str(entry)], {'IDENTITY': 'unchanged'})


def test_an_existing_healthy_watcher_is_not_restarted(monkeypatch, tmp_path):
    home, state, entry, node, _ = configured(monkeypatch, tmp_path)
    state['processes']['backend']['command'] = [node, str(entry)]
    assert runtime.watch_backend(home)['changed'] is False
    runtime.native.stop.assert_not_called()
    runtime.native.spawn.assert_not_called()
    runtime.prepare_platform.assert_not_called()


def test_an_existing_unhealthy_watcher_is_not_reported_up(monkeypatch, tmp_path):
    home, state, entry, node, _ = configured(monkeypatch, tmp_path)
    state['processes']['backend']['command'] = [node, str(entry)]
    runtime.native.health.return_value = {'status': 'DOWN'}
    with pytest.raises(RuntimeError, match='not ready'):
        runtime.watch_backend(home)
    runtime.native.stop.assert_not_called()


def test_unrecognized_backend_entry_is_never_stopped(monkeypatch, tmp_path):
    home, state, _, node, _ = configured(monkeypatch, tmp_path)
    state['processes']['backend']['command'] = [node, 'unrelated.js']
    with pytest.raises(RuntimeError, match='recognized repository entry'):
        runtime.watch_backend(home)
    runtime.native.stop.assert_not_called()


def test_failed_activation_restores_the_previous_backend_only(monkeypatch, tmp_path):
    home, state, _, _, old = configured(monkeypatch, tmp_path)
    runtime.native.spawn.side_effect = [{'pid': 50}, {'pid': 60}]
    runtime.desktop.wait_until.side_effect = [RuntimeError('test watcher failed'), None]
    with pytest.raises(RuntimeError, match='restored the previous backend'):
        runtime.watch_backend(home)
    assert state['processes']['backend'] == {'pid': 60}
    assert state['processes']['ai'] == {'pid': 20}
    assert runtime.native.spawn.call_args_list[1].args[2] == old['command']
    assert runtime.native.stop.call_args_list[1].args == ({'pid': 50},)
