"""Windows-only lifecycle harness around the existing two production runtimes.

No business endpoints, executors or authority are implemented here. Every run
owns a new directory and hidden console processes, identified before stopping.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from urllib.request import build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[5]
CAPS = ['fs.list', 'fs.patch', 'fs.read', 'fs.write']
DBS = {
    'WORKFLOW_DB_PATH': 'workflows', 'LANGGRAPH_CHECKPOINT_DB': 'checkpoints',
    'EXECUTION_VALUE_DB': 'values', 'CONTENT_MANIFEST_DB': 'content',
    'EXECUTION_MEMORY_DB': 'memory', 'PROVENANCE_DB': 'provenance',
    'AUDIT_DB': 'audit', 'RESOURCE_DB': 'resources', 'NODE_DB': 'nodes',
    'RESOURCE_HEALTH_DB': 'health', 'EVOLUTION_DB': 'evolution', 'IDENTITY_DB': 'identity',
}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def fixture_layout(run):
    """Only accept a new test layout, never an earlier service/data directory."""
    if os.name != 'nt' or not run.is_absolute() or run == ROOT or ROOT in run.parents:
        raise RuntimeError('Fixtures require a dedicated absolute Windows directory outside the repository')
    for path in [run, *run.parents]:
        if path.exists() and (path.is_symlink() or path.is_junction()):
            raise RuntimeError('Fixture reparse ancestor rejected')
    allowed = {'workspace', 'outside', 'fixture-preparation.json'}
    if run.exists() and any(p.name not in allowed for p in run.iterdir()):
        raise RuntimeError('Fixture directory contains unrelated or runtime data')
    for name, children in [('workspace', {'symlink', 'junction'}), ('outside', {'sentinel.txt'})]:
        path = run / name
        if os.path.lexists(path):
            if not path.is_dir() or path.is_symlink() or path.is_junction():
                raise RuntimeError('Fixture directories must be real directories')
            if any(p.name not in children for p in path.iterdir()):
                raise RuntimeError('Fixture directory contains unrelated files')


def inspect_symlink(run):
    """Read-only validation of an independently prepared real NTFS symlink."""
    link = run / 'workspace/symlink'
    sentinel = run / 'outside/sentinel.txt'
    if sentinel.parent.is_symlink() or sentinel.parent.is_junction():
        raise RuntimeError('Outside fixture directory must not be a reparse point')
    if not sentinel.is_file() or sentinel.is_symlink() or sentinel.is_junction():
        raise RuntimeError('Fixture sentinel must be a real temporary file')
    if not os.path.lexists(link):
        return {'status': 'BLOCKED', 'reason': 'No independently prepared symlink fixture'}
    tag = getattr(link.lstat(), 'st_reparse_tag', None)
    if not link.is_symlink() or tag != 0xA000000C:
        raise RuntimeError('Fixture is not an IO_REPARSE_TAG_SYMLINK; junctions are not substitutes')
    target = link.resolve(strict=True)
    if target not in {(run / 'outside').resolve(), sentinel.resolve()}:
        raise RuntimeError('Symlink must target this run\'s external temporary sentinel or its directory')
    return {'status': 'PASS', 'link': str(link), 'target': str(target),
            'targetKind': 'directory' if target.is_dir() else 'file', 'reparseTag': hex(tag),
            'sentinelSha256': hashlib.sha256(sentinel.read_bytes()).hexdigest()}


def prepare_fixtures(run):
    """Fixture-only stage. Never imports/starts a Runtime or changes privileges."""
    fixture_layout(run)
    run.mkdir(parents=True, exist_ok=True)
    (run / 'workspace').mkdir(exist_ok=True)
    (run / 'outside').mkdir(exist_ok=True)
    sentinel = run / 'outside/sentinel.txt'
    if not os.path.lexists(sentinel):
        sentinel.write_bytes(b'untouched')
    junction = run / 'workspace/junction'
    if not os.path.lexists(junction):
        subprocess.run(['cmd', '/c', 'mklink', '/J', str(junction), str(run / 'outside')],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if not junction.is_junction() or junction.resolve() != (run / 'outside').resolve():
        raise RuntimeError('Invalid independently prepared junction fixture')
    result = inspect_symlink(run)
    reused = result['status'] == 'PASS'
    if not reused:
        try:
            (run / 'workspace/symlink').symlink_to(run / 'outside', target_is_directory=True)
        except OSError as exc:
            if exc.winerror != 1314:
                raise
            result.update(winerror=exc.winerror, reason='Windows refused fixture creation: privilege not held')
        else:
            result = inspect_symlink(run)
    receipt = {'format': 'kinlin-n01a-fixtures-v1', 'runDirectory': str(run),
               'status': result['status'], 'symlink': result, 'reusedExistingSymlink': reused,
               'sentinelSha256': hashlib.sha256(sentinel.read_bytes()).hexdigest(),
               'preparedBeforeRuntime': True, 'preparedAt': time.time(),
               'preparerToken': windows_token(os.getpid())}
    write_json(run / 'fixture-preparation.json', receipt)
    return receipt


def smoke_outcome(receipt, worker_exit):
    """FAIL takes precedence; missing/unknown evidence can never produce PASS."""
    expected = {f'N01A-{i:02d}' for i in range(1, 9)}
    if not isinstance(receipt, dict):
        return 'FAIL', 1
    checks = receipt.get('checks', {})
    if receipt.get('status') == 'FAIL' or worker_exit != 0 or not isinstance(checks, dict) or set(checks) != expected:
        return 'FAIL', 1
    statuses = [check.get('status') if isinstance(check, dict) else None for check in checks.values()]
    if any(status not in {'PASS', 'BLOCKED'} for status in statuses):
        return 'FAIL', 1
    return ('BLOCKED', 2) if 'BLOCKED' in statuses else ('PASS', 0)


def dpapi(data, decrypt=False):
    class Blob(ctypes.Structure):
        _fields_ = [('length', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_byte))]
    buffer = ctypes.create_string_buffer(data)
    incoming = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    outgoing = Blob()
    function = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not function(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(outgoing.data, outgoing.length)
    finally:
        ctypes.windll.kernel32.LocalFree(outgoing.data)


def credentials(run):
    return json.loads(dpapi((run / 'credentials.dpapi').read_bytes(), decrypt=True))


def environment(run, state, creds, *, smoke=False):
    # Deliberately inherit no application secrets, flags, database URLs or proxies.
    env = {key: value for key, value in os.environ.items()
           if key.upper() in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATH', 'PATHEXT',
                              'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'PROGRAMDATA'}}
    data = run / ('smoke-data' if smoke else 'data')
    env.update({
        'PYTHONPATH': os.pathsep.join(str(ROOT / p) for p in
                                   ['apps', 'apps/agent', 'apps/agentOS', 'apps/agentOS/src']),
        'PYTHONUTF8': '1', 'PYTHONUNBUFFERED': '1', 'PYTHONDONTWRITEBYTECODE': '1',
        'TEMP': str(run / 'temp'), 'TMP': str(run / 'temp'), 'SQLITE_TMPDIR': str(run / 'temp'),
        'XDG_CACHE_HOME': str(data / 'cache'), 'AGENT_CHROMA_PATH': str(data / 'chroma'),
        'AGENTOS_DATA_DIR': str(data), 'AGENTOS_ATTACHMENT_STORAGE_DIR': str(data / 'attachments'),
        'AGENTOS_PACKS_DIR': str(ROOT / 'apps/agent/packs'), 'TOOL_CODEBASE_ROOT': str(run / 'workspace'),
        'AI_INTERNAL_TOKEN': creds['token'], 'AGENTOS_RESOURCE_CREDENTIAL_KEY': creds['key'],
        'ENVIRONMENT': 'development', 'PROVIDER_STATE_ENABLED': 'false',
        'UVICORN_WORKERS': '1', 'WEB_CONCURRENCY': '1', 'CHAT_LEGACY_CONTAINER_TERMINAL_ENABLED': 'false',
        # Retain the formal semantic/C2/Dispatch gates, including schema preparation.
        'AGENTOS_MISSION_SEMANTIC_CONVERGENCE': 'true',
        'AGENTOS_C2_EXECUTION_AUTHORITIES': 'true', 'AGENTOS_C2_EXECUTION_DISPATCH': 'true',
        'AGENTOS_LOCAL_RUNTIME_ENDPOINT': f"http://127.0.0.1:{state['hostPort']}/v1/executions",
        'AGENTOS_LOCAL_RUNTIME_SHELL_ENABLED': 'false',
        'ZHIYI_LOCAL_RUNTIME_BIND_HOST': '127.0.0.1',
        'ZHIYI_LOCAL_RUNTIME_PORT': str(state['hostPort']),
        'ZHIYI_LOCAL_RUNTIME_WORKSPACE_ROOT': str(run / 'workspace'),
    })
    for prefix in ['AGENTOS', 'ZHIYI']:
        for key, value in {'RESOURCE_ID': 'n01a-host', 'WORKSPACE_ID': 'n01a-workspace',
                           'GRANT_ID': 'n01a-grant', 'CREDENTIAL_ID': 'n01a-credential',
                           'CREDENTIAL_SECRET': creds['hmac'], 'CAPABILITIES': ','.join(CAPS)}.items():
            env[f'{prefix}_LOCAL_RUNTIME_{key}'] = value
    for name, filename in DBS.items():
        env['AGENTOS_' + name] = str(data / (filename + '.sqlite3'))
    return env


def health(port, path):
    with build_opener(ProxyHandler({})).open(f'http://127.0.0.1:{port}{path}', timeout=2) as response:
        return json.load(response)


def identity(process):
    return {'pid': process.pid, 'created': process.create_time(),
            'executable': process.exe(), 'command': process.cmdline()}


def windows_token(pid):
    import win32api
    import win32con
    import win32security
    process = win32api.OpenProcess(0x1000, False, pid)
    try:
        token = win32security.OpenProcessToken(process, win32con.TOKEN_QUERY)
        try:
            elevated = bool(win32security.GetTokenInformation(token, win32security.TokenElevation))
            sid, _attributes = win32security.GetTokenInformation(token, win32security.TokenIntegrityLevel)
            integrity = win32security.ConvertSidToStringSid(sid)
            privileges = {win32security.LookupPrivilegeName(None, luid): flags for luid, flags in
                          win32security.GetTokenInformation(token, win32security.TokenPrivileges)}
            return {'pid': pid, 'elevated': elevated, 'integritySid': integrity,
                    'symlinkPrivilegePresent': 'SeCreateSymbolicLinkPrivilege' in privileges,
                    'symlinkPrivilegeEnabled': bool(privileges.get('SeCreateSymbolicLinkPrivilege', 0) & 2)}
        finally:
            token.Close()
    finally:
        process.Close()


def owned(record):
    import psutil
    try:
        process = psutil.Process(record['pid'])
        actual = identity(process)
        if actual['created'] != record['created']:
            return None  # PID reused: the owned process is gone; never signal its successor.
        if actual != record:
            raise RuntimeError('Process identity changed; refusing to signal it')
        return process
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        # A PID the ordinary user cannot inspect belongs to someone else; the
        # owned process is gone exactly like a recycled PID.
        return None


def spawn(run, name, command, env):
    import psutil
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = subprocess.SW_HIDE
    with (run / f'{name}.log').open('ab') as log:
        child = subprocess.Popen(command, cwd=run, env=env, stdout=log, stderr=log,
                                 creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=info)
    process = psutil.Process(child.pid)
    try:
        return identity(process)
    except psutil.NoSuchProcess:
        child.wait()
        raise RuntimeError(f'{name} exited immediately; see its log')


def stop(record, *, allow_terminate=True):
    process = owned(record)
    if process is None:
        return None
    descendants = process.children(recursive=True)
    # A dedicated hidden console lets SIGINT run both production cleanup paths.
    # The helper attaches only to this verified process's console. A loaded
    # dev server (vite) can need a second nudge past the first 25s window.
    failure = None
    for budget in (25, 20):
        # A failing/non-zero _signal (e.g. 120 when the target hides its console
        # and AttachConsole/GenerateConsoleCtrlEvent cannot reach it) must NOT abort
        # the loop: fall through to wait(), then escalate to terminate/kill below.
        # Mirror the safer pattern used by the other stop() in this module.
        try:
            subprocess.run([sys.executable, str(Path(__file__).resolve()), '_signal', str(process.pid)],
                           check=False, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        except (OSError, subprocess.SubprocessError):
            pass
        try:
            process.wait(budget)
            for child in descendants:
                child.wait(5)
            return 'graceful'
        except Exception as exc:
            failure = exc
    if not allow_terminate:
        # Keep credentials and state for diagnosis; never silently force-kill.
        raise RuntimeError(f'Graceful stop failed for owned PID {process.pid}') from failure
    # Some non-interactive contexts (console input mode disabled at spawn time)
    # never receive CTRL_C. Escalate only on the identity-verified process tree
    # and report the escalation so shutdown is never silently forced.
    print(f'WARNING: graceful stop timed out for PID {process.pid}; terminating the verified tree',
          file=sys.stderr, flush=True)
    for member in [*reversed(descendants), process]:
        try:
            member.terminate()
        except Exception:
            pass
    try:
        process.wait(15)
        for child in descendants:
            child.wait(5)
        return 'terminated'
    except Exception:
        for member in [*reversed(descendants), process]:
            try:
                member.kill()
            except Exception:
                pass
        process.wait(10)
        return 'killed'


def signal_process(pid):
    kernel = ctypes.windll.kernel32
    kernel.FreeConsole()
    if not kernel.AttachConsole(pid):
        raise ctypes.WinError()
    try:
        kernel.SetConsoleCtrlHandler(None, True)
        if not kernel.GenerateConsoleCtrlEvent(0, 0):
            raise ctypes.WinError()
        time.sleep(0.3)
    finally:
        kernel.FreeConsole()


def port_free(port):
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind(('127.0.0.1', port))


# Processes that own the session (or the machine) are never traded for a port:
# stopping them logs the user out instead of releasing one stray server.
PROTECTED_PROCESSES = frozenset({
    'system', 'registry', 'smss.exe', 'csrss.exe', 'wininit.exe', 'winlogon.exe',
    'services.exe', 'lsass.exe', 'svchost.exe', 'explorer.exe', 'dwm.exe', 'fontdrvhost.exe'
})


def port_owners(port):
    """PIDs listening on 127.0.0.1:<port>. psutil is exact; netstat is the fallback."""
    import psutil
    owners = set()
    try:
        for connection in psutil.net_connections(kind='tcp4'):
            address = connection.laddr
            if connection.pid and connection.status == psutil.CONN_LISTEN and address and address.port == port:
                owners.add(connection.pid)
    except (psutil.AccessDenied, OSError):
        pass
    if owners:
        return sorted(owners)
    try:
        listing = subprocess.run(['netstat', '-ano', '-p', 'tcp'], capture_output=True, text=True, timeout=15,
                                 creationflags=subprocess.CREATE_NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    for line in listing.splitlines():
        fields = line.split()
        if len(fields) < 5 or fields[0].upper() != 'TCP':
            continue
        if fields[1].endswith(f':{port}') and fields[4].isdigit():
            owners.add(int(fields[4]))
    return sorted(owners)


def describe(pid):
    import psutil
    try:
        return identity(psutil.Process(pid))
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


def _wait_gone(process, descendants, seconds):
    import psutil
    try:
        process.wait(seconds)
    except psutil.Error:
        return False
    for child in descendants:
        try:
            child.wait(3)
        except psutil.Error:
            pass
    return True


def stop_external(record):
    """Stop a process this runtime did not spawn, trusting nothing about it.

    Console applications (vite, java, python) exit cleanly on CTRL_C; GUI
    processes have no console, so the helper is allowed to fail and the tree
    escalates exactly like an owned service would.
    """
    import psutil
    try:
        process = psutil.Process(record['pid'])
        if identity(process) != record:
            raise RuntimeError('Process identity changed; refusing to signal it')
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None
    try:
        descendants = process.children(recursive=True)
    except psutil.Error:
        descendants = []
    try:
        subprocess.run([sys.executable, str(Path(__file__).resolve()), '_signal', str(process.pid)],
                       check=False, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        pass
    if _wait_gone(process, descendants, 8):
        return 'graceful'
    for member in [*reversed(descendants), process]:
        try:
            member.terminate()
        except psutil.Error:
            pass
    if _wait_gone(process, descendants, 8):
        return 'terminated'
    for member in [*reversed(descendants), process]:
        try:
            member.kill()
        except psutil.Error:
            pass
    _wait_gone(process, descendants, 5)
    return 'killed'


def _parents():
    import psutil
    try:
        return psutil.Process().parents()
    except psutil.Error:
        return []


def release_port(port):
    """Stop whatever still listens on <port> so a fresh start can bind it.

    A leftover dev server from an earlier session must never block the desktop
    launcher. The runtime refuses only what it must: itself, its ancestors,
    protected Windows processes and processes the user cannot inspect.
    """
    try:
        port_free(port)
        return None
    except OSError as busy:
        failure = busy
    owners = port_owners(port)
    if not owners:
        raise RuntimeError(f'Port {port} is in use but its owner could not be identified') from failure
    protected = {os.getpid(), *(parent.pid for parent in _parents())}
    released = []
    for pid in owners:
        if pid in protected:
            raise RuntimeError(f'Port {port} is held by the launcher itself (PID {pid}); refusing to stop it')
        if pid <= 4:
            raise RuntimeError(f'Port {port} is held by a Windows kernel process (PID {pid})')
        record = describe(pid)
        if record is None:
            raise RuntimeError(f'Port {port} is held by PID {pid}, which this user cannot inspect')
        name = Path(record['executable'] or '').name.lower() or f'PID {pid}'
        if name in PROTECTED_PROCESSES:
            raise RuntimeError(f'Port {port} is held by Windows process {name} (PID {pid}); close it manually')
        print(f'Port {port} is held by {name} (PID {pid}); stopping it to start Zhiyi AgentOS',
              file=sys.stderr, flush=True)
        released.append({'port': port, 'pid': pid, 'process': record, 'outcome': stop_external(record)})
    try:
        port_free(port)
    except OSError as still_busy:
        raise RuntimeError(f'Port {port} is still in use after stopping PID(s) {owners}') from still_busy
    return released


def release_ports(ports_to_free):
    """Release every port a fresh startup needs; returns what had to be stopped."""
    released = []
    for port in ports_to_free:
        stopped = release_port(port)
        if stopped:
            released.extend(stopped)
    return released


def preflight(run, ai_port, host_port):
    import importlib.metadata as metadata
    if os.name != 'nt' or sys.version_info[:2] not in ((3, 13), (3, 14)):
        raise RuntimeError('Requires real Windows CPython 3.13 or 3.14')
    token = windows_token(os.getpid())
    if token['elevated'] or int(token['integritySid'].rsplit('-', 1)[1]) > 8192:
        raise RuntimeError('Native acceptance requires a non-elevated ordinary-user token')
    if not run.is_absolute():
        raise RuntimeError('Run directory must be absolute')
    if run.exists():
        fixture_layout(run)
        receipt = read_json(run / 'fixture-preparation.json')
        if receipt.get('format') != 'kinlin-n01a-fixtures-v1' or receipt.get('runDirectory') != str(run):
            raise RuntimeError('Existing directory is not an independently prepared fixture layout')
        if hashlib.sha256((run / 'outside/sentinel.txt').read_bytes()).hexdigest() != receipt['sentinelSha256']:
            raise RuntimeError('Prepared sentinel changed before startup')
        inspect_symlink(run)
    # Refuse existing reparse ancestors and workspace/data destinations.
    for parent in [run, *run.parents]:
        if parent.exists() and (parent.is_symlink() or parent.is_junction()):
            raise RuntimeError('Reparse ancestor rejected')
    if run == ROOT or ROOT in run.parents:
        raise RuntimeError('Use a new directory outside the repository')
    if ai_port == host_port or not all(1024 <= p <= 65535 for p in [ai_port, host_port]):
        raise RuntimeError('Distinct unprivileged ports required')
    for port in [ai_port, host_port]:
        port_free(port)
    import re
    mismatches = []
    for filename in ['requirements.lock', 'requirements.native-tools.lock']:
        for name, version, rest in re.findall(r'^([\w-]+)==([^\s\\;]+)([^\n]*)',
                                            (ROOT / 'apps/agent' / filename).read_text(), re.M):
            if 'sys_platform != "win32"' in rest:
                continue
            try:
                actual = metadata.version(name)
            except metadata.PackageNotFoundError:
                actual = 'MISSING'
            if actual != version:
                mismatches.append(f'{name}: expected {version}, found {actual}')
    if mismatches:
        raise RuntimeError('Dependency gate failed: ' + '; '.join(mismatches))
    subprocess.run([sys.executable, '-m', 'pip', 'check'], check=True)
    return {'status': 'PASS', 'python': sys.executable, 'version': sys.version,
            'runDirectory': str(run), 'aiPort': ai_port, 'hostPort': host_port, 'token': token}


@contextmanager
def control_lock(run):
    import msvcrt
    with (run / 'lifecycle.lock').open('a+b') as handle:
        handle.seek(0)
        handle.write(b'0')
        handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def prepare(run, env, name):
    Path(env['AGENTOS_DATA_DIR']).mkdir()
    command = [sys.executable, str(ROOT / 'scripts/prepare_agentos_runtime.py')]
    with (run / f'{name}-schema.log').open('ab') as log:
        # Preserve the read-only failure on empty databases before explicit initialization.
        inspected = subprocess.run(command, cwd=run, env=env, stdout=log, stderr=log)
        if inspected.returncode not in (0, 2) and any(Path(env['AGENTOS_' + key]).exists()
                                                     for key in ['WORKFLOW_DB_PATH', 'LANGGRAPH_CHECKPOINT_DB', 'IDENTITY_DB']):
            raise RuntimeError('Schema inspection failed; see schema log')
        subprocess.run(command + ['--apply', '--initialize-empty'], cwd=run, env=env,
                       stdout=log, stderr=log, check=True)
        subprocess.run(command, cwd=run, env=env, stdout=log, stderr=log, check=True)


def snapshot(state):
    import psutil
    result = {'services': {}, 'coreReady': True}
    # hands 是唯一执行后端：host 探 /v1/health，进程树只认 node.exe。
    for name, path, port in [('host', '/v1/health', state['hostPort']),
                             ('ai', '/health/ready', state['aiPort'])]:
        record = state['processes'].get(name)
        try:
            process = owned(record) if record else None
            if process is None:
                raise RuntimeError('owned process absent')
            tree = [process, *process.children(recursive=True)]
            tokens = [windows_token(member.pid) for member in tree if member.name().lower() == ('node.exe' if name == 'host' else 'python.exe')]
            if not tokens or any(t['elevated'] or int(t['integritySid'].rsplit('-', 1)[1]) > 8192 for t in tokens):
                raise RuntimeError('Runtime must use ordinary-user non-elevated tokens')
            listeners = [c for member in tree for c in member.net_connections(kind='tcp')
                         if c.status == psutil.CONN_LISTEN]
            if not any(c.laddr.ip == '127.0.0.1' and c.laddr.port == port for c in listeners):
                raise RuntimeError('expected loopback listener absent')
            if any(c.laddr.ip != '127.0.0.1' for c in listeners):
                raise RuntimeError('non-loopback listener detected')
            payload = health(port, path)
            if name == 'host':
                assert payload['ok'] and payload['service'] == 'zhiyi-hands'
                assert payload['protocolVersion'] == '1'
            else:
                assert payload['status'] == 'UP'
                assert payload['checks']['dataDirectory'] and payload['checks']['workflowStore']
            result['services'][name] = {'status': 'PASS', 'process': record,
                                        'processTree': [identity(member) for member in tree],
                                        'runtimeTokens': tokens, 'health': payload}
        except Exception as exc:
            result['coreReady'] = False
            result['services'][name] = {'status': 'FAIL', 'reason': str(exc)}
    try:
        result['dependencies'] = health(state['aiPort'], '/health/dependencies')
    except Exception:
        result['dependencies'] = {'status': 'UNREACHABLE'}
    return result


def down(run, state, *, preserve_credentials=False):
    with control_lock(run):
        records = [*state['processes'].values(), *state.get('transients', {}).values()]
        stop_modes = {}
        for record in reversed(records):
            mode = stop(record)
            if mode:
                stop_modes[str(record['pid'])] = mode
        for port in [state['aiPort'], state['hostPort']]:
            port_free(port)
        # Windows refuses renaming SQLite stores with leaked open handles.
        directories = [run / 'data', *run.glob('smoke-data*')]
        for directory in directories:
            if directory.is_dir():
                if directory.resolve().parent != run.resolve() or directory.is_symlink() or directory.is_junction():
                    raise RuntimeError('Database handle probe escaped its dedicated run directory')
                probe = directory.with_name(directory.name + '-handle-probe')
                directory.rename(probe)
                probe.rename(directory)
        import msvcrt
        import win32con
        import win32file
        locks = []
        databases = []
        for directory in directories:
            lock = directory / 'runtime.instance.lock'
            if lock.is_file():
                with lock.open('r+b') as handle:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                locks.append(str(lock))
            for database in directory.glob('*.sqlite3'):
                # OPEN_EXISTING with share=0 proves no other handle remains;
                # acquiring and closing this handle does not alter database bytes.
                handle = win32file.CreateFile(str(database), win32con.GENERIC_READ | win32con.GENERIC_WRITE,
                                             0, None, win32con.OPEN_EXISTING, win32con.FILE_ATTRIBUTE_NORMAL, None)
                handle.Close()
                databases.append(str(database))
        if not preserve_credentials:
            (run / 'credentials.dpapi').unlink(missing_ok=True)
        result = {'status': 'PASS', 'processesAbsent': all(owned(p) is None for p in records),
                  'portsReleased': True, 'credentialsRemoved': not (run / 'credentials.dpapi').exists(),
                  'credentialsPreserved': preserve_credentials, 'databaseHandlesReleased': True,
                  'workflowLockReleased': True, 'checkedWorkflowLocks': locks,
                  'exclusiveDatabaseOpenChecks': databases, 'stopModes': stop_modes}
        write_json(run / 'down.json', result)
        return result


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '_signal':
        signal_process(int(sys.argv[2]))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['fixtures', 'preflight', 'status', 'down', 'smoke'])
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--ai-port', type=int, default=18761)
    parser.add_argument('--host-port', type=int, default=18765)
    args = parser.parse_args()
    if not args.run_dir.is_absolute():
        parser.error('--run-dir must be an absolute Windows path')
    run = args.run_dir.absolute()
    if args.action == 'fixtures':
        result = prepare_fixtures(run)
    elif args.action == 'preflight':
        result = preflight(run, args.ai_port, args.host_port)
    else:
        state = read_json(run / 'state.json')
        if state.get('format') != 'kinlin-n01a-v1' or state['runDirectory'] != str(run):
            raise RuntimeError('Invalid run ownership manifest')
        if args.action == 'status':
            result = snapshot(state)
            if not result['coreReady']:
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 1
        elif args.action == 'down':
            result = down(run, state)
        else:
            with control_lock(run):
                env = environment(run, state, credentials(run), smoke=True)
                # Each invocation gets fresh stores; the host grant remains unchanged.
                suffix = secrets.token_hex(4)
                for key, value in list(env.items()):
                    if str(run / 'smoke-data') in value:
                        env[key] = value.replace(str(run / 'smoke-data'), str(run / ('smoke-data-' + suffix)))
                prepare(run, env, 'smoke')
                name = 'smoke-' + suffix
                receipt_path = run / (name + '.json')
                record = spawn(run, name, [sys.executable, str(Path(__file__).with_name('smoke.py')),
                                          str(run), suffix], env)
                state.setdefault('transients', {})[name] = record
                write_json(run / 'state.json', state)
                worker_exit = 1
                try:
                    process = owned(record)
                    worker_exit = process.wait(120) if process else 1
                except Exception as exc:
                    write_json(run / (name + '-wait-error.json'), {'status': 'FAIL', 'errorType': type(exc).__name__})
                finally:
                    stop(record)
                try:
                    result = read_json(receipt_path) if receipt_path.is_file() else {'checks': {}}
                except (OSError, ValueError) as exc:
                    result = {'checks': {}, 'errorType': type(exc).__name__}
                if not isinstance(result, dict):
                    result = {'checks': {}, 'error': 'Worker receipt must be a JSON object'}
                if result.get('invocationId') != suffix:
                    result = {'checks': {}, 'error': 'Missing or mismatched fresh worker receipt'}
                outcome, code = smoke_outcome(result, worker_exit)
                result.update(status=outcome, exitCode=code, workerExitCode=worker_exit,
                              invocationId=suffix, worker=record)
                write_json(run / 'smoke.json', result)
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return code
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get('status') == 'FAIL':
        return 1
    if result.get('status') == 'BLOCKED' or any(isinstance(value, dict) and value.get('status') == 'BLOCKED'
                                        for value in result.values()):
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
