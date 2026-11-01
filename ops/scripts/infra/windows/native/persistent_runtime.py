"""User-owned persistent Windows deployment of the existing production apps.

No Windows services, firewall rules, container runtime, alternate executor or
workflow database are installed. init creates identities once; up never rotates them.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
import traceback

import native_runtime as native
import desktop_runtime as desktop
import desktop_shell
import terminal_service

ROOT = native.ROOT
PORTS = [15432, 16379, 18761, 18765, 18080, 15200, 18766, 19222]
FORMAT = 'zhiyi-windows-persistent-v1'

def ports(info):
    return dict(zip(['postgres','redis','ai','host','java','frontend','terminal','debug'], [port+int(info.get('portOffset',0)) for port in PORTS]))


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
    if os.name != 'nt' or sys.version_info[:2] != (3, 14):
        raise RuntimeError('Real Windows CPython 3.14 required')
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
    return native.read_json(path) if path.exists() else {
        'format': FORMAT, 'runDirectory': str(home), 'aiPort': ports(manifest(home))['ai'] if (home/'environment.json').exists() else 18761,
        'hostPort': ports(manifest(home))['host'] if (home/'environment.json').exists() else 18765, 'processes': {}, 'desktop': False, 'backend': manifest(home).get('backend','python') if (home/'environment.json').exists() else 'python',
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
    env['AGENTOS_EXECUTION_BACKEND'] = info.get('backend','python')
    env['AGENTOS_WORKSPACE_TEST_PYTHON'] = info.get('testPython',sys.executable)
    from urllib.parse import quote
    env['AGENTOS_WORKSPACE_DATABASE_URL'] = f"postgresql://zhiyi_app:{quote(creds['db'], safe='')}@127.0.0.1:{ports(info)['postgres']}/zhiyi"
    env['AGENTOS_WORKSPACE_GRANTS_FILE'] = str(home/'hands-grants.json')
    env['ZHIYI_LOCAL_RUNTIME_WORKSPACE_PROJECTION'] = str(home/'hands-grants.json')
    if info.get('backend') == 'hands':
        env['AGENTOS_LOCAL_RUNTIME_SHELL_ENABLED'] = 'true'
        env['AGENTOS_WORKSPACE_TEST_NODE'] = shutil.which('node') or ''
        env['AGENTOS_WORKSPACE_TEST_NPM'] = shutil.which('npm.cmd') or ''
    return env


def java_environment(home, info, creds):
    return dict(env_for(home, info, creds),
        SPRING_DATASOURCE_URL=f"jdbc:postgresql://127.0.0.1:{ports(info)['postgres']}/zhiyi",
        SPRING_DATASOURCE_USERNAME='zhiyi_app', SPRING_DATASOURCE_PASSWORD=creds['db'],
        SPRING_REDIS_HOST='127.0.0.1', SPRING_REDIS_PORT=str(ports(info)['redis']), SPRING_REDIS_DATABASE='0',
        SPRING_REDIS_PASSWORD=creds['redis'], APP_JWT_SECRET=creds['jwt'],
        AI_INTERNAL_REQUIRED='true', AI_SERVICE_URL=f"http://127.0.0.1:{ports(info)['ai']}",
        SERVER_PORT=str(ports(info)['java']), SERVER_ADDRESS='127.0.0.1',
        CORS_ALLOWED_ORIGINS=f"http://127.0.0.1:{ports(info)['frontend']},kinlin-app://shell",
        APP_UPLOAD_DIR=str(home/'uploads'), SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE='3',
        SPRING_DATASOURCE_HIKARI_MINIMUM_IDLE='1')


def pg_env(creds):
    return dict(os.environ, PGHOST='127.0.0.1', PGPORT='15432', PGUSER='zhiyi_admin',
                PGPASSWORD=creds['pgadmin'], PGDATABASE='postgres', PGCLIENTENCODING='UTF8')


def sql(info, creds, text):
    # psql 的连接类报错跟随 Windows UI 语言输出 GBK（如「psql: 错误: …」）；
    # postgres 就绪轮询会反复捕获这些字节，utf-8 严格解码会让读取线程崩溃。
    # stderr 在失败分支本就不外露，replace 只保证捕获过程自身不炸。
    result = subprocess.run([str(Path(info['postgresBin'])/'psql.exe'), '-X', '-q', '-t', '-A',
                             '-v', 'ON_ERROR_STOP=1'], input=text, text=True, encoding='utf-8', errors='replace',
                            capture_output=True, env=dict(pg_env(creds),PGPORT=str(ports(info)['postgres'])))
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
    creds = {name: secrets.token_hex(32) for name in ['pgadmin','db','redis','jwt','token','hmac','test_password']}
    creds.update(key=base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(), deepseek=key)
    (home/'credentials.dpapi').write_bytes(native.dpapi(json.dumps(creds).encode()))
    info = {'format': FORMAT, 'home': str(home), 'workspace': str(workspace),
            'postgresBin': str(pg), 'memurai': str(memurai), 'database': 'zhiyi', 'databaseRole': 'zhiyi_app',
            'redisDatabases': {'java': 0, 'coordination': 1, 'providerState': 2},
            'created': datetime.now(timezone.utc).isoformat(),
            'redisLicense': 'Memurai Developer; development/testing only; 10-day maximum uptime',
            'initialized': False, 'portOffset':args.port_offset, 'backend':args.backend,
            'testPython':str(args.test_python.absolute()) if args.test_python else sys.executable,
            'backendJar':str(args.backend_jar.absolute()) if args.backend_jar else str(ROOT/'apps/backend/target/kinlin-backend-1.0.0.jar')}
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


def prepare_workspace_grants(home, info, env):
    grants = home/'hands-grants.json'
    dynamic = [g for g in native.read_json(grants).get('grants', []) if g['grantId'].startswith('wgrant_')] if grants.exists() else []
    native.write_json(grants, {'grants':dynamic+[{'grantId':'n01a-grant','workspaceId':'n01a-workspace',
        'canonicalRoot':info['workspace'],'capabilities':native.CAPS+['shell.exec'],
        'allowedCallers':['n01a-credential'],'revoked':False}]})
    # PostgreSQL is authoritative after crashes too. Missing table is possible
    # only on a first boot, before Java/Flyway; no dynamic grant may survive it.
    import psycopg
    with psycopg.connect(env['AGENTOS_WORKSPACE_DATABASE_URL']) as connection:
        exists = connection.execute("SELECT to_regclass('public.local_workspace_authorizations')").fetchone()[0]
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
    node_env = dict(env, TSX_TSCONFIG_PATH=str(ROOT/'apps/hands/tsconfig.json'))
    try:
        record = start('host',[shutil.which('node'),str(ROOT/'apps/hands/node_modules/tsx/dist/cli.mjs'),
            '--tsconfig',str(ROOT/'apps/hands/tsconfig.json'),str(ROOT/'apps/hands/hands/service-main.ts'),
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
    backend_jar = Path(info.get('backendJar',str(ROOT/'apps/backend/target/kinlin-backend-1.0.0.jar')))
    if not backend_jar.is_file():
        raise RuntimeError('Build the Java backend first: mvn -DskipTests package')
    # A leftover dev server or an orphaned service from an earlier session must
    # not block startup: stop whatever still listens, then bind the runtime's own
    # ports. The runtime itself, its ancestors and Windows session processes are
    # always refused (see native.release_port).
    target_ports = list(ports(info).values()) if use_desktop else list(ports(info).values())[:-1]
    released = native.release_ports(target_ports)
    if released:
        record_port_takeover(home, released)
    session = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+secrets.token_hex(2)
    logdir = home/'logs'/session
    logdir.mkdir()
    shell = desktop_shell.current_shell()
    state.update(processes={}, desktop=use_desktop, shell=shell, session=session)
    save(home, state)
    env = env_for(home, info, creds)
    pgdata = home/'postgres'
    passwordfile = home/'temp/pg-init-password'
    authconfig = home/'temp/redis-auth.conf'
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
            try: return sql(info, creds, 'SELECT 1;') == '1'
            except RuntimeError: return False
        desktop.wait_until(postgres_ready, pg, 60)
        if not info['initialized']:
            if not sql(info, creds, "SELECT 1 FROM pg_roles WHERE rolname='zhiyi_app';"):
                sql(info, creds, f"CREATE ROLE zhiyi_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD '{creds['db']}';")
            if not sql(info, creds, "SELECT 1 FROM pg_database WHERE datname='zhiyi';"):
                sql(info, creds, 'CREATE DATABASE zhiyi OWNER zhiyi_app;')
        # Configuration carries a DPAPI-decrypted password only during launch.
        # The stable non-secret settings are also recorded for support/backup.
        config = (f"bind 127.0.0.1\nprotected-mode yes\nport {ports(info)['redis']}\n"
                  f'dir "{(home/"redis").as_posix()}"\n'
                  'appendonly yes\nappendfsync everysec\nsave 60 1\n'
                  'maxmemory-policy noeviction\n')
        (home/'redis/settings.conf').write_text(config, encoding='utf-8')
        authconfig.write_text(config+'requirepass '+creds['redis']+'\n', encoding='utf-8')
        redis = start('redis', [info['memurai'], str(authconfig)])
        client = redis_client(creds,port=ports(info)['redis'])
        desktop.wait_until(lambda: client.ping(), redis, 60)
        client.close()
        authconfig.unlink()
        schema(home, env, not (home/'data').exists())
        prepare_workspace_grants(home, info, env)
        terminal_service.start(home, info, creds, state)
        local_env = dict(env, PYTHONPATH=os.pathsep.join([str(ROOT/'apps/local-runtime'), str(ROOT/'apps/agentOS/src')]))
        if info.get('backend') == 'hands':
            start_hands(home,info,creds,state,env,start)
        else:
            start('host', [sys.executable, '-m', 'runtime.main'], local_env)
        ai = start('ai', [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host','127.0.0.1',
                           '--port',str(ports(info)['ai']),'--workers','1'])
        desktop.wait_until(lambda: native.health(ports(info)['ai'],'/health/ready').get('status') == 'UP', ai, 180)
        java = start('java', [shutil.which('java'), '-jar', str(backend_jar)],
                     java_environment(home, info, creds))
        desktop.wait_until(lambda: native.health(ports(info)['java'],'/actuator/health/readiness').get('status') == 'UP', java, 150)
        front_env = {key:value for key,value in env.items() if key in {
            'SYSTEMROOT','WINDIR','COMSPEC','PATH','PATHEXT','USERPROFILE','APPDATA','LOCALAPPDATA','PROGRAMDATA',
            'TEMP','TMP','NO_PROXY'}}
        front_env.update(DEV_BACKEND_PROXY_TARGET=f"http://127.0.0.1:{ports(info)['java']}", VITE_API_BASE_URL='')
        frontend_mode = 'electron'
        vite = start('frontend', [shutil.which('node'), str(ROOT/'apps/frontend/node_modules/vite/bin/vite.js'),
                                  str(ROOT/'apps/frontend'), '--mode',frontend_mode,'--host','127.0.0.1','--port',str(ports(info)['frontend'])], front_env)
        desktop.wait_until(lambda: native.health(ports(info)['frontend'],'/api/health/ready').get('status') == 'UP', vite, 60)
        if use_desktop:
            appenv = desktop_shell.desktop_env(shell, front_env)
            appenv.update(terminal_service.desktop_environment(home, info, creds))
            command, cwd = desktop_shell.desktop_command(ROOT, shell, f"http://127.0.0.1:{ports(info)['frontend']}",
                                                         debug_port=ports(info)['debug'])
            # 固定本栈自己的 Chromium 用户数据目录：与桌面热更新链的默认
            # userData 隔离，避免 Electron 单实例锁把本窗口顶掉。
            command.append(f'--user-data-dir={home / "electron"}')
            record = desktop.spawn_app(home, 'logs/'+session+'/desktop', command, appenv, cwd)
            state['processes']['desktop'] = record
            save(home, state)
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
        passwordfile.unlink(missing_ok=True)
        authconfig.unlink(missing_ok=True)


def open_desktop(home):
    """Start an idle environment, focus its window, or reopen only its closed shell."""
    info, state = manifest(home), state_for(home)
    if not any(alive(record) for record in state['processes'].values()):
        return up(home, True)
    current = status(home)
    required = ('postgres', 'redis', 'host', 'ai', 'java', 'frontend')
    if not (all(current['services'].get(name, {}).get('alive') for name in required)
            and current['runtime']['coreReady']
            and all(current.get(name) for name in ('postgresReady', 'redisReady', 'javaReady'))):
        raise RuntimeError('Local services are only partially running; inspect status/logs before recovery')
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
    native.release_port(ports(info)['debug'])
    # Only OS/frontend variables reach the desktop; no DPAPI credentials are inherited.
    appenv = {key: value for key, value in os.environ.items() if key.upper() in {
        'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATH', 'PATHEXT', 'USERPROFILE', 'APPDATA',
        'LOCALAPPDATA', 'PROGRAMDATA', 'TEMP', 'TMP', 'NO_PROXY'}}
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
        result['postgresReady'] = sql(info, creds, 'SELECT 1;') == '1'
        client = redis_client(creds,port=ports(info)['redis'])
        result['redisReady'] = client.ping()
        client.close()
        result['javaReady'] = native.health(ports(info)['java'],'/actuator/health/readiness')['status'] == 'UP'
    except Exception:
        result.update(postgresReady=False, redisReady=False, javaReady=False)
    result['status'] = 'UP' if result['services'] and all(x['alive'] for x in result['services'].values()) and result['runtime']['coreReady'] and all(result.get(x) for x in ['postgresReady','redisReady','javaReady']) else 'DOWN'
    return result


def down(home):
    info, state = manifest(home), state_for(home)
    creds = native.credentials(home)
    # Exact stale identities are never signalled; occupied ports still fail below.
    records = {name:record for name,record in state['processes'].items() if alive(record)}
    stop_modes = {}
    for name,record in reversed(list(records.items())):
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
    parser.add_argument('action', choices=['init','up','open','status','down','recover','backup','restore'])
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--postgres-bin', type=Path)
    parser.add_argument('--memurai', type=Path)
    parser.add_argument('--provider-key-file', type=Path)
    parser.add_argument('--workspace', type=Path)
    parser.add_argument('--test-python', type=Path)
    parser.add_argument('--backend-jar', type=Path)
    parser.add_argument('--desktop', action='store_true')
    parser.add_argument('--backend',choices=['python','hands'],default='python')
    parser.add_argument('--port-offset',type=int,choices=range(0,1001),default=0)
    parser.add_argument('--snapshot', type=Path)
    args = parser.parse_args()
    home = args.home.absolute()
    validate_home(home)
    if not home.exists() and args.action in {'init','restore'}: home.mkdir(parents=True)
    if not home.is_dir(): raise RuntimeError('Initialize this persistent home first')
    control = home.with_name('.'+home.name+'-control')
    control.mkdir(exist_ok=True)
    with native.control_lock(control):
        if args.action == 'init': result = init(home,args)
        elif args.action == 'up': result = up(home,args.desktop)
        elif args.action == 'open': result = open_desktop(home)
        elif args.action == 'down': result = down(home)
        elif args.action == 'status': result = status(home)
        elif args.action == 'recover':
            down(home)
            result = up(home,args.desktop)
        elif args.action == 'backup': result = backup(home,args.snapshot)
        else: result = restore(home,args.snapshot)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return int(result['status'] == 'DOWN')


if __name__ == '__main__': raise SystemExit(main())
