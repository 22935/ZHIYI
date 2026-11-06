"""Preload definitions, then enter the unchanged ASGI startup after native preparation.

The release file only delays assembly. It grants no execution authority and does
not replace schema checks, instance ownership, permission checks or readiness.
"""
from __future__ import annotations

import argparse
import importlib
from pathlib import Path
import sys
import time


PRELOAD_MODULES = (
    'uvicorn',
    'fastapi',
    'app.execution.wiring',
    'app.execution.coordinator',
    'app.api.agentos_v2',
    'app.ai_engine.kylin_sdk.client',
)


def preload():
    # No app.main: its module body constructs stores and acquires the instance lock.
    for name in PRELOAD_MODULES:
        importlib.import_module(name)


def wait_for_release(path, nonce, owner_pid, owner_created, *, timeout=180):
    import psutil

    deadline = time.monotonic() + timeout
    while True:
        try:
            owner = psutil.Process(owner_pid)
            if owner.create_time() != owner_created or not owner.is_running():
                raise RuntimeError('Native startup owner changed before release')
        except psutil.NoSuchProcess as exc:
            raise RuntimeError('Native startup owner exited before release') from exc
        try:
            value = path.read_text(encoding='utf-8')
        except FileNotFoundError:
            pass
        else:
            if value != nonce:
                raise RuntimeError('Native startup release identity mismatch')
            return
        if time.monotonic() >= deadline:
            raise RuntimeError('Native startup preparation release timed out')
        time.sleep(.1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-file', required=True, type=Path)
    parser.add_argument('--nonce', required=True)
    parser.add_argument('--owner-pid', required=True, type=int)
    parser.add_argument('--owner-created', required=True, type=float)
    parser.add_argument('--port', required=True, type=int)
    args = parser.parse_args(argv)
    started = time.monotonic()
    preload()
    print(f'[startup-ai] Definitions preloaded in {time.monotonic() - started:.1f}s; waiting for preparation',
          file=sys.stderr, flush=True)
    wait_for_release(args.release_file, args.nonce, args.owner_pid, args.owner_created)
    print('[startup-ai] Preparation released; entering app.main', file=sys.stderr, flush=True)
    # Reuse the same process/module cache; no second worker or alternate runtime.
    import uvicorn
    uvicorn.run('app.main:app', host='127.0.0.1', port=args.port, workers=1)


if __name__ == '__main__':
    main()
