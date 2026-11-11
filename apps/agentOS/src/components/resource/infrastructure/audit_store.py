"""线程安全的审计仓储；SQLite 按插入顺序读取，支持资源过滤和重启恢复。"""
import json
import sqlite3
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from threading import RLock
from collections import Counter
from ..domain.audit import ResourceAuditEvent


class InMemoryResourceAuditStore:
    def __init__(self) -> None:
        self._events: list[ResourceAuditEvent] = []
        self._lock = RLock()

    def append(self, event: ResourceAuditEvent) -> None:
        with self._lock:
            self._events.append(deepcopy(event))

    def list(self, resource_id: str | None = None, *, limit: int = 100) -> list[ResourceAuditEvent]:
        with self._lock:
            events = [e for e in self._events if resource_id is None or e.resource_id == resource_id]
            return deepcopy(events[-max(1, min(limit, 1000)):])

    def counts(self, resource_id: str | None = None) -> dict[str, int]:
        with self._lock:
            return dict(Counter(e.kind for e in self._events if resource_id is None or e.resource_id == resource_id))


class SQLiteResourceAuditStore:
    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
        self._lock = RLock()
        self._db.execute('CREATE TABLE IF NOT EXISTS resource_audit (id INTEGER PRIMARY KEY, kind TEXT, resource_id TEXT, occurred_at TEXT, metadata TEXT)')
        self._db.execute('CREATE INDEX IF NOT EXISTS idx_resource_audit_resource ON resource_audit(resource_id, id)')
        self._db.commit()

    def append(self, event: ResourceAuditEvent) -> None:
        with self._lock, self._db:
            self._db.execute('INSERT INTO resource_audit(kind, resource_id, occurred_at, metadata) VALUES (?, ?, ?, ?)',
                             (event.kind, event.resource_id, event.occurred_at.isoformat(), json.dumps(event.metadata)))

    def list(self, resource_id: str | None = None, *, limit: int = 100) -> list[ResourceAuditEvent]:
        where, args = ('', []) if resource_id is None else (' WHERE resource_id=?', [resource_id])
        with self._lock:
            rows = self._db.execute('SELECT kind, resource_id, occurred_at, metadata FROM resource_audit' + where + ' ORDER BY id DESC LIMIT ?', (*args, max(1, min(limit, 1000)))).fetchall()
        return [ResourceAuditEvent(k, r, datetime.fromisoformat(t), json.loads(m)) for k, r, t, m in reversed(rows)]

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def counts(self, resource_id: str | None = None) -> dict[str, int]:
        where, args = ('', []) if resource_id is None else (' WHERE resource_id=?', [resource_id])
        with self._lock:
            return dict(self._db.execute('SELECT kind, COUNT(*) FROM resource_audit' + where + ' GROUP BY kind', args).fetchall())
