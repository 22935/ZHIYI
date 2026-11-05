"""Desktop reopening must preserve healthy services and refuse partial recovery."""
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'windows/native'))
import persistent_runtime as runtime


def setup_runtime(monkeypatch, tmp_path, desktop_alive=False):
    processes = {name: {'pid': index} for index, name in enumerate(
        ('postgres', 'redis', 'host', 'ai', 'java', 'frontend', 'desktop', 'terminal'), 1)}
    state = {'processes': processes}
    snapshot = {'services': {name: {'alive': name != 'desktop' or desktop_alive} for name in processes},
                'runtime': {'coreReady': True}, 'postgresReady': True, 'redisReady': True, 'javaReady': True,
                'status': 'UP' if desktop_alive else 'DOWN'}
    monkeypatch.setattr(runtime, 'manifest', lambda home: {})
    monkeypatch.setattr(runtime, 'state_for', lambda home: state)
    monkeypatch.setattr(runtime, 'status', lambda home: snapshot)
    monkeypatch.setattr(runtime.native, 'credentials', lambda home: {'hmac': 'test-only-master-secret'})
    monkeypatch.setattr(runtime, 'alive', lambda record: record if record['pid'] != 7 or desktop_alive else None)
    return state, snapshot


def test_idle_environment_uses_existing_startup(monkeypatch, tmp_path):
    setup_runtime(monkeypatch, tmp_path)
    monkeypatch.setattr(runtime, 'alive', lambda record: None)
    start = Mock(return_value={'status': 'UP'})
    monkeypatch.setattr(runtime, 'up', start)
    assert runtime.open_desktop(tmp_path)['status'] == 'UP'
    start.assert_called_once_with(tmp_path, True)


def test_existing_window_is_focused_without_spawning(monkeypatch, tmp_path):
    state, _ = setup_runtime(monkeypatch, tmp_path, desktop_alive=True)
    show = Mock(return_value=[{'visible': True}])
    spawn = Mock()
    monkeypatch.setattr(runtime.desktop, 'show_desktop', show)
    monkeypatch.setattr(runtime.desktop, 'spawn_app', spawn)
    assert runtime.open_desktop(tmp_path)['desktopWindows'] == [{'visible': True}]
    show.assert_called_once_with(state['processes']['desktop'], runtime.desktop_shell.ELECTRON_WINDOW_CLASSES)
    spawn.assert_not_called()


def test_partial_environment_is_never_automatically_restarted(monkeypatch, tmp_path):
    _, snapshot = setup_runtime(monkeypatch, tmp_path)
    snapshot['services']['java']['alive'] = False
    start = Mock()
    monkeypatch.setattr(runtime, 'up', start)
    with pytest.raises(RuntimeError, match='partially running; unavailable: java'):
        runtime.open_desktop(tmp_path)
    start.assert_not_called()


def test_closed_shell_reopens_with_same_home_and_without_secrets(monkeypatch, tmp_path):
    state, _ = setup_runtime(monkeypatch, tmp_path)
    saved_services = dict(state['processes'])
    monkeypatch.setenv('AI_INTERNAL_TOKEN', 'private-test-value')
    monkeypatch.setenv('ELECTRON_RUN_AS_NODE', '1')
    release = Mock()
    monkeypatch.setattr(runtime.native, 'release_port', release)
    monkeypatch.setattr(runtime.desktop_shell, 'desktop_command', Mock(return_value=(['electron'], tmp_path)))
    spawn = Mock(return_value={'pid': 88})
    monkeypatch.setattr(runtime.desktop, 'spawn_app', spawn)
    monkeypatch.setattr(runtime.desktop, 'wait_until', Mock())
    monkeypatch.setattr(runtime.desktop, 'show_desktop', Mock(return_value=[{'visible': True}]))
    monkeypatch.setattr(runtime, 'save', Mock())
    runtime.open_desktop(tmp_path)
    release.assert_called_once_with(19222)
    args = spawn.call_args.args
    assert args[2] == ['electron', f'--user-data-dir={tmp_path / "electron"}']
    assert 'AI_INTERNAL_TOKEN' not in args[3]
    assert 'ELECTRON_RUN_AS_NODE' not in args[3]
    assert state['processes']['desktop'] == {'pid': 88}
    assert all(state['processes'][name] == saved_services[name] for name in saved_services if name != 'desktop')
