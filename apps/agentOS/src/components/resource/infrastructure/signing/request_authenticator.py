"""远程边缘/云节点请求的资源级签名鉴权。

认证顺序固定为：查找身份、校验凭据、校验时间窗口、校验 HMAC 完整性，
最后原子消费 nonce。只有全部通过的请求才会消耗 nonce，避免无效请求
污染重放保护存储。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from typing import Protocol

from ...contracts.resource_signing import (
    build_resource_signature,
    canonical_resource_request as _canonical_request,
)

from ...domain.credentials import ResourceCredentialRecord


class ResourceAuthenticationPort(Protocol):
    """鉴权器所需的最小应用能力，不暴露资源平面的其他用例。"""

    def runtime_credential(self, resource_id: str) -> ResourceCredentialRecord: ...
    def node_credential(self, node_id: str) -> ResourceCredentialRecord: ...
    def runtime_credential_hmac_key(self, resource_id: str, credential_id: str) -> bytes: ...
    def node_credential_hmac_key(self, node_id: str, credential_id: str) -> bytes: ...
    def consume_nonce(self, resource_id: str, nonce: str, expires_at: datetime, *, now: datetime) -> bool: ...
    def consume_node_nonce(self, node_id: str, nonce: str, expires_at: datetime, *, now: datetime) -> bool: ...


class ResourceRequestExpired(ValueError):
    """签名时间戳超出允许的时钟偏差窗口。"""


class ResourceRequestReplay(ValueError):
    """请求 nonce 已被成功消费，表示该请求可能被重放。"""


class ResourceRequestNotFound(ValueError):
    """请求声明的资源或节点不存在。"""


class ResourceRequestInvalid(ValueError):
    """凭据或签名与目标资源不匹配。"""


class ResourceRequestAuthenticator:
    """验证 Runtime 请求的身份、新鲜度、完整性与重放保护。"""

    def __init__(
        self,
        plane: ResourceAuthenticationPort,
        *,
        clock_skew: timedelta = timedelta(minutes=5),
    ) -> None:
        if clock_skew <= timedelta(0):
            raise ValueError("clock skew must be positive")
        self.plane = plane
        self.clock_skew = clock_skew

    def authenticate(
        self,
        *,
        resource_id: str,
        credential_id: str,
        method: str,
        path: str,
        timestamp: int,
        nonce: str,
        signature: str,
        body: bytes,
        now: datetime | None = None,
    ) -> ResourceCredentialRecord:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        try:
            record = self.plane.runtime_credential(resource_id)
        except KeyError as error:
            raise ResourceRequestNotFound("resource not found") from error
        if record.credential_id != credential_id:
            raise ResourceRequestInvalid("resource credential is invalid")

        try:
            signed_at = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as error:
            raise ResourceRequestExpired("resource request timestamp is invalid") from error
        if abs((current - signed_at).total_seconds()) > self.clock_skew.total_seconds():
            raise ResourceRequestExpired("resource request timestamp is expired")

        # 使用恒定时间比较，避免签名不匹配时泄露前缀匹配长度。
        expected = hmac.new(
            self.plane.runtime_credential_hmac_key(resource_id, credential_id),
            _canonical_request(
                method=method,
                path=path,
                timestamp=timestamp,
                nonce=nonce,
                body=body,
            ),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ResourceRequestInvalid("resource signature is invalid")

        expires_at = signed_at + self.clock_skew
        if not self.plane.consume_nonce(
            resource_id, nonce, expires_at, now=current
        ):
            raise ResourceRequestReplay("resource request nonce was already used")
        return record


class NodeRequestAuthenticator:
    """使用与 Runtime 相同的 HMAC 合约验证 Node 台账请求。"""

    def __init__(
        self,
        plane: ResourceAuthenticationPort,
        *,
        clock_skew: timedelta = timedelta(minutes=5),
    ) -> None:
        if clock_skew <= timedelta(0):
            raise ValueError("clock skew must be positive")
        self.plane = plane
        self.clock_skew = clock_skew

    def authenticate(
        self,
        *,
        node_id: str,
        credential_id: str,
        method: str,
        path: str,
        timestamp: int,
        nonce: str,
        signature: str,
        body: bytes,
        now: datetime | None = None,
    ) -> ResourceCredentialRecord:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        try:
            record = self.plane.node_credential(node_id)
        except KeyError as error:
            raise ResourceRequestNotFound("node not found") from error
        if record.credential_id != credential_id:
            raise ResourceRequestInvalid("node credential is invalid")

        try:
            signed_at = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as error:
            raise ResourceRequestExpired("node request timestamp is invalid") from error
        if abs((current - signed_at).total_seconds()) > self.clock_skew.total_seconds():
            raise ResourceRequestExpired("node request timestamp is expired")

        # Node 与 Runtime 分开取密钥和消费 nonce，防止跨资源命名空间重放。
        expected = hmac.new(
            self.plane.node_credential_hmac_key(node_id, credential_id),
            _canonical_request(
                method=method,
                path=path,
                timestamp=timestamp,
                nonce=nonce,
                body=body,
            ),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ResourceRequestInvalid("node signature is invalid")

        expires_at = signed_at + self.clock_skew
        if not self.plane.consume_node_nonce(node_id, nonce, expires_at, now=current):
            raise ResourceRequestReplay("node request nonce was already used")
        return record


# TODO(key-rotation): 支持 credential 的宽限期轮换后，应允许当前与上一把密钥并行校验。
