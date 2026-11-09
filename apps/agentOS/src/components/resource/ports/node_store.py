"""Node 持久化端口；定义应用层所需的最小读写能力。"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from contracts.resource import NodeProfile, NodeSnapshot

from ..domain.models import VersionedNodeSnapshot
from ..domain.credentials import ResourceCredentialRecord


class NodeStore(Protocol):
    """隔离 Node 用例与具体内存/SQLite 存储实现。"""

    def register(self, profile: NodeProfile, snapshot: NodeSnapshot) -> VersionedNodeSnapshot: ...

    def register_remote(
        self, profile: NodeProfile, snapshot: NodeSnapshot, credential: ResourceCredentialRecord
    ) -> VersionedNodeSnapshot: ...

    def get_profile(self, node_id: str) -> NodeProfile: ...

    def get_snapshot(self, node_id: str) -> VersionedNodeSnapshot: ...

    def list_profiles(self) -> list[NodeProfile]: ...

    def update_snapshot(
        self, snapshot: NodeSnapshot, *, expected_version: int | None = None
    ) -> VersionedNodeSnapshot: ...

    def update_profile(self, profile: NodeProfile) -> NodeProfile: ...

    def save_credential(self, record: ResourceCredentialRecord) -> None: ...

    def rotate_credential(self, record: ResourceCredentialRecord) -> None: ...

    def get_credential(self, node_id: str) -> ResourceCredentialRecord: ...

    def consume_nonce(
        self, node_id: str, nonce: str, expires_at: datetime, *, now: datetime
    ) -> bool: ...
