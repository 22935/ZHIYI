"""Durable health state shared by independently running AgentOS processes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Protocol


@dataclass(frozen=True)
class ResourceHealthState:
    resource_id: str
    reliability: float
    latency_ms: float | None
    last_heartbeat: datetime | None
    forced_health: bool | None
    updated_at: datetime
    version: int


class ResourceHealthStore(Protocol):
    def get(self, resource_id: str) -> ResourceHealthState | None:
        ...

    def upsert(
        self,
        *,
        resource_id: str,
        reliability: float,
        latency_ms: float | None,
        last_heartbeat: datetime | None,
        forced_health: bool | None,
        updated_at: datetime,
    ) -> ResourceHealthState:
        ...


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("health timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


class InMemoryResourceHealthStore:
    """Small isolated store for unit tests and explicitly single-process use."""

    def __init__(self) -> None:
        self._states: dict[str, ResourceHealthState] = {}
        self._lock = RLock()

    def get(self, resource_id: str) -> ResourceHealthState | None:
        with self._lock:
            return self._states.get(resource_id)

    def upsert(
        self,
        *,
        resource_id: str,
        reliability: float,
        latency_ms: float | None,
        last_heartbeat: datetime | None,
        forced_health: bool | None,
        updated_at: datetime,
    ) -> ResourceHealthState:
        with self._lock:
            previous = self._states.get(resource_id)
            state = ResourceHealthState(
                resource_id=resource_id,
                reliability=reliability,
                latency_ms=latency_ms,
                last_heartbeat=_utc(last_heartbeat) if last_heartbeat is not None else None,
                forced_health=forced_health,
                updated_at=_utc(updated_at),
                version=(previous.version + 1 if previous else 1),
            )
            self._states[resource_id] = state
            return state


class SQLiteResourceHealthStore:
    """SQLite-backed health truth safe to open from multiple AgentOS processes."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            self.db_path, check_same_thread=False, timeout=30.0
        )
        self._connection.execute("PRAGMA busy_timeout = 30000")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS resource_health (
                resource_id TEXT PRIMARY KEY,
                reliability REAL NOT NULL CHECK(reliability >= 0 AND reliability <= 1),
                latency_ms REAL,
                last_heartbeat TEXT,
                forced_health INTEGER,
                updated_at TEXT NOT NULL,
                version INTEGER NOT NULL CHECK(version >= 1)
            )"""
        )
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS resource_health_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                resource_id TEXT NOT NULL,
                reliability REAL NOT NULL,
                latency_ms REAL,
                last_heartbeat TEXT,
                forced_health INTEGER,
                observed_at TEXT NOT NULL,
                version INTEGER NOT NULL
            )"""
        )
        self._connection.commit()
        self._lock = RLock()

    @staticmethod
    def _parse(row: tuple[object, ...]) -> ResourceHealthState:
        return ResourceHealthState(
            resource_id=str(row[0]),
            reliability=float(row[1]),
            latency_ms=float(row[2]) if row[2] is not None else None,
            last_heartbeat=(
                datetime.fromisoformat(str(row[3])).astimezone(timezone.utc)
                if row[3] is not None
                else None
            ),
            forced_health=(bool(row[4]) if row[4] is not None else None),
            updated_at=datetime.fromisoformat(str(row[5])).astimezone(timezone.utc),
            version=int(row[6]),
        )

    def get(self, resource_id: str) -> ResourceHealthState | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT resource_id, reliability, latency_ms, last_heartbeat, forced_health, updated_at, version "
                "FROM resource_health WHERE resource_id = ?",
                (resource_id,),
            ).fetchone()
            return self._parse(row) if row is not None else None

    def upsert(
        self,
        *,
        resource_id: str,
        reliability: float,
        latency_ms: float | None,
        last_heartbeat: datetime | None,
        forced_health: bool | None,
        updated_at: datetime,
    ) -> ResourceHealthState:
        updated = _utc(updated_at)
        heartbeat = _utc(last_heartbeat) if last_heartbeat is not None else None
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                row = self._connection.execute(
                    "SELECT version FROM resource_health WHERE resource_id = ?",
                    (resource_id,),
                ).fetchone()
                version = int(row[0]) + 1 if row is not None else 1
                values = (
                    resource_id,
                    reliability,
                    latency_ms,
                    heartbeat.isoformat() if heartbeat is not None else None,
                    None if forced_health is None else int(forced_health),
                    updated.isoformat(),
                    version,
                )
                self._connection.execute(
                    "INSERT INTO resource_health(resource_id, reliability, latency_ms, last_heartbeat, forced_health, updated_at, version) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(resource_id) DO UPDATE SET reliability=excluded.reliability, "
                    "latency_ms=excluded.latency_ms, last_heartbeat=excluded.last_heartbeat, "
                    "forced_health=excluded.forced_health, updated_at=excluded.updated_at, version=excluded.version",
                    values,
                )
                self._connection.execute(
                    "INSERT INTO resource_health_events(resource_id, reliability, latency_ms, last_heartbeat, forced_health, observed_at, version) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    values,
                )
                self._connection.commit()
                return ResourceHealthState(
                    resource_id=resource_id,
                    reliability=reliability,
                    latency_ms=latency_ms,
                    last_heartbeat=heartbeat,
                    forced_health=forced_health,
                    updated_at=updated,
                    version=version,
                )
            except Exception:
                self._connection.rollback()
                raise

    def list_events(self, resource_id: str, *, limit: int = 100) -> list[ResourceHealthState]:
        if limit < 1:
            raise ValueError("health event limit must be positive")
        rows = self._connection.execute(
            "SELECT resource_id, reliability, latency_ms, last_heartbeat, forced_health, observed_at, version "
            "FROM resource_health_events WHERE resource_id = ? ORDER BY event_id DESC LIMIT ?",
            (resource_id, limit),
        ).fetchall()
        return [self._parse(row) for row in rows]

    def close(self) -> None:
        self._connection.close()


__all__ = [
    "InMemoryResourceHealthStore",
    "ResourceHealthState",
    "ResourceHealthStore",
    "SQLiteResourceHealthStore",
]
