"""资源商店目录、安装任务与自定义本地服务的数据合同。"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from contracts.resource import ResourceEndpoint, RuntimeKind


class InstallationStatus(str, Enum):
    QUEUED = "queued"
    INSTALLING = "installing"
    REGISTERING = "registering"
    RUNNING = "running"
    FAILED = "failed"
    STOPPED = "stopped"
    UNINSTALLING = "uninstalling"
    REMOVED = "removed"


_ALLOWED_TRANSITIONS = {
    InstallationStatus.QUEUED: {InstallationStatus.INSTALLING, InstallationStatus.FAILED},
    InstallationStatus.INSTALLING: {InstallationStatus.REGISTERING, InstallationStatus.FAILED},
    InstallationStatus.REGISTERING: {InstallationStatus.RUNNING, InstallationStatus.FAILED},
    InstallationStatus.RUNNING: {InstallationStatus.STOPPED, InstallationStatus.UNINSTALLING},
    InstallationStatus.STOPPED: {InstallationStatus.UNINSTALLING},
    InstallationStatus.UNINSTALLING: {InstallationStatus.REMOVED, InstallationStatus.FAILED},
}


class CatalogItem(BaseModel):
    """平台预置的本地安装项；启动定义只能来自受控平台目录。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    catalog_id: StrictStr = Field(alias="catalogId", min_length=1, max_length=160)
    kind: RuntimeKind
    version: StrictStr = Field(min_length=1, max_length=80)
    display_name: StrictStr = Field(default="", alias="displayName", max_length=160)
    description: StrictStr = Field(default="", max_length=2000)
    package_path: StrictStr = Field(alias="packagePath", min_length=1, max_length=512)
    sha256: StrictStr = Field(pattern=r"^[a-fA-F0-9]{64}$")
    size_bytes: int = Field(default=0, alias="sizeBytes", ge=0)
    requirements: dict[str, Any] = Field(default_factory=dict)
    runtime: dict[str, Any]
    startup: dict[str, Any] = Field(default_factory=dict)
    category: StrictStr = Field(default="", max_length=80)

    @field_validator("package_path")
    @classmethod
    def validate_package_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or "\\" in value or value in {"", "."}:
            raise ValueError("packagePath must be a safe relative POSIX path")
        return value


class InstallationJob(BaseModel):
    """不包含包内容、凭据或命令的安装任务投影。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid", validate_assignment=True)

    job_id: StrictStr = Field(alias="jobId", min_length=1)
    catalog_id: StrictStr | None = Field(default=None, alias="catalogId")
    owner_scope: StrictStr = Field(alias="ownerScope", min_length=1)
    status: InstallationStatus = InstallationStatus.QUEUED
    runtime_id: StrictStr | None = Field(default=None, alias="runtimeId")
    display_name: StrictStr = Field(default="", alias="displayName")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), alias="createdAt")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), alias="updatedAt")
    error_summary: StrictStr | None = Field(default=None, alias="errorSummary", max_length=500)

    @classmethod
    def new(cls, job_id: str, catalog_id: str | None, owner_scope: str, *, display_name: str = "") -> InstallationJob:
        return cls(jobId=job_id, catalogId=catalog_id, ownerScope=owner_scope, displayName=display_name)

    def advance(
        self,
        status: InstallationStatus,
        *,
        runtime_id: str | None = None,
        error_summary: str | None = None,
    ) -> InstallationJob:
        if status not in _ALLOWED_TRANSITIONS.get(self.status, set()):
            raise ValueError(f"invalid installation status transition: {self.status.value} -> {status.value}")
        return self.model_copy(update={
            "status": status,
            "runtime_id": runtime_id if runtime_id is not None else self.runtime_id,
            "error_summary": error_summary,
            "updated_at": datetime.now(timezone.utc),
        })


class CustomResourceRequest(BaseModel):
    """用户自定义已运行的本地 HTTP 服务；合同中不接受 shell 命令。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    display_name: StrictStr = Field(alias="displayName", min_length=1, max_length=120)
    kind: RuntimeKind
    endpoint: ResourceEndpoint
    capabilities: list[StrictStr] = Field(min_length=1)
    model_ids: list[StrictStr] = Field(default_factory=list, alias="modelIds")
    provider: StrictStr | None = None
    adapter: StrictStr | None = None

    @field_validator("endpoint")
    @classmethod
    def require_loopback_endpoint(cls, value: ResourceEndpoint) -> ResourceEndpoint:
        parsed = urlsplit(value.address)
        if value.protocol not in {"http", "https"} or parsed.hostname not in {
            "127.0.0.1", "localhost", "::1", "[::1]"
        }:
            raise ValueError("custom resources must use a local loopback HTTP(S) endpoint")
        return value
