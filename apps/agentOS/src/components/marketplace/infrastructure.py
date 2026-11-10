"""资源商店目录、安装任务与包校验的基础设施实现。"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from threading import RLock

from components.resource.infrastructure.sqlite.connection import configure_sqlite_connection

from .contracts import CatalogItem, InstallationJob
from .ports import Catalog, InstallationJobStore


class InMemoryCatalog:
    """用于测试和受控进程内平台目录的不可变目录映射。"""

    def __init__(self, items: list[CatalogItem]) -> None:
        self._items = {item.catalog_id: item for item in items}

    def list_items(self) -> list[CatalogItem]:
        return list(self._items.values())

    def get(self, catalog_id: str) -> CatalogItem:
        try:
            return self._items[catalog_id]
        except KeyError as exc:
            raise KeyError(f"unknown catalog item: {catalog_id}") from exc


class SQLiteInstallationJobStore:
    """以独立 SQLite 表持久化任务状态，跨 AgentOS 重启可查询。"""

    def __init__(self, db_path: str | Path) -> None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = configure_sqlite_connection(
            sqlite3.connect(path, check_same_thread=False, timeout=30.0)
        )
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS marketplace_installations (
                job_id TEXT PRIMARY KEY,
                owner_scope TEXT NOT NULL,
                created_at TEXT NOT NULL,
                job_json TEXT NOT NULL
            )"""
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_marketplace_installations_owner "
            "ON marketplace_installations(owner_scope, created_at DESC)"
        )
        self._connection.commit()
        self._lock = RLock()

    @staticmethod
    def _parse(value: str) -> InstallationJob:
        return InstallationJob.model_validate_json(value)

    @staticmethod
    def _serialize(job: InstallationJob) -> str:
        return job.model_dump_json(by_alias=True)

    def create(self, job: InstallationJob) -> InstallationJob:
        with self._lock:
            self._connection.execute(
                "INSERT INTO marketplace_installations(job_id, owner_scope, created_at, job_json) VALUES (?, ?, ?, ?)",
                (job.job_id, job.owner_scope, job.created_at.isoformat(), self._serialize(job)),
            )
            self._connection.commit()
            return job.model_copy(deep=True)

    def get(self, job_id: str) -> InstallationJob:
        with self._lock:
            row = self._connection.execute(
                "SELECT job_json FROM marketplace_installations WHERE job_id = ?", (job_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown installation job: {job_id}")
        return self._parse(str(row[0]))

    def update(self, job: InstallationJob) -> InstallationJob:
        with self._lock:
            cursor = self._connection.execute(
                "UPDATE marketplace_installations SET job_json = ? WHERE job_id = ? AND owner_scope = ?",
                (self._serialize(job), job.job_id, job.owner_scope),
            )
            if cursor.rowcount != 1:
                self._connection.rollback()
                raise KeyError(f"unknown installation job: {job.job_id}")
            self._connection.commit()
            return job.model_copy(deep=True)

    def list(self, owner_scope: str) -> list[InstallationJob]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT job_json FROM marketplace_installations WHERE owner_scope = ? ORDER BY created_at DESC",
                (owner_scope,),
            ).fetchall()
        return [self._parse(str(row[0])) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._connection.close()


class InMemoryInstallationJobs:
    """线程安全的任务仓储，仅用于测试。"""

    def __init__(self) -> None:
        self._jobs: dict[str, InstallationJob] = {}
        self._lock = RLock()

    def create(self, job: InstallationJob) -> InstallationJob:
        with self._lock:
            if job.job_id in self._jobs:
                raise ValueError(f"installation job already exists: {job.job_id}")
            self._jobs[job.job_id] = job.model_copy(deep=True)
            return job.model_copy(deep=True)

    def get(self, job_id: str) -> InstallationJob:
        with self._lock:
            try:
                return self._jobs[job_id].model_copy(deep=True)
            except KeyError as exc:
                raise KeyError(f"unknown installation job: {job_id}") from exc

    def update(self, job: InstallationJob) -> InstallationJob:
        with self._lock:
            if job.job_id not in self._jobs:
                raise KeyError(f"unknown installation job: {job.job_id}")
            self._jobs[job.job_id] = job.model_copy(deep=True)
            return job.model_copy(deep=True)

    def list(self, owner_scope: str) -> list[InstallationJob]:
        with self._lock:
            return [job.model_copy(deep=True) for job in self._jobs.values() if job.owner_scope == owner_scope]


def validate_package(package_root: Path, item: CatalogItem) -> Path:
    """解析目录内包路径并校验真实文件内容摘要。"""
    root = package_root.resolve()
    package = (root / item.package_path).resolve()
    if root not in package.parents or not package.is_file():
        raise ValueError("catalog package is missing or escapes platform root")
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    if digest.lower() != item.sha256.lower():
        raise ValueError("catalog package checksum mismatch")
    return package


__all__ = [
    "InMemoryCatalog", "InMemoryInstallationJobs", "SQLiteInstallationJobStore", "validate_package",
]
