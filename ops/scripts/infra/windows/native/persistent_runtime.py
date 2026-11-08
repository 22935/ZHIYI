"""User-owned persistent Windows deployment of the existing production apps.

No Windows services, firewall rules, container runtime, alternate executor or
workflow database are installed. init creates identities once; up never rotates them.
"""
import argparse
import base64
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import threading
import time
import traceback

import native_runtime as native
import desktop_runtime as desktop
import desktop_shell
import terminal_service
import platform_database

ROOT = native.ROOT
PORTS = [15432, 16379, 18761, 18765, 18080, 15200, 18766, 19222]
FORMAT = 'zhiyi-windows-persistent-v1'


class StartupProgress:
    """Keep CLI stdout machine-readable; report startup stages immediately on stderr."""
    def __init__(self, path=None):
        self.path = path
        self.started = time.monotonic()
        self.stages = []
        self._lock = threading.Lock()

    @contextmanager
    def stage(self, name):
        started = time.monotonic()
        record = {'stage': name, 'status': 'RUNNING',
                  'startedAfterSeconds': round(started - self.started, 3)}
        with self._lock:
            self.stages.append(record)
            self._save()
        print(f'[startup +{started - self.started:.1f}s] {name}...', file=sys.stderr, flush=True)
        try:
            yield
        except BaseException:
            with self._lock:
                record['status'] = 'FAILED'
            raise
        else:
            with self._lock:
                record['status'] = 'DONE'
        finally:
            with self._lock:
                record['durationSeconds'] = round(time.monotonic() - started, 3)
                self._save()
            print(f'[startup] {name}: {record["status"]} ({record["durationSeconds"]:.1f}s)',
                  file=sys.stderr, flush=True)

    def _save(self):
        if self.path is not None:
            try:
                native.write_json(self.path, {'elapsedSeconds': round(time.monotonic() - self.started, 3),
                                             'stages': self.stages})
            except OSError:
                # Diagnostics must not mask the original startup/cleanup failure.
                pass

def ports(info):
    return dict(zip(['postgres','redis','ai','host','backend','frontend','terminal','debug'], [port+int(info.get('portOffset',0)) for port in PORTS]))


