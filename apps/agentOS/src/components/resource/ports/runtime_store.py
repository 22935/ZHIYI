"""Runtime、模型端点、凭据与 nonce 的持久化端口。"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from contracts.resource import ModelEndpointProfile, RuntimeProfile, RuntimeSnapshot

from ..domain.models import VersionedRuntimeSnapshot
from ..domain.credentials import ResourceCredentialRecord


class RuntimeStore(Protocol):
    """应用服务操作 Runtime 资源目录所依赖的最小契约。"""

    def register(self, profile: RuntimeProfile, snapshot: RuntimeSnapshot) -> VersionedRuntimeSnapshot: ...

    def register_remote(
        self, profile: RuntimeProfile, snapshot: RuntimeSnapshot, credential: ResourceCredentialRecord
    ) -> VersionedRuntimeSnapshot: ...

    def get_profile(self, runtime_id: str) -> RuntimeProfile: ...

    def get_snapshot(self, runtime_id: str) -> VersionedRuntimeSnapshot: ...

    def list_profiles(self) -> list[RuntimeProfile]: ...

    def delete_runtime(self, runtime_id: str) -> None: ...

    def update_snapshot(
        self, snapshot: RuntimeSnapshot, *, expected_version: int | None = None
    ) -> VersionedRuntimeSnapshot: ...

    def update_capacity(
        self, runtime_id: str, capacity: int, *, expected_capacity: int
    ) -> VersionedRuntimeSnapshot: ...

    def update_profile(self, profile: RuntimeProfile) -> RuntimeProfile: ...

    def upsert_model_endpoint(self, endpoint: ModelEndpointProfile) -> tuple[ModelEndpointProfile, bool]: ...

    def get_model_endpoint(self, endpoint_id: str) -> ModelEndpointProfile: ...

    def list_model_endpoints(self) -> list[ModelEndpointProfile]: ...

    def delete_model_endpoint(self, endpoint_id: str) -> None: ...

    def save_credential(self, record: ResourceCredentialRecord) -> None: ...

    def rotate_credential(self, record: ResourceCredentialRecord) -> None: ...

    def get_credential(self, runtime_id: str) -> ResourceCredentialRecord: ...

    def consume_nonce(
        self, runtime_id: str, nonce: str, expires_at: datetime, *, now: datetime
    ) -> bool: ...
