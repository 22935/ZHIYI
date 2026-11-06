"""The native preload phase must never construct or authorize an execution runtime."""
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import psutil
import pytest

ROOT = Path(__file__).resolve().parents[4]
APP_PATHS = [ROOT / 'apps/agent', ROOT / 'apps/agentOS', ROOT / 'apps/agentOS/src']
sys.path.insert(0, str(APP_PATHS[0]))
from app import native_startup as startup


def test_leaf_authority_import_does_not_import_runtime_or_coordinator(tmp_path):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, APP_PATHS)), PYTHONDONTWRITEBYTECODE='1')
    code = '''import sys
from app.execution.workspace_authority import WorkspaceAuthority
assert 'app.execution.wiring' not in sys.modules
assert 'app.execution.coordinator' not in sys.modules
'''
    result = subprocess.run([sys.executable, '-B', '-c', code], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('existing_data', [False, True])
def test_real_preload_has_no_persistent_or_execution_side_effects(tmp_path, existing_data):
    data = tmp_path / 'data'
    if existing_data:
        data.mkdir()
    grants = tmp_path / 'grants.json'
    grants.write_text('{"grants": []}')
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, APP_PATHS)),
               PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1', AGENTOS_DATA_DIR=str(data),
               AGENT_CHROMA_PATH=str(tmp_path / 'chroma'), DEEPSEEK_API_KEY='test-only-key',
               DEEPSEEK_ENABLED='true', AGENTOS_WORKSPACE_GRANTS_FILE=str(grants),
               ZHIYI_LOCAL_RUNTIME_WORKSPACE_PROJECTION=str(grants))
    code = '''import sys, os, threading
def deny(*args, **kwargs):
    raise AssertionError('preload started a background thread')
threading.Thread.start = deny
def audit(event, args):
    if event in {'sqlite3.connect', 'socket.connect', 'subprocess.Popen', 'os.mkdir'}:
        raise AssertionError('preload side effect: ' + event)
    if event == 'open':
        if str(args[0]) == os.environ['AGENTOS_WORKSPACE_GRANTS_FILE']:
            raise AssertionError('preload attempted to cache workspace authority before projection')
        mode, flags = args[1:]
        if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC):
            raise AssertionError('preload attempted a write: ' + str(args[0]))
def profile(frame, event, arg):
    if event == 'call' and frame.f_code.co_name in {'build_default_runtime', '_assemble_default_runtime', 'acquire_workflow_instance_lock'}:
        raise AssertionError('preload attempted runtime assembly')
sys.addaudithook(audit)
sys.setprofile(profile)
from app.native_startup import preload
preload()
assert 'app.main' not in sys.modules
assert len(threading.enumerate()) == 1
print('SAFE')
'''
    result = subprocess.run([sys.executable, '-B', '-c', code], cwd=tmp_path, env=env,
                            capture_output=True, text=True, encoding='utf-8', timeout=90)
    assert result.returncode == 0, result.stderr
    assert 'SAFE' in result.stdout
    assert set(tmp_path.iterdir()) == ({data, grants} if existing_data else {grants})


def test_public_execution_exports_keep_their_original_identity(tmp_path):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, APP_PATHS)), PYTHONDONTWRITEBYTECODE='1')
    code = '''import importlib
import app.execution as execution
for name in execution.__all__:
    module = 'coordinator' if name == 'RunExecutionCoordinator' else 'runtime'
    assert getattr(execution, name) is getattr(importlib.import_module('app.execution.' + module), name)
try:
    execution.missing_export
except AttributeError:
    pass
else:
    raise AssertionError('unknown export accepted')
'''
    result = subprocess.run([sys.executable, '-B', '-c', code], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stderr


def test_release_requires_matching_nonce_and_live_owner(tmp_path):
    path = tmp_path / 'release'
    path.write_text('launch-nonce')
    startup.wait_for_release(path, 'launch-nonce', os.getpid(), psutil.Process().create_time())
    with pytest.raises(RuntimeError, match='identity mismatch'):
        startup.wait_for_release(path, 'another-launch', os.getpid(), psutil.Process().create_time())


def test_missing_release_times_out_without_serving(tmp_path):
    with pytest.raises(RuntimeError, match='timed out'):
        startup.wait_for_release(tmp_path / 'missing', 'nonce', os.getpid(), psutil.Process().create_time(), timeout=0)


@pytest.mark.parametrize('reused', [False, True])
def test_dead_or_reused_owner_cannot_release_ai(monkeypatch, tmp_path, reused):
    path = tmp_path / 'release'
    path.write_text('nonce')
    process = Mock(create_time=Mock(return_value=2), is_running=Mock(return_value=True))
    monkeypatch.setattr(psutil, 'Process', Mock(return_value=process) if reused else Mock(side_effect=psutil.NoSuchProcess(123)))
    with pytest.raises(RuntimeError, match='owner (changed|exited)'):
        startup.wait_for_release(path, 'nonce', 123, 1)


@pytest.mark.parametrize('allowed', [True, False])
def test_original_asgi_entry_is_only_called_after_release(monkeypatch, tmp_path, allowed):
    events = []
    monkeypatch.setattr(startup, 'preload', lambda: events.append('preload'))
    def release(*args):
        events.append('release')
        if not allowed:
            raise RuntimeError('preparation failed')
    monkeypatch.setattr(startup, 'wait_for_release', release)
    serve = Mock(side_effect=lambda *args, **kwargs: events.append('serve'))
    monkeypatch.setitem(sys.modules, 'uvicorn', SimpleNamespace(run=serve))
    args = ['--release-file', str(tmp_path / 'release'), '--nonce', 'test',
            '--owner-pid', '123', '--owner-created', '1', '--port', '18761']
    if allowed:
        startup.main(args)
        serve.assert_called_once_with('app.main:app', host='127.0.0.1', port=18761, workers=1)
        assert events == ['preload', 'release', 'serve']
    else:
        with pytest.raises(RuntimeError, match='preparation failed'):
            startup.main(args)
        serve.assert_not_called()
