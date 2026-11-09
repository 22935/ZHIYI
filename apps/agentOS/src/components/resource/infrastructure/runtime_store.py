"""资源平面存储：Runtime 画像/快照、模型端点目录与远程凭据。

静态画像、动态观测、签名凭据和重放 nonce 分离保存。内存实现用于测试和
嵌入式运行，SQLite 实现使用事务与版本号维护跨进程一致性。
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from threading import RLock

from contracts.resource import (
    HealthStatus,
    ModelEndpointProfile,
    RuntimeProfile,
    RuntimeSnapshot,
)

from ..domain.models import VersionedRuntimeSnapshot
from ..domain.credentials import ResourceCredentialRecord
from .sqlite.connection import configure_sqlite_connection


class VersionConflict(RuntimeError):
    """乐观并发控制检测到版本竞争。"""


class StaleResourceObservation(RuntimeError):
    """观测序号低于当前已记录序号。"""


class InMemoryResourceStore:
    """进程内存实现；测试与嵌入式场景的默认存储。"""

    def __init__(self) -> None:
        self._profiles: dict[str, RuntimeProfile] = {}
        self._snapshots: dict[str, VersionedRuntimeSnapshot] = {}
        self._model_endpoints: dict[str, ModelEndpointProfile] = {}
        self._credentials: dict[str, ResourceCredentialRecord] = {}
        self._nonces: dict[tuple[str, str], datetime] = {}
        self._lock = RLock()

    def register(self, profile: RuntimeProfile, snapshot: RuntimeSnapshot) -> VersionedRuntimeSnapshot:
        if profile.runtime_id != snapshot.runtime_id:
            raise ValueError("profile and snapshot runtime_id must match")
        with self._lock:
            if profile.runtime_id in self._profiles:
                raise ValueError(f"runtime already registered: {profile.runtime_id}")
            # 写入和返回均复制，避免调用方持有内部 RuntimeSnapshot 引用。
            versioned = VersionedRuntimeSnapshot(snapshot=snapshot.model_copy(deep=True), version=1)
            self._profiles[profile.runtime_id] = profile.model_copy(deep=True)
            self._snapshots[profile.runtime_id] = versioned
            return self._copy_versioned(versioned)

    def register_remote(
        self,
        profile: RuntimeProfile,
        snapshot: RuntimeSnapshot,
        credential: ResourceCredentialRecord,
    ) -> VersionedRuntimeSnapshot:
        if profile.runtime_id != snapshot.runtime_id or profile.runtime_id != credential.resource_id:
            raise ValueError("remote registration runtime_id values must match")
        with self._lock:
            if profile.runtime_id in self._profiles:
                raise ValueError(f"runtime already registered: {profile.runtime_id}")
            if any(
                item.credential_id == credential.credential_id
                for item in self._credentials.values()
            ):
                raise ValueError(f"runtime credential already exists: {credential.credential_id}")
            versioned = VersionedRuntimeSnapshot(snapshot=snapshot.model_copy(deep=True), version=1)
            self._profiles[profile.runtime_id] = profile.model_copy(deep=True)
            self._snapshots[profile.runtime_id] = versioned
            self._credentials[profile.runtime_id] = credential
            return self._copy_versioned(versioned)

    def get_profile(self, runtime_id: str) -> RuntimeProfile:
        try:
            return self._profiles[runtime_id].model_copy(deep=True)
        except KeyError as error:
            raise KeyError(f"unknown runtime: {runtime_id}") from error

    def get_snapshot(self, runtime_id: str) -> VersionedRuntimeSnapshot:
        try:
            return self._copy_versioned(self._snapshots[runtime_id])
        except KeyError as error:
            raise KeyError(f"unknown runtime: {runtime_id}") from error

    def list_profiles(self) -> list[RuntimeProfile]:
        return [self._profiles[key].model_copy(deep=True) for key in sorted(self._profiles)]

    def update_snapshot(
        self, snapshot: RuntimeSnapshot, *, expected_version: int | None = None
    ) -> VersionedRuntimeSnapshot:
        with self._lock:
            try:
                current = self._snapshots[snapshot.runtime_id]
            except KeyError as error:
                raise KeyError(f"unknown runtime: {snapshot.runtime_id}") from error
            if expected_version is not None and expected_version != current.version:
                raise VersionConflict(
                    f"snapshot version conflict for {snapshot.runtime_id}: "
                    f"expected {expected_version}, current {current.version}"
                )
            if snapshot.observation_sequence < current.snapshot.observation_sequence:
                raise StaleResourceObservation(
                    f"stale observation for {snapshot.runtime_id}: "
                    f"received {snapshot.observation_sequence}, "
                    f"current {current.snapshot.observation_sequence}"
                )
            versioned = VersionedRuntimeSnapshot(
                snapshot=snapshot.model_copy(deep=True), version=current.version + 1
            )
            self._snapshots[snapshot.runtime_id] = versioned
            return self._copy_versioned(versioned)

    def update_capacity(
        self, runtime_id: str, capacity: int, *, expected_capacity: int
    ) -> VersionedRuntimeSnapshot:
        if capacity < 1:
            raise ValueError("runtime capacity must be positive")
        with self._lock:
            profile = self._profiles.get(runtime_id)
            if profile is None:
                raise KeyError(f"unknown runtime: {runtime_id}")
            current = self._snapshots[runtime_id]
            if profile.capacity != expected_capacity:
                raise VersionConflict(
                    f"capacity conflict for {runtime_id}: "
                    f"expected {expected_capacity}, current {profile.capacity}"
                )
            allocated = max(0, profile.capacity - current.snapshot.available_slots)
            updated_profile = profile.model_copy(update={"capacity": capacity})
            updated_snapshot = current.snapshot.model_copy(update={
                "available_slots": max(0, capacity - allocated),
                "utilization": min(1.0, allocated / capacity),
            })
            self._profiles[runtime_id] = updated_profile
            versioned = VersionedRuntimeSnapshot(
                snapshot=updated_snapshot, version=current.version + 1
            )
            self._snapshots[runtime_id] = versioned
            return self._copy_versioned(versioned)

    def update_profile(self, profile: RuntimeProfile) -> RuntimeProfile:
        with self._lock:
            try:
                current = self._profiles[profile.runtime_id]
            except KeyError as error:
                raise KeyError(f"unknown runtime: {profile.runtime_id}") from error
            if profile.runtime_id != current.runtime_id:
                raise ValueError("runtime profile identity is immutable")
            self._profiles[profile.runtime_id] = profile.model_copy(deep=True)
            return profile.model_copy(deep=True)

    def upsert_model_endpoint(self, endpoint: ModelEndpointProfile) -> tuple[ModelEndpointProfile, bool]:
        with self._lock:
            existing = self._model_endpoints.get(endpoint.endpoint_id)
            if existing is not None and existing == endpoint:
                return existing.model_copy(deep=True), False
            updated = endpoint if existing is None else endpoint.model_copy(
                update={"version": existing.version + 1}
            )
            self._model_endpoints[endpoint.endpoint_id] = updated.model_copy(deep=True)
            return updated.model_copy(deep=True), True

    def get_model_endpoint(self, endpoint_id: str) -> ModelEndpointProfile:
        try:
            return self._model_endpoints[endpoint_id].model_copy(deep=True)
        except KeyError as error:
            raise KeyError(f"unknown model endpoint: {endpoint_id}") from error

    def list_model_endpoints(self) -> list[ModelEndpointProfile]:
        return [
            self._model_endpoints[key].model_copy(deep=True)
            for key in sorted(self._model_endpoints)
        ]

    def delete_model_endpoint(self, endpoint_id: str) -> None:
        with self._lock:
            if self._model_endpoints.pop(endpoint_id, None) is None:
                raise KeyError(f"unknown model endpoint: {endpoint_id}")

    def save_credential(self, record: ResourceCredentialRecord) -> None:
        with self._lock:
            if record.resource_id not in self._profiles:
                raise KeyError(f"unknown runtime: {record.resource_id}")
            if record.resource_id in self._credentials:
                raise ValueError(f"runtime credential already exists: {record.resource_id}")
            self._credentials[record.resource_id] = record

    def rotate_credential(self, record: ResourceCredentialRecord) -> None:
        with self._lock:
            if record.resource_id not in self._profiles:
                raise KeyError(f"unknown runtime: {record.resource_id}")
            if record.resource_id not in self._credentials:
                raise KeyError(f"runtime credential not found: {record.resource_id}")
            self._credentials[record.resource_id] = record

    def get_credential(self, runtime_id: str) -> ResourceCredentialRecord:
        with self._lock:
            try:
                return self._credentials[runtime_id]
            except KeyError as error:
                raise KeyError(f"runtime credential not found: {runtime_id}") from error

    def consume_nonce(
        self,
        runtime_id: str,
        nonce: str,
        expires_at: datetime,
        *,
        now: datetime,
    ) -> bool:
        with self._lock:
            # 清理过期 nonce 后再检查唯一性，控制常驻进程的重放记录规模。
            self._nonces = {
                key: expiry for key, expiry in self._nonces.items() if expiry > now
            }
            key = (runtime_id, nonce)
            if expires_at <= now or key in self._nonces:
                return False
            self._nonces[key] = expires_at
            return True

    @staticmethod
    def _copy_versioned(value: VersionedRuntimeSnapshot) -> VersionedRuntimeSnapshot:
        return VersionedRuntimeSnapshot(
            snapshot=value.snapshot.model_copy(deep=True), version=value.version
        )


class SQLiteResourceStore:
    """SQLite 资源平面真值：Runtime 画像/快照、模型端点与远程凭据。

    表名与旧平铺资源表分离（``plane_runtimes`` / ``plane_model_endpoints``）；
    启动时把旧表或历史版本中无法按当前合同解析的行清理掉——资源模块由
    启动引导负责再注册，不留跨版本迁移包袱。持久化快照的健康态统一重置
    为 UNKNOWN，延续"重启后必须重新证明健康"的安全语义。
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = configure_sqlite_connection(
            sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
        )
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS plane_runtimes (
                runtime_id TEXT PRIMARY KEY,
                profile_json TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,
                version INTEGER NOT NULL CHECK(version >= 1)
            )"""
        )
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS plane_model_endpoints (
                endpoint_id TEXT PRIMARY KEY,
                profile_json TEXT NOT NULL,
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
        dropped = self._drop_unparsable_rows("plane_runtimes", RuntimeProfile)
        dropped += self._drop_unparsable_rows("plane_model_endpoints", ModelEndpointProfile)
        if self._table_exists("resources"):
            # 旧平铺资源表不再被读取；凭据在独立的 resource_credentials 表中保留。
            self._connection.execute("DROP TABLE IF EXISTS resources")
            dropped += 1
        for runtime_id, payload in self._connection.execute(
            "SELECT runtime_id, snapshot_json FROM plane_runtimes"
        ).fetchall():
            snapshot = RuntimeSnapshot.model_validate(json.loads(str(payload)))
            if snapshot.health_status is not HealthStatus.UNKNOWN:
                safe = snapshot.model_copy(update={"health_status": HealthStatus.UNKNOWN})
                self._connection.execute(
                    "UPDATE plane_runtimes SET snapshot_json = ? WHERE runtime_id = ?",
                    (self._json(safe), str(runtime_id)),
                )
        if dropped:
            # 自愈清理是升级路径的一部分：旧平铺资源行由引导流程重新注册。
            self._connection.execute("DELETE FROM resources") if self._table_exists("resources") else None
        self._connection.commit()
        self._lock = RLock()

    def _table_exists(self, name: str) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
        ).fetchone()
        return row is not None

    def _drop_unparsable_rows(self, table: str, model) -> int:
        rows = self._connection.execute(
            f"SELECT rowid, profile_json FROM {table}"
        ).fetchall()
        dropped = 0
        for rowid, payload in rows:
            try:
                model.model_validate(json.loads(str(payload)))
            except Exception:
                self._connection.execute(f"DELETE FROM {table} WHERE rowid = ?", (rowid,))
                dropped += 1
        return dropped

    @staticmethod
    def _json(model) -> str:
        return json.dumps(
            model.model_dump(by_alias=True, mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _snapshot(row: tuple[object, object]) -> VersionedRuntimeSnapshot:
        return VersionedRuntimeSnapshot(
            snapshot=RuntimeSnapshot.model_validate(json.loads(str(row[0]))),
            version=int(row[1]),  # type: ignore[arg-type]
        )

    def register(self, profile: RuntimeProfile, snapshot: RuntimeSnapshot) -> VersionedRuntimeSnapshot:
        if profile.runtime_id != snapshot.runtime_id:
            raise ValueError("profile and snapshot runtime_id must match")
        with self._lock:
            row = self._connection.execute(
                "SELECT profile_json, snapshot_json, version FROM plane_runtimes WHERE runtime_id = ?",
                (profile.runtime_id,),
            ).fetchone()
            if row is not None:
                raise ValueError(f"runtime already registered: {profile.runtime_id}")
            self._connection.execute(
                "INSERT INTO plane_runtimes(runtime_id, profile_json, snapshot_json, version) VALUES (?, ?, ?, 1)",
                (profile.runtime_id, self._json(profile), self._json(snapshot)),
            )
            self._connection.commit()
            return VersionedRuntimeSnapshot(snapshot=snapshot.model_copy(deep=True), version=1)

    def get_profile(self, runtime_id: str) -> RuntimeProfile:
        row = self._connection.execute(
            "SELECT profile_json FROM plane_runtimes WHERE runtime_id = ?", (runtime_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown runtime: {runtime_id}")
        return RuntimeProfile.model_validate(json.loads(str(row[0])))

    def register_remote(
        self,
        profile: RuntimeProfile,
        snapshot: RuntimeSnapshot,
        credential: ResourceCredentialRecord,
    ) -> VersionedRuntimeSnapshot:
        if profile.runtime_id != snapshot.runtime_id or profile.runtime_id != credential.resource_id:
            raise ValueError("remote registration runtime_id values must match")
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                runtime = self._connection.execute(
                    "SELECT 1 FROM plane_runtimes WHERE runtime_id = ?",
                    (profile.runtime_id,),
                ).fetchone()
                if runtime is not None:
                    raise ValueError(f"runtime already registered: {profile.runtime_id}")
                duplicate = self._connection.execute(
                    "SELECT 1 FROM resource_credentials WHERE credential_id = ?",
                    (credential.credential_id,),
                ).fetchone()
                if duplicate is not None:
                    raise ValueError(f"runtime credential already exists: {credential.credential_id}")
                self._connection.execute(
                    "INSERT INTO plane_runtimes(runtime_id, profile_json, snapshot_json, version) VALUES (?, ?, ?, 1)",
                    (profile.runtime_id, self._json(profile), self._json(snapshot)),
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
                return VersionedRuntimeSnapshot(
                    snapshot=snapshot.model_copy(deep=True), version=1
                )
            except sqlite3.IntegrityError as error:
                self._connection.rollback()
                raise ValueError("remote registration violates a storage constraint") from error
            except Exception:
                self._connection.rollback()
                raise

    def get_snapshot(self, runtime_id: str) -> VersionedRuntimeSnapshot:
        row = self._connection.execute(
            "SELECT snapshot_json, version FROM plane_runtimes WHERE runtime_id = ?", (runtime_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown runtime: {runtime_id}")
        return self._snapshot(row)

    def list_profiles(self) -> list[RuntimeProfile]:
        rows = self._connection.execute(
            "SELECT profile_json FROM plane_runtimes ORDER BY runtime_id"
        ).fetchall()
        return [RuntimeProfile.model_validate(json.loads(str(row[0]))) for row in rows]

    def update_snapshot(
        self, snapshot: RuntimeSnapshot, *, expected_version: int | None = None
    ) -> VersionedRuntimeSnapshot:
        with self._lock:
            row = self._connection.execute(
                "SELECT snapshot_json, version FROM plane_runtimes WHERE runtime_id = ?",
                (snapshot.runtime_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown runtime: {snapshot.runtime_id}")
            current_snapshot = RuntimeSnapshot.model_validate(json.loads(str(row[0])))
            current_version = int(row[1])
            if expected_version is not None and expected_version != current_version:
                raise VersionConflict(
                    f"snapshot version conflict for {snapshot.runtime_id}: "
                    f"expected {expected_version}, current {current_version}"
                )
            # 存储层再次拦截迟到观测，防止绕过服务层的旧数据覆盖新状态。
            if snapshot.observation_sequence < current_snapshot.observation_sequence:
                raise StaleResourceObservation(
                    f"stale observation for {snapshot.runtime_id}: "
                    f"received {snapshot.observation_sequence}, "
                    f"current {current_snapshot.observation_sequence}"
                )
            next_version = current_version + 1
            cursor = self._connection.execute(
                "UPDATE plane_runtimes SET snapshot_json = ?, version = ? "
                "WHERE runtime_id = ? AND version = ?",
                (self._json(snapshot), next_version, snapshot.runtime_id, current_version),
            )
            if cursor.rowcount != 1:
                self._connection.rollback()
                raise VersionConflict(f"snapshot version conflict for {snapshot.runtime_id}")
            self._connection.commit()
            return VersionedRuntimeSnapshot(snapshot=snapshot.model_copy(deep=True), version=next_version)

    def update_capacity(
        self, runtime_id: str, capacity: int, *, expected_capacity: int
    ) -> VersionedRuntimeSnapshot:
        if capacity < 1:
            raise ValueError("runtime capacity must be positive")
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                row = self._connection.execute(
                    "SELECT profile_json, snapshot_json, version FROM plane_runtimes WHERE runtime_id = ?",
                    (runtime_id,),
                ).fetchone()
                if row is None:
                    raise KeyError(f"unknown runtime: {runtime_id}")
                profile = RuntimeProfile.model_validate(json.loads(str(row[0])))
                snapshot = RuntimeSnapshot.model_validate(json.loads(str(row[1])))
                version = int(row[2])
                if profile.capacity != expected_capacity:
                    raise VersionConflict(
                        f"capacity conflict for {runtime_id}: "
                        f"expected {expected_capacity}, current {profile.capacity}"
                    )
                allocated = max(0, profile.capacity - snapshot.available_slots)
                updated_profile = profile.model_copy(update={"capacity": capacity})
                updated_snapshot = snapshot.model_copy(update={
                    "available_slots": max(0, capacity - allocated),
                    "utilization": min(1.0, allocated / capacity),
                })
                cursor = self._connection.execute(
                    "UPDATE plane_runtimes SET profile_json = ?, snapshot_json = ?, version = ? "
                    "WHERE runtime_id = ? AND version = ?",
                    (
                        self._json(updated_profile),
                        self._json(updated_snapshot),
                        version + 1,
                        runtime_id,
                        version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise VersionConflict(f"capacity conflict for {runtime_id}")
                self._connection.commit()
                return VersionedRuntimeSnapshot(
                    snapshot=updated_snapshot.model_copy(deep=True),
                    version=version + 1,
                )
            except Exception:
                self._connection.rollback()
                raise

    def update_profile(self, profile: RuntimeProfile) -> RuntimeProfile:
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                row = self._connection.execute(
                    "SELECT profile_json FROM plane_runtimes WHERE runtime_id = ?",
                    (profile.runtime_id,),
                ).fetchone()
                if row is None:
                    raise KeyError(f"unknown runtime: {profile.runtime_id}")
                current = RuntimeProfile.model_validate(json.loads(str(row[0])))
                if profile.runtime_id != current.runtime_id:
                    raise ValueError("runtime profile identity is immutable")
                self._connection.execute(
                    "UPDATE plane_runtimes SET profile_json = ? WHERE runtime_id = ?",
                    (self._json(profile), profile.runtime_id),
                )
                self._connection.commit()
                return profile.model_copy(deep=True)
            except Exception:
                self._connection.rollback()
                raise

    def upsert_model_endpoint(self, endpoint: ModelEndpointProfile) -> tuple[ModelEndpointProfile, bool]:
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                row = self._connection.execute(
                    "SELECT profile_json, version FROM plane_model_endpoints WHERE endpoint_id = ?",
                    (endpoint.endpoint_id,),
                ).fetchone()
                if row is not None:
                    existing = ModelEndpointProfile.model_validate(json.loads(str(row[0])))
                    if existing == endpoint:
                        self._connection.commit()
                        return existing.model_copy(deep=True), False
                    updated = endpoint.model_copy(update={"version": int(row[1]) + 1})
                    self._connection.execute(
                        "UPDATE plane_model_endpoints SET profile_json = ?, version = ? WHERE endpoint_id = ?",
                        (self._json(updated), int(row[1]) + 1, endpoint.endpoint_id),
                    )
                else:
                    updated = endpoint
                    self._connection.execute(
                        "INSERT INTO plane_model_endpoints(endpoint_id, profile_json, version) VALUES (?, ?, 1)",
                        (endpoint.endpoint_id, self._json(endpoint)),
                    )
                self._connection.commit()
                return updated.model_copy(deep=True), True
            except Exception:
                self._connection.rollback()
                raise

    def get_model_endpoint(self, endpoint_id: str) -> ModelEndpointProfile:
        row = self._connection.execute(
            "SELECT profile_json FROM plane_model_endpoints WHERE endpoint_id = ?", (endpoint_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown model endpoint: {endpoint_id}")
        return ModelEndpointProfile.model_validate(json.loads(str(row[0])))

    def list_model_endpoints(self) -> list[ModelEndpointProfile]:
        rows = self._connection.execute(
            "SELECT profile_json FROM plane_model_endpoints ORDER BY endpoint_id"
        ).fetchall()
        return [ModelEndpointProfile.model_validate(json.loads(str(row[0]))) for row in rows]

    def delete_model_endpoint(self, endpoint_id: str) -> None:
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM plane_model_endpoints WHERE endpoint_id = ?", (endpoint_id,)
            )
            if cursor.rowcount != 1:
                self._connection.rollback()
                raise KeyError(f"unknown model endpoint: {endpoint_id}")
            self._connection.commit()

    def save_credential(self, record: ResourceCredentialRecord) -> None:
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                known = self._connection.execute(
                    "SELECT 1 FROM plane_runtimes WHERE runtime_id = ?", (record.resource_id,)
                ).fetchone()
                if known is None:
                    raise KeyError(f"unknown runtime: {record.resource_id}")
                duplicate = self._connection.execute(
                    "SELECT 1 FROM resource_credentials WHERE resource_id = ? OR credential_id = ?",
                    (record.resource_id, record.credential_id),
                ).fetchone()
                if duplicate is not None:
                    raise ValueError(f"runtime credential already exists: {record.resource_id}")
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
            except Exception:
                self._connection.rollback()
                raise

    def rotate_credential(self, record: ResourceCredentialRecord) -> None:
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                cursor = self._connection.execute(
                    "UPDATE resource_credentials SET credential_id = ?, owner_scope = ?, secret_digest = ?, encrypted_secret = ?, created_at = ? "
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
                    self._connection.rollback()
                    raise KeyError(f"runtime credential not found: {record.resource_id}")
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

    def get_credential(self, runtime_id: str) -> ResourceCredentialRecord:
        row = self._connection.execute(
            "SELECT credential_id, owner_scope, secret_digest, encrypted_secret, created_at "
            "FROM resource_credentials WHERE resource_id = ?",
            (runtime_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"runtime credential not found: {runtime_id}")
        return ResourceCredentialRecord(
            resource_id=runtime_id,
            credential_id=str(row[0]),
            owner_scope=str(row[1]),
            secret_digest=str(row[2]),
            encrypted_secret=str(row[3]),
            created_at=datetime.fromisoformat(str(row[4])),
        )

    def consume_nonce(
        self,
        runtime_id: str,
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
                cursor = self._connection.execute(
                    "INSERT INTO resource_auth_nonces(resource_id, nonce, expires_at) VALUES (?, ?, ?)",
                    (
                        runtime_id,
                        nonce,
                        expires_at.astimezone(timezone.utc).isoformat(),
                    ),
                )
                self._connection.commit()
                return cursor.rowcount == 1
            except sqlite3.IntegrityError:
                # nonce 唯一键冲突即已消费，调用鉴权层会将其归类为重放。
                self._connection.rollback()
                return False
            except Exception:
                self._connection.rollback()
                raise

    def close(self) -> None:
        with self._lock:
            self._connection.close()


__all__ = [
    # TODO(runtime-store-migration): 跨主机部署时应将事务和 nonce 去重迁移到集中式数据库/缓存协调器。
    "InMemoryResourceStore",
    "ResourceCredentialRecord",
    "SQLiteResourceStore",
    "StaleResourceObservation",
    "VersionConflict",
]
