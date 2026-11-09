"""节点资源表的存储实现（协议、内存与 SQLite）。

Node 是部署实体，静态画像和动态快照分离管理；所有读取返回副本，避免
调用方绕开版本控制修改状态。远程登记与凭据写入必须保持原子性。
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sqlite3
from threading import RLock

from contracts.resource import NodeProfile, NodeSnapshot

from ..domain.models import VersionedNodeSnapshot
from .runtime_store import ResourceCredentialRecord, StaleResourceObservation, VersionConflict
from .sqlite.connection import configure_sqlite_connection
from ..ports.node_store import NodeStore


class InMemoryNodeStore:
    """面向单进程运行的节点资源存储，主要用于测试和本地开发。"""

    def __init__(self) -> None:
        self._profiles: dict[str, NodeProfile] = {}
        self._snapshots: dict[str, VersionedNodeSnapshot] = {}
        self._credentials: dict[str, ResourceCredentialRecord] = {}
        self._nonces: dict[tuple[str, str], datetime] = {}
        self._lock = RLock()

    def register(self, profile: NodeProfile, snapshot: NodeSnapshot) -> VersionedNodeSnapshot:
        if profile.node_id != snapshot.node_id:
            raise ValueError("profile and snapshot nodeId must match")
        with self._lock:
            if profile.node_id in self._profiles:
                current_profile = self._profiles[profile.node_id]
                current_snapshot = self._snapshots[profile.node_id]
                if current_profile == profile and current_snapshot.snapshot == snapshot:
                    return self._copy(current_snapshot)
                raise ValueError(f"node already registered: {profile.node_id}")
            # 存储副本与返回副本隔离，保护版本和序号不变量。
            self._profiles[profile.node_id] = profile.model_copy(deep=True)
            versioned = VersionedNodeSnapshot(snapshot=snapshot.model_copy(deep=True), version=1)
            self._snapshots[profile.node_id] = versioned
            return self._copy(versioned)

    def register_remote(
        self,
        profile: NodeProfile,
        snapshot: NodeSnapshot,
        credential: ResourceCredentialRecord,
    ) -> VersionedNodeSnapshot:
        if profile.node_id != snapshot.node_id or profile.node_id != credential.resource_id:
            raise ValueError("remote registration nodeId values must match")
        with self._lock:
            if profile.node_id in self._profiles:
                raise ValueError(f"node already registered: {profile.node_id}")
            if any(item.credential_id == credential.credential_id for item in self._credentials.values()):
                raise ValueError(f"node credential already exists: {credential.credential_id}")
            versioned = VersionedNodeSnapshot(snapshot=snapshot.model_copy(deep=True), version=1)
            self._profiles[profile.node_id] = profile.model_copy(deep=True)
            self._snapshots[profile.node_id] = versioned
            self._credentials[profile.node_id] = credential
            return self._copy(versioned)

    def get_profile(self, node_id: str) -> NodeProfile:
        try:
            return self._profiles[node_id].model_copy(deep=True)
        except KeyError as error:
            raise KeyError(f"unknown node: {node_id}") from error

    def get_snapshot(self, node_id: str) -> VersionedNodeSnapshot:
        try:
            return self._copy(self._snapshots[node_id])
        except KeyError as error:
            raise KeyError(f"unknown node: {node_id}") from error

    def list_profiles(self) -> list[NodeProfile]:
        return [self._profiles[key].model_copy(deep=True) for key in sorted(self._profiles)]

    def update_snapshot(
        self, snapshot: NodeSnapshot, *, expected_version: int | None = None
    ) -> VersionedNodeSnapshot:
        with self._lock:
            try:
                current = self._snapshots[snapshot.node_id]
            except KeyError as error:
                raise KeyError(f"unknown node: {snapshot.node_id}") from error
            if expected_version is not None and expected_version != current.version:
                raise VersionConflict(
                    f"snapshot version conflict for {snapshot.node_id}: "
                    f"expected {expected_version}, current {current.version}"
                )
            if snapshot.observation_sequence < current.snapshot.observation_sequence:
                raise StaleResourceObservation(
                    f"stale observation for {snapshot.node_id}: "
                    f"received {snapshot.observation_sequence}, "
                    f"current {current.snapshot.observation_sequence}"
                )
            versioned = VersionedNodeSnapshot(
                snapshot=snapshot.model_copy(deep=True), version=current.version + 1
            )
            self._snapshots[snapshot.node_id] = versioned
            return self._copy(versioned)

    def save_credential(self, record: ResourceCredentialRecord) -> None:
        with self._lock:
            if record.resource_id not in self._profiles:
                raise KeyError(f"unknown node: {record.resource_id}")
            if record.resource_id in self._credentials:
                raise ValueError(f"node credential already exists: {record.resource_id}")
            self._credentials[record.resource_id] = record

    def update_profile(self, profile: NodeProfile) -> NodeProfile:
        with self._lock:
            try:
                current = self._profiles[profile.node_id]
            except KeyError as error:
                raise KeyError(f"unknown node: {profile.node_id}") from error
            if profile.node_id != current.node_id:
                raise ValueError("node profile identity is immutable")
            self._profiles[profile.node_id] = profile.model_copy(deep=True)
            return profile.model_copy(deep=True)

    def rotate_credential(self, record: ResourceCredentialRecord) -> None:
        with self._lock:
            if record.resource_id not in self._profiles:
                raise KeyError(f"unknown node: {record.resource_id}")
            if record.resource_id not in self._credentials:
                raise KeyError(f"node credential not found: {record.resource_id}")
            self._credentials[record.resource_id] = record

    def get_credential(self, node_id: str) -> ResourceCredentialRecord:
        with self._lock:
            try:
                return self._credentials[node_id]
            except KeyError as error:
                raise KeyError(f"node credential not found: {node_id}") from error

    def consume_nonce(
        self, node_id: str, nonce: str, expires_at: datetime, *, now: datetime
    ) -> bool:
        with self._lock:
            # 每次消费前清理过期 nonce，限制常驻进程的重放记录增长。
            self._nonces = {key: expiry for key, expiry in self._nonces.items() if expiry > now}
            key = (node_id, nonce)
            if expires_at <= now or key in self._nonces:
                return False
            self._nonces[key] = expires_at
            return True

    @staticmethod
    def _copy(value: VersionedNodeSnapshot) -> VersionedNodeSnapshot:
        return VersionedNodeSnapshot(snapshot=value.snapshot.model_copy(deep=True), version=value.version)


class SQLiteNodeStore:
    """由 SQLite 支撑的 Node 注册表，保存画像、快照、凭据和 nonce。"""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = configure_sqlite_connection(
            sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
        )
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS nodes (
                node_id TEXT PRIMARY KEY,
                profile_json TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,
                version INTEGER NOT NULL CHECK(version >= 1)
            )"""
        )
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS node_credentials (
                node_id TEXT PRIMARY KEY,
                credential_id TEXT NOT NULL UNIQUE,
                owner_scope TEXT NOT NULL,
                secret_digest TEXT NOT NULL,
                encrypted_secret TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS node_auth_nonces (
                node_id TEXT NOT NULL,
                nonce TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                PRIMARY KEY(node_id, nonce)
            )"""
        )
        # 旧版节点画像（NodeType/privacy 等字段）无法按当前合同解析；由引导
        # 流程重新登记，不保留跨版本迁移包袱。
        for rowid, payload in self._connection.execute(
            "SELECT rowid, profile_json FROM nodes"
        ).fetchall():
            try:
                NodeProfile.model_validate(json.loads(str(payload)))
            except Exception:
                self._connection.execute("DELETE FROM nodes WHERE rowid = ?", (rowid,))
        self._connection.commit()
        self._lock = RLock()

    @staticmethod
    def _json(model: NodeProfile | NodeSnapshot) -> str:
        return json.dumps(
            model.model_dump(by_alias=True, mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _snapshot(row: tuple[object, object]) -> VersionedNodeSnapshot:
        return VersionedNodeSnapshot(
            snapshot=NodeSnapshot.model_validate(json.loads(str(row[0]))),
            version=int(row[1]),
        )

    def register(self, profile: NodeProfile, snapshot: NodeSnapshot) -> VersionedNodeSnapshot:
        if profile.node_id != snapshot.node_id:
            raise ValueError("profile and snapshot nodeId must match")
        with self._lock:
            row = self._connection.execute(
                "SELECT profile_json, snapshot_json, version FROM nodes WHERE node_id = ?",
                (profile.node_id,),
            ).fetchone()
            if row is not None:
                current_profile = NodeProfile.model_validate(json.loads(str(row[0])))
                current_snapshot = NodeSnapshot.model_validate(json.loads(str(row[1])))
                if current_profile == profile and current_snapshot == snapshot:
                    return self._snapshot((row[1], row[2]))
                raise ValueError(f"node already registered: {profile.node_id}")
            self._connection.execute(
                "INSERT INTO nodes(node_id, profile_json, snapshot_json, version) VALUES (?, ?, ?, 1)",
                (profile.node_id, self._json(profile), self._json(snapshot)),
            )
            self._connection.commit()
            return VersionedNodeSnapshot(snapshot=snapshot.model_copy(deep=True), version=1)

    def register_remote(
        self,
        profile: NodeProfile,
        snapshot: NodeSnapshot,
        credential: ResourceCredentialRecord,
    ) -> VersionedNodeSnapshot:
        if profile.node_id != snapshot.node_id or profile.node_id != credential.resource_id:
            raise ValueError("remote registration nodeId values must match")
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                existing = self._connection.execute(
                    "SELECT 1 FROM nodes WHERE node_id = ?", (profile.node_id,)
                ).fetchone()
                if existing is not None:
                    raise ValueError(f"node already registered: {profile.node_id}")
                duplicate = self._connection.execute(
                    "SELECT 1 FROM node_credentials WHERE credential_id = ?",
                    (credential.credential_id,),
                ).fetchone()
                if duplicate is not None:
                    raise ValueError(f"node credential already exists: {credential.credential_id}")
                self._connection.execute(
                    "INSERT INTO nodes(node_id, profile_json, snapshot_json, version) VALUES (?, ?, ?, 1)",
                    (profile.node_id, self._json(profile), self._json(snapshot)),
                )
                self._insert_credential(credential)
                self._connection.commit()
                return VersionedNodeSnapshot(snapshot=snapshot.model_copy(deep=True), version=1)
            except sqlite3.IntegrityError as error:
                self._connection.rollback()
                raise ValueError("remote node registration violates a storage constraint") from error
            except Exception:
                self._connection.rollback()
                raise

    def get_profile(self, node_id: str) -> NodeProfile:
        row = self._connection.execute(
            "SELECT profile_json FROM nodes WHERE node_id = ?", (node_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown node: {node_id}")
        return NodeProfile.model_validate(json.loads(str(row[0])))

    def get_snapshot(self, node_id: str) -> VersionedNodeSnapshot:
        row = self._connection.execute(
            "SELECT snapshot_json, version FROM nodes WHERE node_id = ?", (node_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown node: {node_id}")
        return self._snapshot(row)

    def list_profiles(self) -> list[NodeProfile]:
        rows = self._connection.execute(
            "SELECT profile_json FROM nodes ORDER BY node_id"
        ).fetchall()
        return [NodeProfile.model_validate(json.loads(str(row[0]))) for row in rows]

    def update_snapshot(
        self, snapshot: NodeSnapshot, *, expected_version: int | None = None
    ) -> VersionedNodeSnapshot:
        with self._lock:
            row = self._connection.execute(
                "SELECT snapshot_json, version FROM nodes WHERE node_id = ?",
                (snapshot.node_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown node: {snapshot.node_id}")
            current_snapshot = NodeSnapshot.model_validate(json.loads(str(row[0])))
            current_version = int(row[1])
            # 期望版本不匹配时拒绝覆盖，调用方应重新读取后再合并观测。
            if expected_version is not None and expected_version != current_version:
                raise VersionConflict(
                    f"snapshot version conflict for {snapshot.node_id}: "
                    f"expected {expected_version}, current {current_version}"
                )
            if snapshot.observation_sequence <= current_snapshot.observation_sequence:
                raise StaleResourceObservation(
                    f"stale observation for {snapshot.node_id}: "
                    f"received {snapshot.observation_sequence}, "
                    f"current {current_snapshot.observation_sequence}"
                )
            next_version = current_version + 1
            cursor = self._connection.execute(
                "UPDATE nodes SET snapshot_json = ?, version = ? WHERE node_id = ? AND version = ?",
                (self._json(snapshot), next_version, snapshot.node_id, current_version),
            )
            if cursor.rowcount != 1:
                self._connection.rollback()
                raise VersionConflict(f"snapshot version conflict for {snapshot.node_id}")
            self._connection.commit()
            return VersionedNodeSnapshot(snapshot=snapshot.model_copy(deep=True), version=next_version)

    def save_credential(self, record: ResourceCredentialRecord) -> None:
        with self._lock:
            if self._connection.execute(
                "SELECT 1 FROM nodes WHERE node_id = ?", (record.resource_id,)
            ).fetchone() is None:
                raise KeyError(f"unknown node: {record.resource_id}")
            try:
                self._insert_credential(record)
                self._connection.commit()
            except sqlite3.IntegrityError as error:
                self._connection.rollback()
                raise ValueError(f"node credential already exists: {record.resource_id}") from error

    def update_profile(self, profile: NodeProfile) -> NodeProfile:
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                row = self._connection.execute(
                    "SELECT profile_json FROM nodes WHERE node_id = ?",
                    (profile.node_id,),
                ).fetchone()
                if row is None:
                    raise KeyError(f"unknown node: {profile.node_id}")
                current = NodeProfile.model_validate(json.loads(str(row[0])))
                if profile.node_id != current.node_id:
                    raise ValueError("node profile identity is immutable")
                self._connection.execute(
                    "UPDATE nodes SET profile_json = ? WHERE node_id = ?",
                    (self._json(profile), profile.node_id),
                )
                self._connection.commit()
                return profile.model_copy(deep=True)
            except Exception:
                self._connection.rollback()
                raise

    def rotate_credential(self, record: ResourceCredentialRecord) -> None:
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                if self._connection.execute(
                    "SELECT 1 FROM nodes WHERE node_id = ?", (record.resource_id,)
                ).fetchone() is None:
                    raise KeyError(f"unknown node: {record.resource_id}")
                cursor = self._connection.execute(
                    "UPDATE node_credentials SET credential_id = ?, owner_scope = ?, "
                    "secret_digest = ?, encrypted_secret = ?, created_at = ? WHERE node_id = ?",
                    (
                        record.credential_id,
                        record.owner_scope,
                        record.secret_digest,
                        record.encrypted_secret,
                        record.created_at.isoformat(),
                        record.resource_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise KeyError(f"node credential not found: {record.resource_id}")
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

    def get_credential(self, node_id: str) -> ResourceCredentialRecord:
        row = self._connection.execute(
            "SELECT credential_id, owner_scope, secret_digest, encrypted_secret, created_at "
            "FROM node_credentials WHERE node_id = ?",
            (node_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"node credential not found: {node_id}")
        return ResourceCredentialRecord(
            resource_id=node_id,
            credential_id=str(row[0]),
            owner_scope=str(row[1]),
            secret_digest=str(row[2]),
            encrypted_secret=str(row[3]),
            created_at=datetime.fromisoformat(str(row[4])),
        )

    def consume_nonce(
        self,
        node_id: str,
        nonce: str,
        expires_at: datetime,
        *,
        now: datetime,
    ) -> bool:
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                self._connection.execute(
                    "DELETE FROM node_auth_nonces WHERE expires_at <= ?",
                    (now.isoformat(),),
                )
                if expires_at <= now:
                    self._connection.commit()
                    return False
                self._connection.execute(
                    "INSERT INTO node_auth_nonces(node_id, nonce, expires_at) VALUES (?, ?, ?)",
                    (node_id, nonce, expires_at.isoformat()),
                )
                self._connection.commit()
                return True
            except sqlite3.IntegrityError:
                # 主键冲突表示 nonce 已消费，鉴权层会将其转换为重放异常。
                self._connection.rollback()
                return False


# TODO(node-store-migration): 多机部署时迁移到集中式存储，并保留 nonce 的唯一性约束。
            except Exception:
                self._connection.rollback()
                raise

    def close(self) -> None:
        self._connection.close()

    def _insert_credential(self, record: ResourceCredentialRecord) -> None:
        self._connection.execute(
            "INSERT INTO node_credentials(node_id, credential_id, owner_scope, secret_digest, encrypted_secret, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                record.resource_id,
                record.credential_id,
                record.owner_scope,
                record.secret_digest,
                record.encrypted_secret,
                record.created_at.isoformat(),
            ),
        )
