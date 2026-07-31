"""Single-instance guard for the SQLite-backed AgentOS runtime."""

from __future__ import annotations

import os
from pathlib import Path
from typing import IO


_LOCK_HANDLE: IO[str] | None = None


def acquire_workflow_instance_lock(db_path: str) -> IO[str]:
    global _LOCK_HANDLE
    if _LOCK_HANDLE is not None:
        return _LOCK_HANDLE
    workers = int(os.getenv("UVICORN_WORKERS", os.getenv("WEB_CONCURRENCY", "1")))
    if workers != 1:
        raise RuntimeError("SQLite WorkflowStore requires exactly one Uvicorn worker")
    lock_path = Path(db_path).resolve().parent / "runtime.instance.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            if handle.read(1) == "":
                handle.seek(0)
                handle.write("0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        raise RuntimeError(f"another AgentOS runtime owns {lock_path}") from exc
    handle.seek(0)
    handle.truncate()
    handle.write(f"pid={os.getpid()}\n")
    handle.flush()
    _LOCK_HANDLE = handle
    return handle
