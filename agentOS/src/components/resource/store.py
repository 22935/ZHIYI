"""资源画像和快照的进程内存存储实现。"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Protocol

from contracts.resource import ResourceHealthStatus, ResourceProfile, ResourceSnapshot

from .models import VersionedResourceSnapshot


class VersionConflict(ValueError):
    """调用方基于过期快照版本提交更新时抛出的乐观锁冲突。"""


class StaleResourceObservation(ValueError):
    """资源节点上报的观测序号早于当前权威快照。"""


@dataclass(frozen=True)
class ResourceCredentialRecord:
    """只包含服务端可持久化的资源凭据元数据和哈希。"""

    resource_id: str
    credential_id: str
    owner_scope: str
    secret_digest: str
    encrypted_secret: str
    created_at: datetime


class ResourceStore(Protocol):
    """资源服务依赖的最小存储边界，便于替换存储介质。

    实现必须返回调用方不可变更内部状态的投影；若支持并发，版本读取、校验和写入
    必须具有原子语义，未知资源和版本冲突不得被静默吞掉。
    """

    def register(self, profile: ResourceProfile, snapshot: ResourceSnapshot) -> VersionedResourceSnapshot:
        """登记匹配画像与首份快照并返回版本投影；重复或标识不一致时抛出 ``ValueError``。"""
        ...

    def get_profile(self, resource_id: str) -> ResourceProfile:
        """读取资源画像副本；未知标识应抛出 ``KeyError``。"""
        ...

    def get_snapshot(self, resource_id: str) -> VersionedResourceSnapshot:
        """读取当前版本快照副本；未知标识应抛出 ``KeyError``。"""
        ...

    def list_profiles(self) -> list[ResourceProfile]:
        """返回稳定顺序的画像副本列表，不暴露实现内部容器。"""
        ...

    def update_snapshot(
        self, snapshot: ResourceSnapshot, *, expected_version: int | None = None
    ) -> VersionedResourceSnapshot:
        """按可选期望版本原子更新快照；过期版本应抛出 ``VersionConflict``。"""
        ...

    def update_capacity(
        self, resource_id: str, capacity: int, *, expected_capacity: int
    ) -> VersionedResourceSnapshot:
        """CAS 更新同一资源的静态容量并同步可用槽位。"""
        ...

    def register_remote(
        self,
        profile: ResourceProfile,
        snapshot: ResourceSnapshot,
        credential: ResourceCredentialRecord,
    ) -> VersionedResourceSnapshot:
        """Atomically write a remote resource and its initial credential."""
        ...

    def save_credential(self, record: ResourceCredentialRecord) -> None:
        """保存一个资源凭据；同一资源不可静默覆盖已有凭据。"""
        ...

    def rotate_credential(self, record: ResourceCredentialRecord) -> None:
        """原子替换已有资源凭据；资源画像和快照不得被修改。"""
        ...

    def get_credential(self, resource_id: str) -> ResourceCredentialRecord:
        """读取资源凭据元数据；未登记凭据应抛出 ``KeyError``。"""
        ...

    def consume_nonce(
        self,
        resource_id: str,
        nonce: str,
        expires_at: datetime,
        *,
        now: datetime,
    ) -> bool:
        """原子登记 nonce；已使用或已过期返回 False。"""
        ...


class InMemoryResourceStore:
    """面向单进程运行的资源存储。

    每次写快照均创建新投影并增加版本，以使调用方能检测到陈旧观测。
    对外返回深拷贝，防止调用方修改 Pydantic 模型后绕过版本控制。
    """

    def __init__(self) -> None:
        self._profiles: dict[str, ResourceProfile] = {}
        self._snapshots: dict[str, VersionedResourceSnapshot] = {}
        self._credentials: dict[str, ResourceCredentialRecord] = {}
        self._nonces: dict[tuple[str, str], datetime] = {}
        # 注册和快照更新共享同一把可重入锁，保证版本读取、校验、写入不可穿插。
        self._lock = RLock()

    def register(self, profile: ResourceProfile, snapshot: ResourceSnapshot) -> VersionedResourceSnapshot:
        """原子登记相互匹配的静态画像和第一份动态快照。"""
        if profile.resource_id != snapshot.resource_id:
            raise ValueError("profile and snapshot resource_id must match")
        with self._lock:
            if profile.resource_id in self._profiles:
                current_profile = self._profiles[profile.resource_id]
                current_snapshot = self._snapshots[profile.resource_id]
                if current_profile == profile and current_snapshot.snapshot == snapshot:
                    return self._copy_versioned(current_snapshot)
                raise ValueError(f"resource already registered: {profile.resource_id}")
            resource_id = profile.resource_id
            self._profiles[resource_id] = profile.model_copy(deep=True)
            versioned = VersionedResourceSnapshot(snapshot=snapshot.model_copy(deep=True), version=1)
            self._snapshots[resource_id] = versioned
            return self._copy_versioned(versioned)

    def get_profile(self, resource_id: str) -> ResourceProfile:
        """读取资源画像；未知资源被明确视为调用错误。"""
        try:
            return self._profiles[resource_id].model_copy(deep=True)
        except KeyError as error:
            raise KeyError(f"unknown resource: {resource_id}") from error

    def register_remote(
        self,
        profile: ResourceProfile,
        snapshot: ResourceSnapshot,
        credential: ResourceCredentialRecord,
    ) -> VersionedResourceSnapshot:
        if profile.resource_id != snapshot.resource_id or profile.resource_id != credential.resource_id:
            raise ValueError("remote registration resource_id values must match")
        with self._lock:
            if profile.resource_id in self._profiles:
                raise ValueError(f"resource already registered: {profile.resource_id}")
            if any(item.credential_id == credential.credential_id for item in self._credentials.values()):
                raise ValueError(f"resource credential already exists: {credential.credential_id}")
            versioned = VersionedResourceSnapshot(
                snapshot=snapshot.model_copy(deep=True), version=1
            )
            self._profiles[profile.resource_id] = profile.model_copy(deep=True)
            self._snapshots[profile.resource_id] = versioned
            self._credentials[profile.resource_id] = credential
            return self._copy_versioned(versioned)

    def get_snapshot(self, resource_id: str) -> VersionedResourceSnapshot:
        """读取当前最新版快照及其版本号。"""
        try:
            return self._copy_versioned(self._snapshots[resource_id])
        except KeyError as error:
            raise KeyError(f"unknown resource: {resource_id}") from error

    def list_profiles(self) -> list[ResourceProfile]:
        """按注册顺序返回画像副本，保证相同输入下结果稳定。"""
        return [self._profiles[key].model_copy(deep=True) for key in sorted(self._profiles)]

    def update_snapshot(
        self, snapshot: ResourceSnapshot, *, expected_version: int | None = None
    ) -> VersionedResourceSnapshot:
        """在单一临界区内校验版本并写入，避免并发更新同时通过校验。"""
        with self._lock:
            try:
                current = self._snapshots[snapshot.resource_id]
            except KeyError as error:
                raise KeyError(f"unknown resource: {snapshot.resource_id}") from error
            if expected_version is not None and expected_version != current.version:
                raise VersionConflict(
                    f"snapshot version conflict for {snapshot.resource_id}: "
                    f"expected {expected_version}, current {current.version}"
                )
            if snapshot.observation_sequence < current.snapshot.observation_sequence:
                raise StaleResourceObservation(
                    f"stale observation for {snapshot.resource_id}: "
                    f"received {snapshot.observation_sequence}, "
                    f"current {current.snapshot.observation_sequence}"
                )
            # 版本派生和字典写回也在锁内，令一次更新成为不可分割的状态转换。
            versioned = VersionedResourceSnapshot(
                snapshot=snapshot.model_copy(deep=True), version=current.version + 1
            )
            self._snapshots[snapshot.resource_id] = versioned
            return self._copy_versioned(versioned)

    def update_capacity(
        self, resource_id: str, capacity: int, *, expected_capacity: int
    ) -> VersionedResourceSnapshot:
        if capacity < 1:
            raise ValueError("resource capacity must be positive")
        with self._lock:
            try:
                profile = self._profiles[resource_id]
                current = self._snapshots[resource_id]
            except KeyError as error:
                raise KeyError(f"unknown resource: {resource_id}") from error
            if profile.capacity != expected_capacity:
                raise VersionConflict(
                    f"capacity conflict for {resource_id}: "
                    f"expected {expected_capacity}, current {profile.capacity}"
                )
            allocated = max(0, profile.capacity - current.snapshot.available_slots)
            snapshot = current.snapshot.model_copy(update={
                "available_slots": max(0, capacity - allocated),
                "utilization": min(1.0, allocated / capacity),
            })
            versioned = VersionedResourceSnapshot(
                snapshot=snapshot,
                version=current.version + 1,
            )
            self._profiles[resource_id] = profile.model_copy(update={"capacity": capacity})
            self._snapshots[resource_id] = versioned
            return self._copy_versioned(versioned)

    def save_credential(self, record: ResourceCredentialRecord) -> None:
        with self._lock:
            if record.resource_id not in self._profiles:
                raise KeyError(f"unknown resource: {record.resource_id}")
            if record.resource_id in self._credentials:
                raise ValueError(f"resource credential already exists: {record.resource_id}")
            self._credentials[record.resource_id] = record

    def rotate_credential(self, record: ResourceCredentialRecord) -> None:
        with self._lock:
            if record.resource_id not in self._profiles:
                raise KeyError(f"unknown resource: {record.resource_id}")
            if record.resource_id not in self._credentials:
                raise KeyError(f"resource credential not found: {record.resource_id}")
            self._credentials[record.resource_id] = record

    def get_credential(self, resource_id: str) -> ResourceCredentialRecord:
        with self._lock:
            try:
                return self._credentials[resource_id]
            except KeyError as error:
                raise KeyError(f"resource credential not found: {resource_id}") from error

    def consume_nonce(
        self,
        resource_id: str,
        nonce: str,
        expires_at: datetime,
        *,
        now: datetime,
    ) -> bool:
        with self._lock:
            self._nonces = {
                key: expiry for key, expiry in self._nonces.items() if expiry > now
            }
            key = (resource_id, nonce)
            if expires_at <= now or key in self._nonces:
                return False
            self._nonces[key] = expires_at
            return True

    @staticmethod
    def _copy_versioned(value: VersionedResourceSnapshot) -> VersionedResourceSnapshot:
        return VersionedResourceSnapshot(snapshot=value.snapshot.model_copy(deep=True), version=value.version)


class SQLiteResourceStore:
    """SQLite resource truth preserving profiles and safe restart snapshots."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS resources (
                resource_id TEXT PRIMARY KEY,
                profile_json TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,
                version INTEGER NOT NULL CHECK(version >= 1)
            )"""
        )
        credential_table = self._connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'resource_credentials'"
        ).fetchone()
        if credential_table is not None:
            columns = {
                str(row[1])
                for row in self._connection.execute("PRAGMA table_info(resource_credentials)").fetchall()
            }
            if "secret_hash" in columns or not {"secret_digest", "encrypted_secret"} <= columns:
                self._connection.close()
                raise RuntimeError(
                    "legacy resource credential schema requires explicit credential migration"
                )
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS resource_credentials (
                resource_id TEXT PRIMARY KEY,
                credential_id TEXT NOT NULL UNIQUE,
                owner_scope TEXT NOT NULL,
                secret_digest TEXT NOT NULL,
                encrypted_secret TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS resource_auth_nonces (
                resource_id TEXT NOT NULL,
                nonce TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                PRIMARY KEY(resource_id, nonce)
            )"""
        )
        for resource_id, payload in self._connection.execute(
            "SELECT resource_id, snapshot_json FROM resources"
        ).fetchall():
            snapshot = ResourceSnapshot.model_validate(json.loads(str(payload)))
            if snapshot.health_status is not ResourceHealthStatus.UNKNOWN:
                safe = snapshot.model_copy(update={"health_status": ResourceHealthStatus.UNKNOWN})
                self._connection.execute(
                    "UPDATE resources SET snapshot_json = ? WHERE resource_id = ?",
                    (self._json(safe), str(resource_id)),
                )
        self._connection.commit()
        self._lock = RLock()

    @staticmethod
    def _json(model: ResourceProfile | ResourceSnapshot) -> str:
        return json.dumps(
            model.model_dump(by_alias=True, mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _snapshot(row: tuple[object, object]) -> VersionedResourceSnapshot:
        persisted = ResourceSnapshot.model_validate(json.loads(str(row[0])))
        return VersionedResourceSnapshot(snapshot=persisted, version=int(row[1]))

    def register(self, profile: ResourceProfile, snapshot: ResourceSnapshot) -> VersionedResourceSnapshot:
        if profile.resource_id != snapshot.resource_id:
            raise ValueError("profile and snapshot resource_id must match")
        with self._lock:
            row = self._connection.execute(
                "SELECT profile_json, snapshot_json, version FROM resources WHERE resource_id = ?",
                (profile.resource_id,),
            ).fetchone()
            if row is not None:
                existing_profile = ResourceProfile.model_validate(json.loads(str(row[0])))
                existing_snapshot = ResourceSnapshot.model_validate(json.loads(str(row[1])))
                if existing_profile == profile and existing_snapshot == snapshot:
                    return self._snapshot((row[1], row[2]))
                raise ValueError(f"resource already registered: {profile.resource_id}")
            self._connection.execute(
                "INSERT INTO resources(resource_id, profile_json, snapshot_json, version) VALUES (?, ?, ?, 1)",
                (profile.resource_id, self._json(profile), self._json(snapshot)),
            )
            self._connection.commit()
            return VersionedResourceSnapshot(snapshot=snapshot.model_copy(deep=True), version=1)

    def get_profile(self, resource_id: str) -> ResourceProfile:
        row = self._connection.execute(
            "SELECT profile_json FROM resources WHERE resource_id = ?", (resource_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown resource: {resource_id}")
        return ResourceProfile.model_validate(json.loads(str(row[0])))

    def register_remote(
        self,
        profile: ResourceProfile,
        snapshot: ResourceSnapshot,
        credential: ResourceCredentialRecord,
    ) -> VersionedResourceSnapshot:
        if profile.resource_id != snapshot.resource_id or profile.resource_id != credential.resource_id:
            raise ValueError("remote registration resource_id values must match")
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                resource = self._connection.execute(
                    "SELECT profile_json, snapshot_json, version FROM resources WHERE resource_id = ?",
                    (profile.resource_id,),
                ).fetchone()
                if resource is not None:
                    raise ValueError(f"resource already registered: {profile.resource_id}")
                duplicate = self._connection.execute(
                    "SELECT 1 FROM resource_credentials WHERE credential_id = ?",
                    (credential.credential_id,),
                ).fetchone()
                if duplicate is not None:
                    raise ValueError(f"resource credential already exists: {credential.credential_id}")
                self._connection.execute(
                    "INSERT INTO resources(resource_id, profile_json, snapshot_json, version) VALUES (?, ?, ?, 1)",
                    (profile.resource_id, self._json(profile), self._json(snapshot)),
                )
                self._connection.execute(
                    "INSERT INTO resource_credentials(resource_id, credential_id, owner_scope, secret_digest, encrypted_secret, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        credential.resource_id,
                        credential.credential_id,
                        credential.owner_scope,
                        credential.secret_digest,
                        credential.encrypted_secret,
                        credential.created_at.astimezone(timezone.utc).isoformat(),
                    ),
                )
                self._connection.commit()
                return VersionedResourceSnapshot(
                    snapshot=snapshot.model_copy(deep=True), version=1
                )
            except sqlite3.IntegrityError as error:
                self._connection.rollback()
                raise ValueError("remote registration violates a storage constraint") from error
            except Exception:
                self._connection.rollback()
                raise

    def get_snapshot(self, resource_id: str) -> VersionedResourceSnapshot:
        row = self._connection.execute(
            "SELECT snapshot_json, version FROM resources WHERE resource_id = ?", (resource_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown resource: {resource_id}")
        return self._snapshot(row)

    def list_profiles(self) -> list[ResourceProfile]:
        rows = self._connection.execute(
            "SELECT profile_json FROM resources ORDER BY resource_id"
        ).fetchall()
        return [ResourceProfile.model_validate(json.loads(str(row[0]))) for row in rows]

    def update_snapshot(
        self, snapshot: ResourceSnapshot, *, expected_version: int | None = None
    ) -> VersionedResourceSnapshot:
        with self._lock:
            row = self._connection.execute(
                "SELECT snapshot_json, version FROM resources WHERE resource_id = ?",
                (snapshot.resource_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown resource: {snapshot.resource_id}")
            current_snapshot = ResourceSnapshot.model_validate(json.loads(str(row[0])))
            current_version = int(row[1])
            if expected_version is not None and expected_version != current_version:
                raise VersionConflict(
                    f"snapshot version conflict for {snapshot.resource_id}: "
                    f"expected {expected_version}, current {current_version}"
                )
            if snapshot.observation_sequence < current_snapshot.observation_sequence:
                raise StaleResourceObservation(
                    f"stale observation for {snapshot.resource_id}: "
                    f"received {snapshot.observation_sequence}, "
                    f"current {current_snapshot.observation_sequence}"
                )
            next_version = current_version + 1
            cursor = self._connection.execute(
                "UPDATE resources SET snapshot_json = ?, version = ? "
                "WHERE resource_id = ? AND version = ?",
                (self._json(snapshot), next_version, snapshot.resource_id, current_version),
            )
            if cursor.rowcount != 1:
                self._connection.rollback()
                raise VersionConflict(f"snapshot version conflict for {snapshot.resource_id}")
            self._connection.commit()
            return VersionedResourceSnapshot(snapshot=snapshot.model_copy(deep=True), version=next_version)

    def update_capacity(
        self, resource_id: str, capacity: int, *, expected_capacity: int
    ) -> VersionedResourceSnapshot:
        if capacity < 1:
            raise ValueError("resource capacity must be positive")
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                row = self._connection.execute(
                    "SELECT profile_json, snapshot_json, version FROM resources WHERE resource_id = ?",
                    (resource_id,),
                ).fetchone()
                if row is None:
                    raise KeyError(f"unknown resource: {resource_id}")
                profile = ResourceProfile.model_validate(json.loads(str(row[0])))
                snapshot = ResourceSnapshot.model_validate(json.loads(str(row[1])))
                version = int(row[2])
                if profile.capacity != expected_capacity:
                    raise VersionConflict(
                        f"capacity conflict for {resource_id}: "
                        f"expected {expected_capacity}, current {profile.capacity}"
                    )
                allocated = max(0, profile.capacity - snapshot.available_slots)
                updated_profile = profile.model_copy(update={"capacity": capacity})
                updated_snapshot = snapshot.model_copy(update={
                    "available_slots": max(0, capacity - allocated),
                    "utilization": min(1.0, allocated / capacity),
                })
                cursor = self._connection.execute(
                    "UPDATE resources SET profile_json = ?, snapshot_json = ?, version = ? "
                    "WHERE resource_id = ? AND version = ?",
                    (
                        self._json(updated_profile),
                        self._json(updated_snapshot),
                        version + 1,
                        resource_id,
                        version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise VersionConflict(f"capacity conflict for {resource_id}")
                self._connection.commit()
                return VersionedResourceSnapshot(
                    snapshot=updated_snapshot.model_copy(deep=True),
                    version=version + 1,
                )
            except Exception:
                self._connection.rollback()
                raise

    def save_credential(self, record: ResourceCredentialRecord) -> None:
        with self._lock:
            try:
                self._connection.execute(
                    "INSERT INTO resource_credentials(resource_id, credential_id, owner_scope, secret_digest, encrypted_secret, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        record.resource_id,
                        record.credential_id,
                        record.owner_scope,
                        record.secret_digest,
                        record.encrypted_secret,
                        record.created_at.astimezone(timezone.utc).isoformat(),
                    ),
                )
                self._connection.commit()
            except sqlite3.IntegrityError as error:
                self._connection.rollback()
                raise ValueError(
                    f"resource credential already exists: {record.resource_id}"
                ) from error

    def rotate_credential(self, record: ResourceCredentialRecord) -> None:
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                resource = self._connection.execute(
                    "SELECT 1 FROM resources WHERE resource_id = ?",
                    (record.resource_id,),
                ).fetchone()
                if resource is None:
                    raise KeyError(f"unknown resource: {record.resource_id}")
                cursor = self._connection.execute(
                    "UPDATE resource_credentials SET credential_id = ?, owner_scope = ?, "
                    "secret_digest = ?, encrypted_secret = ?, created_at = ? "
                    "WHERE resource_id = ?",
                    (
                        record.credential_id,
                        record.owner_scope,
                        record.secret_digest,
                        record.encrypted_secret,
                        record.created_at.astimezone(timezone.utc).isoformat(),
                        record.resource_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise KeyError(f"resource credential not found: {record.resource_id}")
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

    def get_credential(self, resource_id: str) -> ResourceCredentialRecord:
        row = self._connection.execute(
            "SELECT credential_id, owner_scope, secret_digest, encrypted_secret, created_at "
            "FROM resource_credentials WHERE resource_id = ?",
            (resource_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"resource credential not found: {resource_id}")
        return ResourceCredentialRecord(
            resource_id=resource_id,
            credential_id=str(row[0]),
            owner_scope=str(row[1]),
            secret_digest=str(row[2]),
            encrypted_secret=str(row[3]),
            created_at=datetime.fromisoformat(str(row[4])).astimezone(timezone.utc),
        )

    def consume_nonce(
        self,
        resource_id: str,
        nonce: str,
        expires_at: datetime,
        *,
        now: datetime,
    ) -> bool:
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                self._connection.execute(
                    "DELETE FROM resource_auth_nonces WHERE expires_at <= ?",
                    (now.astimezone(timezone.utc).isoformat(),),
                )
                if expires_at <= now:
                    self._connection.commit()
                    return False
                self._connection.execute(
                    "INSERT INTO resource_auth_nonces(resource_id, nonce, expires_at) VALUES (?, ?, ?)",
                    (
                        resource_id,
                        nonce,
                        expires_at.astimezone(timezone.utc).isoformat(),
                    ),
                )
                self._connection.commit()
                return True
            except sqlite3.IntegrityError:
                self._connection.rollback()
                return False
            except Exception:
                self._connection.rollback()
                raise

    def close(self) -> None:
        self._connection.close()
