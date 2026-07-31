"""Process-wide per-run locking for AgentOS runtime mutations.

The stage-one runtime graph MVP is explicitly single-process.  This manager
provides the one lock namespace shared by runtime controllers and lifecycle
operations inside that process.  It is not a distributed lock or a database
compare-and-set substitute.
"""

from __future__ import annotations

from threading import Lock


class RunLock:
    """Short critical-section lock usable by async and legacy sync entry points."""

    def __init__(self) -> None:
        self._lock = Lock()

    def __enter__(self):
        self._lock.acquire()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self._lock.release()

    async def __aenter__(self):
        self._lock.acquire()
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        self._lock.release()


class RunLockManager:
    """Own one short-section lock shared by async and legacy sync run paths."""

    def __init__(self) -> None:
        self._locks: dict[str, RunLock] = {}
        self._registry_lock = Lock()

    def lock_for(self, run_id: str) -> RunLock:
        """Return the process-wide lock associated with ``run_id``."""

        normalized = str(run_id or "").strip()
        if not normalized:
            raise ValueError("run_id is required")
        with self._registry_lock:
            lock = self._locks.get(normalized)
            if lock is None:
                lock = RunLock()
                self._locks[normalized] = lock
            return lock


GLOBAL_RUN_LOCK_MANAGER = RunLockManager()


__all__ = ["RunLockManager", "GLOBAL_RUN_LOCK_MANAGER"]