def protect(directory):
    """Restrict only this newly created user-owned directory; never broaden ACLs."""
    import win32api
    import win32security
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32security.TOKEN_QUERY)
    try:
        sid = win32security.ConvertSidToStringSid(win32security.GetTokenInformation(token, win32security.TokenUser)[0])
    finally:
        token.Close()
    subprocess.run(['icacls', str(directory), '/inheritance:r', '/grant:r',
                    f'*{sid}:(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def validate_home(home):
    if os.name != 'nt' or sys.version_info[:2] not in ((3, 13), (3, 14)):
        raise RuntimeError('Real Windows CPython 3.13 or 3.14 required')
    token = native.windows_token(os.getpid())
    if token['elevated'] or int(token['integritySid'].rsplit('-', 1)[1]) > 8192:
        raise RuntimeError('Run as an ordinary non-elevated Windows user')
    if not home.is_absolute() or home.resolve().is_relative_to(ROOT.resolve()):
        raise RuntimeError('Persistent home must be an absolute path outside the repository')
    for part in [home, *home.parents]:
        if part.is_symlink() or part.is_junction():
            raise RuntimeError('Persistent home may not traverse reparse directories')


def manifest(home):
    value = native.read_json(home / 'environment.json')
    if value.get('format') != FORMAT or value['home'] != str(home):
        raise RuntimeError('Persistent home identity mismatch; no data was changed')
    return value


def state_for(home):
    path = home / 'runtime-state.json'
    if path.exists():
        return native.read_json(path)
    return {
        'format': FORMAT, 'runDirectory': str(home), 'aiPort': ports(manifest(home))['ai'] if (home/'environment.json').exists() else 18761,
        'hostPort': ports(manifest(home))['host'] if (home/'environment.json').exists() else 18765, 'processes': {}, 'desktop': False,
    }


def save(home, state):
    temporary = home / 'runtime-state.next.json'
    native.write_json(temporary, state)
    temporary.replace(home / 'runtime-state.json')


def env_for(home, info, creds):
    env = native.environment(home, state_for(home), creds)
    env.update({
        'NO_PROXY': '127.0.0.1,localhost',
        'ZHIYI_LOCAL_RUNTIME_WORKSPACE_ROOT': info['workspace'],
        'TOOL_CODEBASE_ROOT': info['workspace'],
        'DEEPSEEK_API_KEY': creds['deepseek'], 'DEEPSEEK_BASE_URL': 'https://api.deepseek.com',
        'DEEPSEEK_MODEL': 'deepseek-chat', 'AGENTOS_LLM_PROVIDER': 'deepseek',
        'AGENTOS_LLM_MODEL': 'deepseek-chat', 'TEXT_ENGINE': 'deepseek', 'DEEPSEEK_ENABLED': 'true',
        'REDIS_PASSWORD': creds['redis'],
        'AGENTOS_COORDINATION_REDIS_URL': f"redis://127.0.0.1:{ports(info)['redis']}/1",
        'PROVIDER_STATE_REDIS_URL': f"redis://127.0.0.1:{ports(info)['redis']}/2",
    })
    env['AGENTOS_EXECUTION_BACKEND'] = 'hands'  # hands 是唯一执行后端（DSH 基座）。
    env['AGENTOS_WORKSPACE_TEST_PYTHON'] = info.get('testPython',sys.executable)
    from urllib.parse import quote
    env['AGENTOS_WORKSPACE_DATABASE_URL'] = f"postgresql://zhiyi_app:{quote(creds['db'], safe='')}@127.0.0.1:{ports(info)['postgres']}/zhiyi"
    env['AGENTOS_WORKSPACE_GRANTS_FILE'] = str(home/'hands-grants.json')
    env['ZHIYI_LOCAL_RUNTIME_WORKSPACE_PROJECTION'] = str(home/'hands-grants.json')
    env['AGENTOS_LOCAL_RUNTIME_SHELL_ENABLED'] = 'true'
    env['AGENTOS_WORKSPACE_TEST_NODE'] = shutil.which('node') or ''
    env['AGENTOS_WORKSPACE_TEST_NPM'] = shutil.which('npm.cmd') or ''
    return env


def backend_environment(home, info, creds):
    env = env_for(home, info, creds)
    env.update({
        'ZHIYI_DATABASE_URL': env['AGENTOS_WORKSPACE_DATABASE_URL'],
        'AI_SERVICE_URL': f"http://127.0.0.1:{ports(info)['ai']}",
        'ZHIYI_BACKEND_TS_PORT': str(ports(info)['backend']),
        'ZHIYI_BACKEND_TS_DEV_ORIGIN': f"http://127.0.0.1:{ports(info)['frontend']}",
        'APP_UPLOAD_DIR': str(home/'uploads'),
    })
    return env


def prepare_platform(home, info, creds):
    env = backend_environment(home, info, creds)
    identity_env = platform_database.prepare(home, env['ZHIYI_DATABASE_URL'],
                                             ROOT/'apps/backend/migrations')
    env.update(identity_env)
    return env


def pg_env(creds):
    return dict(os.environ, PGHOST='127.0.0.1', PGPORT='15432', PGUSER='zhiyi_admin',
                PGPASSWORD=creds['pgadmin'], PGDATABASE='postgres', PGCLIENTENCODING='UTF8')


def sql(info, creds, text, *, timeout=None):
    # psql 的连接类报错跟随 Windows UI 语言输出 GBK（如「psql: 错误: …」）；
    # postgres 就绪轮询会反复捕获这些字节，utf-8 严格解码会让读取线程崩溃。
    # stderr 在失败分支本就不外露，replace 只保证捕获过程自身不炸。
    result = subprocess.run([str(Path(info['postgresBin'])/'psql.exe'), '-X', '-q', '-t', '-A',
                             '-v', 'ON_ERROR_STOP=1'], input=text, text=True, encoding='utf-8', errors='replace',
                            capture_output=True, timeout=timeout,
                            env=dict(pg_env(creds),PGPORT=str(ports(info)['postgres']),PGCONNECT_TIMEOUT='3'))
    if result.returncode:
        # DDL errors can echo a password literal; never expose that stderr.
        raise RuntimeError('Native PostgreSQL administrative command failed')
    return result.stdout.strip()


def redis_client(creds, db=0, *, port=16379):
    import redis
    return redis.Redis(host='127.0.0.1', port=port, password=creds['redis'],
                       db=db, socket_timeout=3, socket_connect_timeout=3)


def alive(record):
    try: return native.owned(record)
    except RuntimeError: return None  # recycled PID belongs to someone else


def init(home, args):
    if (home/'environment.json').exists():
        manifest(home)
        return {'status': 'READY', 'initializedNow': False, 'home': str(home)}
    if any(home.iterdir()):
        raise RuntimeError('Refusing to initialize a nonempty unrecognized home')
    pg = args.postgres_bin.resolve(strict=True)
    memurai = args.memurai.resolve(strict=True)
    for name in ['postgres.exe', 'initdb.exe', 'pg_ctl.exe', 'psql.exe']:
        if not (pg/name).is_file(): raise RuntimeError(f'Missing PostgreSQL executable: {name}')
    keyfile = args.provider_key_file or ROOT/'.secrets/kinlin-win-p1-001/deepseek_api_key'
    key = keyfile.read_text(encoding='utf-8').strip()
    if not key: raise RuntimeError('Configure a real provider key before initialization')
    workspace = args.workspace.resolve(strict=True) if args.workspace else home/'workspace'
    if workspace.exists() and (not workspace.is_dir() or workspace.is_symlink() or workspace.is_junction()):
        raise RuntimeError('Workspace must be a real directory')
    protect(home)
    for path in [home/'temp', home/'logs', home/'redis', workspace]: path.mkdir(exist_ok=True)
    (home/'.env').write_text('', encoding='utf-8')
    creds = {name: secrets.token_hex(32) for name in ['pgadmin','db','redis','token','hmac']}
    creds.update(key=base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(), deepseek=key)
    (home/'credentials.dpapi').write_bytes(native.dpapi(json.dumps(creds).encode()))
    info = {'format': FORMAT, 'home': str(home), 'workspace': str(workspace),
            'postgresBin': str(pg), 'memurai': str(memurai), 'database': 'zhiyi', 'databaseRole': 'zhiyi_app',
            'redisDatabases': {'backend': 0, 'coordination': 1, 'providerState': 2},
            'created': datetime.now(timezone.utc).isoformat(),
            'redisLicense': 'Memurai Developer; development/testing only; 10-day maximum uptime',
            'initialized': False, 'portOffset':args.port_offset,
            'testPython':str(args.test_python.absolute()) if args.test_python else sys.executable,
            'backendEntry':str(ROOT/'apps/backend/dist/main.js')}
    native.write_json(home/'environment.json', info)
    save(home, state_for(home))
    return {'status': 'READY', 'initializedNow': True, 'home': str(home), 'workspace': str(workspace)}


def schema(home, env, first):
    if first:
        native.prepare(home, env, 'logs/initialize')
    else:
        command = [sys.executable, str(ROOT/'scripts/prepare_agentos_runtime.py')]
        with (home/'logs/schema-inspect.log').open('ab') as log:
            subprocess.run(command, cwd=home, env=env, stdout=log, stderr=log, check=True)


def prepare_workspace_grants(home, info, env, backend=None):
    grants = home/'hands-grants.json'
    dynamic = [g for g in native.read_json(grants).get('grants', []) if g['grantId'].startswith('wgrant_')] if grants.exists() else []
    if not grants.exists():
        native.write_json(grants, {'grants':dynamic+[{'grantId':'n01a-grant','workspaceId':'n01a-workspace',
        'canonicalRoot':info['workspace'],'capabilities':native.CAPS+['shell.exec'],
        'allowedCallers':['n01a-credential'],'revoked':False}]})
    # PostgreSQL is authoritative after crashes too. Missing table is possible
    # only on a first boot, before platform initialization; no dynamic grant may survive it.
    import psycopg
    def authority_table_ready():
        with psycopg.connect(env['AGENTOS_WORKSPACE_DATABASE_URL'], connect_timeout=5) as connection:
            return connection.execute("SELECT to_regclass('public.local_workspace_authorizations')").fetchone()[0]
    if backend is not None:
        # Wait for the actual authority table. Projection below
        # still fails closed if the resulting schema/data is incompatible.
        desktop.wait_until(authority_table_ready, backend, 150)
    exists = authority_table_ready()
    if exists:
        command = [sys.executable, '-c',
            'import os; from app.execution.workspace_authority import WorkspaceAuthority; '
            'a=WorkspaceAuthority(os.environ, os.environ["AGENTOS_LOCAL_RUNTIME_RESOURCE_ID"]); '
            'c=a.connect(); a._project(c); c.close()']
        subprocess.run(command, env=env, cwd=home, check=True)
    elif dynamic:
        raise RuntimeError('Dynamic workspace authority schema missing; refusing stale grant projection')


def start_hands(home, info, creds, state, env, start):
    grants = home/'hands-grants.json'
    keys = home/'temp/hands-keys.json'
    native.write_json(keys, {'credentials':[{'credentialId':'n01a-credential','secret':creds['hmac']}]})
    config = home/'hands-service.json'
    native.write_json(config, {'workspaceRoot':info['workspace'],'credentialsFile':str(keys),
        'grantsFile':str(grants),'dataDir':str(home/'hands-ledger'),'host':'127.0.0.1',
        'port':ports(info)['host'],'confinement':'none','dynamicWorkspaces':True})
    node_env = dict(env, TSX_TSCONFIG_PATH=str(ROOT/'apps/agentOS/src/hands/tsconfig.json'))
    try:
        record = start('host',[shutil.which('node'),str(ROOT/'apps/agentOS/src/hands/node_modules/tsx/dist/cli.mjs'),
            '--tsconfig',str(ROOT/'apps/agentOS/src/hands/tsconfig.json'),str(ROOT/'apps/agentOS/src/hands/hands/service-main.ts'),
            '--config',str(config)],node_env)
        desktop.wait_until(lambda:native.health(ports(info)['host'],'/v1/health').get('ok'),record,60)
    finally:
        keys.unlink(missing_ok=True)


def record_port_takeover(home, released):
    """Persist which processes were stopped to take over the runtime ports.

    The launcher console closes on success, so this file is the only trace.
    Command lines are intentionally dropped: they may carry tokens.
    """
    native.write_json(home/'port-takeover.json', {
        'at': datetime.now(timezone.utc).isoformat(),
        'released': [{'port': item['port'], 'pid': item['pid'],
                      'executable': (item.get('process') or {}).get('executable'),
                      'outcome': item.get('outcome')} for item in released]})


def up(home, use_desktop):
    info, creds, state = manifest(home), native.credentials(home), state_for(home)
    workspace = Path(info['workspace'])
    if not workspace.is_dir() or workspace.is_symlink() or workspace.is_junction() or str(workspace.resolve()) != info['workspace']:
        raise RuntimeError('Startup-issued workspace root changed; refusing to reissue authority')
    if any(alive(record) for record in state['processes'].values()):
        raise RuntimeError('This persistent environment already owns running processes; use status or recover')
    backend_entry = ROOT/'apps/backend/scripts/dev.mjs'
    if (not backend_entry.is_file()
            or not (ROOT/'apps/backend/node_modules/typescript/lib/typescript.js').is_file()):
        raise RuntimeError('Install backend development dependencies first: cd apps/backend && npm ci')
    # Never take over an unrelated process, even in the development launcher.
    target_ports = list(ports(info).values()) if use_desktop else list(ports(info).values())[:-1]
    for port in target_ports:
        native.port_free(port)
    session = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+secrets.token_hex(2)
    logdir = home/'logs'/session
    logdir.mkdir()
    progress = StartupProgress(logdir/'startup-timings.json')
    shell = desktop_shell.current_shell()
    state.update(processes={}, desktop=use_desktop, shell=shell, session=session)
    save(home, state)
    env = env_for(home, info, creds)
    pgdata = home/'postgres'
    passwordfile = home/'temp/pg-init-password'
    authconfig = home/'temp/redis-auth.conf'
    release_file = home/'temp'/f'ai-start-{session}.ready'
    release_next = release_file.with_suffix('.next')
    def start(name, command, child_env=env):
        record = native.spawn(home, 'logs/'+session+'/'+name, command, child_env)
        state['processes'][name] = record
        save(home, state)
        return record
    try:
        if not (pgdata/'PG_VERSION').exists():
            passwordfile.write_text(creds['pgadmin'], encoding='utf-8')
            with (logdir/'initdb.log').open('ab') as log:
                subprocess.run([str(Path(info['postgresBin'])/'initdb.exe'), '-D', str(pgdata),
                                '-U', 'zhiyi_admin', '--encoding=UTF8', '--locale=C',
                                '--auth=scram-sha-256', '--pwfile='+str(passwordfile)],
                               stdout=log, stderr=log, check=True)
            passwordfile.unlink()
            with (pgdata/'postgresql.conf').open('a', encoding='utf-8') as file:
                file.write(f"\nlisten_addresses='127.0.0.1'\nport={ports(info)['postgres']}\npassword_encryption='scram-sha-256'\n")
        pg = start('postgres', [str(Path(info['postgresBin'])/'postgres.exe'), '-D', str(pgdata)])
        def postgres_ready():
            try: return sql(info, creds, 'SELECT 1;', timeout=5) == '1'
            except (RuntimeError, subprocess.TimeoutExpired): return False
        # Configuration carries a DPAPI-decrypted password only during launch.
        # The stable non-secret settings are also recorded for support/backup.
        config = (f"bind 127.0.0.1\nprotected-mode yes\nport {ports(info)['redis']}\n"
                  f'dir "{(home/"redis").as_posix()}"\n'
                  'appendonly yes\nappendfsync everysec\nsave 60 1\n'
                  'maxmemory-policy noeviction\n')
        (home/'redis/settings.conf').write_text(config, encoding='utf-8')
        authconfig.write_text(config+'requirepass '+creds['redis']+'\n', encoding='utf-8')
        redis = start('redis', [info['memurai'], str(authconfig)])
        # Both database processes are now starting; readiness remains mandatory.
        with progress.stage('PostgreSQL readiness'):
            desktop.wait_until(postgres_ready, pg, 60)
        if not info['initialized']:
            if not sql(info, creds, "SELECT 1 FROM pg_roles WHERE rolname='zhiyi_app';"):
                sql(info, creds, f"CREATE ROLE zhiyi_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD '{creds['db']}';")
            if not sql(info, creds, "SELECT 1 FROM pg_database WHERE datname='zhiyi';"):
                sql(info, creds, 'CREATE DATABASE zhiyi OWNER zhiyi_app;')
        client = redis_client(creds,port=ports(info)['redis'])
        with progress.stage('Redis readiness'):
            try:
                desktop.wait_until(lambda: client.ping(), redis, 60)
            finally:
                client.close()
        authconfig.unlink()
        # Complete new-Home metadata before binding LocalIdentity to its bytes.
        # Existing Homes and their verified identity files are never rewritten.
        if not info['initialized']:
            info['initialized'] = True
            native.write_json(home/'environment.next.json', info)
            (home/'environment.next.json').replace(home/'environment.json')
        with progress.stage('Validate platform schema and LocalIdentity'):
            backend_env = prepare_platform(home, info, creds)
        front_env = {key:value for key,value in env.items() if key in {
            'SYSTEMROOT','WINDIR','COMSPEC','PATH','PATHEXT','USERPROFILE','APPDATA','LOCALAPPDATA','PROGRAMDATA',
            'TEMP','TMP','NO_PROXY'}}
        front_env.update(DEV_BACKEND_PROXY_TARGET=f"http://127.0.0.1:{ports(info)['backend']}", VITE_API_BASE_URL='')
        # Vite can prepare its module graph while schema/AI/Backend become ready.
        # Its proxy readiness gate stays below all backend gates; Electron never
        # opens early. A startup failure still cleans up every recorded child.
        with progress.stage('Launch Node backend and frontend'):
            backend = start('backend', [shutil.which('node'), str(backend_entry)], backend_env)
            vite = start('frontend', [shutil.which('node'), str(ROOT/'apps/frontend/node_modules/vite/bin/vite.js'),
                                      str(ROOT/'apps/frontend'), '--mode','electron','--host','127.0.0.1','--port',str(ports(info)['frontend'])], front_env)
        # Preload only audited definitions. app.main (and therefore store/lock
        # construction and recovery) remains behind the per-launch release file.
        import psutil
        owner = native.identity(psutil.Process(os.getpid()))
        nonce = secrets.token_hex(16)
        with progress.stage('Launch gated AI preload'):
            ai = start('ai', [sys.executable, '-m', 'app.native_startup',
                              '--release-file', str(release_file), '--nonce', nonce,
                              '--owner-pid', str(owner['pid']), '--owner-created', str(owner['created']),
                              '--port', str(ports(info)['ai'])])

        def inspect_schema():
            with progress.stage('Inspect persistent schemas'):
                schema(home, env, not (home/'data').exists())

        def prepare_grants():
            with progress.stage('Prepare workspace grants'):
                prepare_workspace_grants(home, info, env, backend)

        # SQLite preparation and PostgreSQL/JSON grant projection use separate
        # stores. Join both workers before release or cleanup; no worker writes
        # runtime-state.json and none can outlive the preparation boundary.
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix='native-prepare') as preparation:
            futures = [preparation.submit(inspect_schema), preparation.submit(prepare_grants)]
            for future in as_completed(futures):
                future.result()
        with progress.stage('Terminal service readiness'):
            terminal_service.start(home, info, creds, state)
        start_hands(home,info,creds,state,env,start)
        with progress.stage('AI service readiness'):
            release_next.write_text(nonce, encoding='utf-8')
            release_next.replace(release_file)
            desktop.wait_until(lambda: native.health(ports(info)['ai'],'/health/ready').get('status') == 'UP', ai, 180)
        with progress.stage('Backend service readiness'):
            desktop.wait_until(lambda: native.health(ports(info)['backend'],'/health/ready').get('status') == 'UP', backend, 150)
        with progress.stage('Frontend proxy readiness'):
            desktop.wait_until(lambda: native.health(ports(info)['frontend'],'/api/health/ready').get('status') == 'UP', vite, 60)
        if use_desktop:
            appenv = desktop_shell.desktop_env(shell, front_env)
            appenv['KINLIN_API_ORIGIN'] = f"http://127.0.0.1:{ports(info)['backend']}"
            appenv.update(terminal_service.desktop_environment(home, info, creds))
            command, cwd = desktop_shell.desktop_command(ROOT, shell, f"http://127.0.0.1:{ports(info)['frontend']}",
                                                         debug_port=ports(info)['debug'])
            # 固定本栈自己的 Chromium 用户数据目录：与桌面热更新链的默认
            # userData 隔离，避免 Electron 单实例锁把本窗口顶掉。
            command.append(f'--user-data-dir={home / "electron"}')
            record = desktop.spawn_app(home, 'logs/'+session+'/desktop', command, appenv, cwd)
            state['processes']['desktop'] = record
            save(home, state)
            with progress.stage('Electron window readiness'):
                desktop.wait_until(desktop_shell.ready_check(ports(info)['debug']), record, 240)
                state['desktopWindows'] = desktop.show_desktop(record, desktop_shell.window_classes(shell))
            save(home, state)
        if not info['initialized']:
            info['initialized'] = True
            temporary = home/'environment.next.json'
            native.write_json(temporary, info)
            temporary.replace(home/'environment.json')
        result = status(home)
        native.write_json(logdir/'up.json', result)
        return result
    except BaseException as exc:
        # 先落盘原始栈与服务日志尾部，再尝试清理；清理失败不得掩盖首因。
        try:
            failure = {'error': f'{type(exc).__name__}: {exc}', 'traceback': traceback.format_exc(),
                       'session': session, 'logs': {}}
            for logfile in sorted(logdir.glob('*.log')):
                try:
                    failure['logs'][logfile.name] = logfile.read_text(encoding='utf-8', errors='replace').splitlines()[-30:]
                except OSError as read_error:
                    failure['logs'][logfile.name] = [f'<unreadable: {read_error}>']
            native.write_json(logdir/'up-failure.json', failure)
        except Exception:
            pass
        try:
            down(home)
        except Exception as cleanup:
            try:
                native.write_json(logdir/'up-failure-cleanup.json', {'error': f'{type(cleanup).__name__}: {cleanup}'})
            except Exception:
                pass
        raise
    finally:
        release_file.unlink(missing_ok=True)
        release_next.unlink(missing_ok=True)
        passwordfile.unlink(missing_ok=True)
        authconfig.unlink(missing_ok=True)


def watch_backend(home):
    """Switch only the identity-verified platform process to its stable watcher."""
    info, state = manifest(home), state_for(home)
    entry = ROOT/'apps/backend/scripts/dev.mjs'
    compiler = ROOT/'apps/backend/node_modules/typescript/lib/typescript.js'
    node = shutil.which('node')
    if not node or not entry.is_file() or not compiler.is_file():
        raise RuntimeError('Install backend development dependencies first: cd apps/backend && npm ci')
    record = state['processes'].get('backend')
    if not record or not alive(record):
        raise RuntimeError('The recorded backend is not running; inspect status before starting it')
    command = record.get('command', [])
    if (len(command) != 2 or Path(command[0]) != Path(node)
            or Path(command[1]) not in {entry, ROOT/'apps/backend/dist/main.js'}):
        raise RuntimeError('The recorded backend is not a recognized repository entry')
    if Path(command[1]) == entry:
        if native.health(ports(info)['backend'], '/health/ready').get('status') != 'UP':
            raise RuntimeError('Backend watcher is running but its service is not ready; inspect its log')
        return {'status': 'UP', 'backendWatch': True, 'changed': False}
    # Validate existing identity/schema before touching the live process.
    env = prepare_platform(home, info, native.credentials(home))
    session = state.get('session', 'backend')
    log = 'logs/'+session+'/backend-watch-'+secrets.token_hex(3)
    native.stop(record, allow_terminate=False)
    state['processes'].pop('backend')
    save(home, state)
    replacement = None
    try:
        replacement = native.spawn(home, log, [node, str(entry)], env)
        state['processes']['backend'] = replacement
        save(home, state)
        desktop.wait_until(lambda: native.health(ports(info)['backend'], '/health/ready')['status'] == 'UP',
                           replacement, 60)
    except BaseException:
        if replacement is not None:
            native.stop(replacement, allow_terminate=False)
        restored = native.spawn(home, log+'-rollback', command, env)
        state['processes']['backend'] = restored
        save(home, state)
        desktop.wait_until(lambda: native.health(ports(info)['backend'], '/health/ready')['status'] == 'UP',
                           restored, 30)
        raise RuntimeError('Backend watcher activation failed; restored the previous backend entry') from None
    return {'status': 'UP', 'backendWatch': True, 'changed': True,
            'backendPid': replacement['pid'], 'log': str(home/(log+'.log'))}


def open_desktop(home):
    """Start an idle environment, focus its window, or reopen only its closed shell."""
    info, state = manifest(home), state_for(home)
    if not any(alive(record) for record in state['processes'].values()):
        return up(home, True)
    with StartupProgress().stage('Check existing services'):
        current = status(home)
    required = ('postgres', 'redis', 'host', 'ai', 'backend', 'frontend')
    if not (all(current['services'].get(name, {}).get('alive') for name in required)
            and current['runtime']['coreReady']
            and all(current.get(name) for name in ('postgresReady', 'redisReady', 'backendReady'))):
        unavailable = [name for name in required if not current['services'].get(name, {}).get('alive')]
        unavailable += [name for name, key in [('postgres', 'postgresReady'), ('redis', 'redisReady'), ('backend', 'backendReady')]
                        if not current.get(key) and name not in unavailable]
        if not current['runtime']['coreReady']:
            unavailable += [name for name in ('host', 'ai')
                            if current['runtime'].get('services', {}).get(name, {}).get('status') != 'PASS'
                            and name not in unavailable]
        raise RuntimeError('Local services are only partially running; unavailable: '
                           + ', '.join(unavailable) + '; inspect status/logs before recovery')
    shell = desktop_shell.current_shell()
    terminal = state['processes'].get('terminal')
    if not terminal or not alive(terminal):
        terminal_service.start(home, info, native.credentials(home), state)
    record = state['processes'].get('desktop')
    if record and alive(record):
        windows = desktop.show_desktop(record, desktop_shell.window_classes(shell))
        if not windows:
            raise RuntimeError('Desktop process exists but has no window; inspect its log')
        return dict(current, desktopWindows=windows)
    native.port_free(ports(info)['debug'])
    # Only OS/frontend variables reach the desktop; no DPAPI credentials are inherited.
    appenv = {key: value for key, value in os.environ.items() if key.upper() in {
        'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATH', 'PATHEXT', 'USERPROFILE', 'APPDATA',
        'LOCALAPPDATA', 'PROGRAMDATA', 'TEMP', 'TMP', 'NO_PROXY'}}
    appenv['KINLIN_API_ORIGIN'] = f"http://127.0.0.1:{ports(info)['backend']}"
    appenv.update(terminal_service.desktop_environment(home, info, native.credentials(home)))
    command, cwd = desktop_shell.desktop_command(ROOT, shell, f"http://127.0.0.1:{ports(info)['frontend']}",
                                                 debug_port=ports(info)['debug'])
    command.append(f'--user-data-dir={home / "electron"}')
    logname = 'logs/desktop-reopen-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + secrets.token_hex(2)
    record = desktop.spawn_app(home, logname, command, desktop_shell.desktop_env(shell, appenv), cwd)
    state.update(desktop=True, shell=shell)
    state['processes']['desktop'] = record
    save(home, state)
    desktop.wait_until(desktop_shell.ready_check(ports(info)['debug']), record, 240)
    state['desktopWindows'] = desktop.show_desktop(record, desktop_shell.window_classes(shell))
    save(home, state)
    return status(home)


def status(home):
    info, state = manifest(home), state_for(home)
    result = {'home':str(home), 'workspace':info['workspace'], 'services':{},
              'runtime':native.snapshot(state), 'redisLicense':info['redisLicense']}
    for name, record in state['processes'].items():
        result['services'][name] = {'alive':alive(record) is not None, 'process':record}
    try:
        creds = native.credentials(home)
    except Exception:
        result.update(postgresReady=False, redisReady=False, backendReady=False)
    else:
        def redis_ready():
            client = redis_client(creds, port=ports(info)['redis'])
            try:
                return client.ping()
            finally:
                client.close()
        # One dead backend must not falsely mark healthy PostgreSQL/Redis DOWN.
        for name, key, check in [
            ('postgres', 'postgresReady', lambda: sql(info, creds, 'SELECT 1;', timeout=5) == '1'),
            ('redis', 'redisReady', redis_ready),
            ('backend', 'backendReady', lambda: native.health(ports(info)['backend'], '/health/ready')['status'] == 'UP'),
        ]:
            try:
                result[key] = bool(result['services'].get(name, {}).get('alive') and check())
            except Exception:
                result[key] = False
    result['status'] = 'UP' if result['services'] and all(x['alive'] for x in result['services'].values()) and result['runtime']['coreReady'] and all(result.get(x) for x in ['postgresReady','redisReady','backendReady']) else 'DOWN'
    return result


def down(home):
    info, state = manifest(home), state_for(home)
    creds = native.credentials(home)
    # Exact stale identities are never signalled; occupied ports still fail below.
    records = {name:record for name,record in state['processes'].items() if alive(record)}
    stop_modes = {}
    # Startup is now parallel: insertion order no longer describes dependencies.
    # Runtime cleanup may still use Host/terminal, so stop AI before its providers.
    stop_order = ('desktop', 'frontend', 'ai', 'host', 'terminal', 'backend', 'java', 'redis', 'postgres')
    ordered = [name for name in reversed(records) if name not in stop_order]
    ordered += [name for name in stop_order if name in records]
    progress = StartupProgress()
    for name in ordered:
        record = records[name]
        with progress.stage('Stop ' + name):
            if name == 'desktop':
                desktop.close_desktop(record, desktop_shell.window_classes(state.get('shell','electron')))
                stop_modes[name] = native.stop(record) or 'window-closed'
            elif name == 'postgres':
                subprocess.run([str(Path(info['postgresBin'])/'pg_ctl.exe'), '-D', str(home/'postgres'),
                                'stop','-m','fast','-w','-t','45'], check=True, capture_output=True)
                stop_modes[name] = 'pg_ctl'
            elif name == 'redis':
                with redis_client(creds,port=ports(info)['redis']) as client: client.shutdown(save=True)
                parent = alive(record)
                if parent: parent.wait(20)
                stop_modes[name] = 'shutdown'
            else:
                stop_modes[name] = native.stop(record) or 'already-exited'
    for port in list(ports(info).values()) if state.get('desktop') else list(ports(info).values())[:-1]: native.port_free(port)
    cleaned = dict(state, processes=records)
    # This keeps the existing Windows workflow lock and exclusive-handle checks.
    cleanup = native.down(home, cleaned, preserve_credentials=True)
    escalated = sorted(name for name, mode in stop_modes.items() if mode in {'terminated', 'killed'})
    if escalated:
        print(f'WARNING: graceful stop unavailable for {escalated}; verified process trees were terminated',
              file=sys.stderr, flush=True)
    result = {'status':'PASS','home':str(home),'cleanup':cleanup,'persistentCredentialsRetained':True,
              'stopModes':stop_modes,'escalated':escalated}
    for name in ['pg-init-password','redis-auth.conf','hands-keys.json']:
        (home/'temp'/name).unlink(missing_ok=True)
    native.write_json(home/'logs/last-down.json', result)
    return result


def require_stopped(home):
    if any(alive(record) for record in state_for(home)['processes'].values()):
        raise RuntimeError('Stop the application before cold backup or restore')
    for port in ports(manifest(home)).values(): native.port_free(port)


def backup(home, destination):
    require_stopped(home)
    if not destination or not destination.is_absolute() or destination.exists() or destination.resolve().is_relative_to(home):
        raise RuntimeError('Snapshot must be a new absolute directory outside the persistent home')
    # Full cold cluster backup, same PostgreSQL major/binaries and same home path.
    # Keeping absolute content paths preserves the canonical Artifact contract.
    destination.mkdir(parents=True)
    protect(destination)
    payload = destination/'payload'
    excluded = {'logs','webview','temp','lifecycle.lock'}
    # Do not follow a workspace reparse point while creating a cold backup.
    for directory, directories, filenames in os.walk(home, followlinks=False):
        if Path(directory) == home:
            directories[:] = [name for name in directories if name not in excluded]
        for name in [*directories, *filenames]:
            candidate = Path(directory)/name
            if candidate.is_symlink() or candidate.is_junction():
                raise RuntimeError('Backup refuses reparse points')
    shutil.copytree(home, payload, symlinks=True,
                    ignore=lambda directory,names: set(names)&excluded if Path(directory)==home else set())
    files = {}
    for path in payload.rglob('*'):
        if path.is_symlink() or path.is_junction():
            raise RuntimeError('Backup refuses reparse points; use a separately managed workspace backup')
        if path.is_file(): files[str(path.relative_to(payload))] = hashlib.sha256(path.read_bytes()).hexdigest()
    result = {'format':FORMAT+'-cold-backup','home':str(home),'files':files,
              'credentials':'Current Windows user DPAPI; same user/machine required',
              'externalWorkspaceIncluded':False,'created':datetime.now(timezone.utc).isoformat()}
    native.write_json(destination/'snapshot.json', result)
    return {'status':'PASS','snapshot':str(destination),'files':len(files)}


def restore(home, source):
    require_stopped(home)
    if not source or not source.is_absolute(): raise RuntimeError('Absolute snapshot required')
    receipt = native.read_json(source/'snapshot.json')
    if receipt.get('format') != FORMAT+'-cold-backup' or receipt.get('home') != str(home):
        raise RuntimeError('Cold restore requires the original home path and PostgreSQL binary version')
    payload = source/'payload'
    for name,digest in receipt['files'].items():
        file = payload/name
        if not file.resolve().is_relative_to(payload.resolve()) or file.is_symlink() or file.is_junction():
            raise RuntimeError('Invalid snapshot path')
        if hashlib.sha256(file.read_bytes()).hexdigest() != digest: raise RuntimeError('Snapshot checksum mismatch')
    # Verify DPAPI before moving any current state. Keep the entire pre-restore
    # home as a sibling rollback copy; nothing is recursively deleted.
    native.credentials(payload)
    previous = home.with_name(home.name+'.pre-restore-'+secrets.token_hex(5))
    if previous.resolve().parent != home.resolve().parent or previous.exists():
        raise RuntimeError('Unsafe rollback directory')
    home.rename(previous)
    try:
        shutil.copytree(payload, home)
        for name in ['logs','temp','webview']: (home/name).mkdir(exist_ok=True)
        protect(home)
    except BaseException:
        raise RuntimeError('Restore interrupted; original home retained at '+str(previous))
    return {'status':'PASS','home':str(home),'rollbackCopy':str(previous),'snapshot':str(source)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init','up','open','status','down','recover','watch-backend','backup','restore'])
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--postgres-bin', type=Path)
    parser.add_argument('--memurai', type=Path)
    parser.add_argument('--provider-key-file', type=Path)
    parser.add_argument('--workspace', type=Path)
    parser.add_argument('--test-python', type=Path)
    parser.add_argument('--desktop', action='store_true')
    parser.add_argument('--port-offset',type=int,choices=range(0,1001),default=0)
    parser.add_argument('--snapshot', type=Path)
    args = parser.parse_args()
    home = args.home.absolute()
    validate_home(home)
    if not home.exists() and args.action in {'init','restore'}: home.mkdir(parents=True)
    if not home.is_dir(): raise RuntimeError('Initialize this persistent home first')
    print(f'[startup] {args.action}: checking environment and lifecycle lock', file=sys.stderr, flush=True)
    control = home.with_name('.'+home.name+'-control')
    control.mkdir(exist_ok=True)
    with native.control_lock(control):
        if args.action == 'init': result = init(home,args)
        elif args.action == 'up': result = up(home,args.desktop)
        elif args.action == 'open': result = open_desktop(home)
        elif args.action == 'watch-backend': result = watch_backend(home)
        elif args.action == 'down': result = down(home)
        elif args.action == 'status': result = status(home)
        elif args.action == 'recover':
            with StartupProgress().stage('Stop recorded services for recovery'):
                down(home)
            result = up(home,args.desktop)
        elif args.action == 'backup': result = backup(home,args.snapshot)
        else: result = restore(home,args.snapshot)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return int(result['status'] == 'DOWN')


if __name__ == '__main__': raise SystemExit(main())
