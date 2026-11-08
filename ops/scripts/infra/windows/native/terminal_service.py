"""Lifecycle/configuration of the desktop user's interactive terminal service."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil

import native_runtime as native
import desktop_runtime as desktop


def desktop_environment(home, info, creds):
    # A purpose-separated token never grants access to the Agent Host or provider keys.
    token = hashlib.sha256(('zhiyi-terminal-v1:' + creds['hmac']).encode()).hexdigest()
    return {'KINLIN_TERMINAL_ENDPOINT': f"http://127.0.0.1:{18766 + int(info.get('portOffset', 0))}",
            'KINLIN_TERMINAL_TOKEN': token}


def start(home, info, creds, state):
    entry = native.ROOT / 'apps/terminal/src/main.mjs'
    if not (entry.parent.parent / 'node_modules/node-pty/package.json').is_file():
        raise RuntimeError('Install terminal dependencies first: cd apps/terminal; npm ci')
    desktop_env = desktop_environment(home, info, creds)
    token_file = home / 'temp/terminal-token'
    token_file.write_text(desktop_env['KINLIN_TERMINAL_TOKEN'], encoding='utf-8')
    config = home / 'terminal-service.json'
    port = 18766 + int(info.get('portOffset', 0))
    native.write_json(config, {'port': port, 'defaultCwd': info['workspace'], 'tokenFile': str(token_file)})
    allowed = {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATH', 'PATHEXT', 'TEMP', 'TMP', 'USERPROFILE',
               'USERNAME', 'USERDOMAIN', 'HOMEDRIVE', 'HOMEPATH', 'APPDATA', 'LOCALAPPDATA',
               'PROGRAMDATA', 'PROGRAMFILES', 'PROGRAMFILES(X86)', 'PROGRAMW6432', 'PSMODULEPATH',
               'ONEDRIVE', 'ONEDRIVECONSUMER', 'ONEDRIVECOMMERCIAL'}
    environment = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    node = shutil.which('node')
    if not node:
        raise RuntimeError('Node.js is required by the terminal service')
    try:
        record = native.spawn(home, 'logs/terminal-service', [node, str(entry), '--config', str(config)], environment)
        state['processes']['terminal'] = record
        native.write_json(home / 'runtime-state.json', state)
        desktop.wait_until(lambda: native.health(port, '/health').get('status') == 'UP', record, 30)
        return record
    finally:
        token_file.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--home', required=True, type=Path)
    args = parser.parse_args()
    info = native.read_json(args.home / 'environment.json')
    print(json.dumps(desktop_environment(args.home, info, native.credentials(args.home))))
