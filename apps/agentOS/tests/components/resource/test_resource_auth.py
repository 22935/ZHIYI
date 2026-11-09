"""资源凭据与签名请求合同：一次性密钥、轮换、重放保护。

密钥只在签发/轮换响应中出现一次；库文件中不得出现明文或可直接推导
HMAC 键的材料。远程 Runtime 与远程 Node 共用同一套 HMAC 请求签名协议。
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import time

import pytest

from components.resource.infrastructure.signing.request_authenticator import (
    NodeRequestAuthenticator,
    ResourceRequestAuthenticator,
    ResourceRequestExpired,
    ResourceRequestInvalid,
    ResourceRequestNotFound,
    ResourceRequestReplay,
)
from components.resource.application.resource_plane import ResourcePlane
from components.resource.infrastructure.runtime_store import SQLiteResourceStore
from contracts.resource import (
    HealthStatus,
    NodeHealthStatus,
    NodeProfile,
    NodeSnapshot,
    Placement,
    ResourceEndpoint,
    RuntimeKind,
    RuntimeProfile,
    RuntimeSnapshot,
    TrustLevel,
)
from contracts.resource_signing import build_resource_signature
from cryptography.fernet import Fernet


def _plane() -> ResourcePlane:
    return ResourcePlane()


def _register_remote_runtime(plane: ResourcePlane, runtime_id: str = "runtime:edge-exec-1"):
    plane.ensure_node("node:edge-1", placement=Placement.EDGE, trust=TrustLevel.TRUSTED)
    profile = RuntimeProfile(
        runtimeId=runtime_id,
        kind=RuntimeKind.EXECUTION_BACKEND,
        nodeId="node:edge-1",
        placement=Placement.EDGE,
        capabilities=["repo.read"],
        trust=TrustLevel.TRUSTED,
        endpoint=ResourceEndpoint(protocol="https", address=f"https://edge-1/{runtime_id}"),
        ownerScope="scope-a",
        capacity=2,
    )
    snapshot = RuntimeSnapshot(
        runtimeId=runtime_id,
        availableSlots=2,
        utilization=0.0,
        healthStatus=HealthStatus.UNKNOWN,
    )
    return plane.register_remote_runtime(profile, snapshot)


def _signed_headers(secret: str, *, method="POST", path="/observe", body=b"{}", nonce=None):
    timestamp = int(time.time())
    nonce = nonce or f"n-{timestamp}-{id(object())}"
    signature = build_resource_signature(
        secret,
        method=method,
        path=path,
        timestamp=timestamp,
        nonce=nonce,
        body=body,
    )
    return timestamp, nonce, signature


def test_issue_credential_returns_secret_once_and_verifies_without_storing_plaintext() -> None:
    plane = _plane()
    issued = _register_remote_runtime(plane)
    assert issued.secret and issued.credential_id

    record = plane.runtime_credential(issued.resource_id)
    assert record.credential_id == issued.credential_id
    # 库里只有摘要与加密形态，明文密钥不出现在任何记录字段。
    assert issued.secret not in (record.secret_digest, record.encrypted_secret)
    assert plane.verify_runtime_credential(issued.resource_id, issued.credential_id, issued.secret)


def test_remote_runtime_registration_is_idempotent_without_reissuing_secret() -> None:
    plane = _plane()
    first = _register_remote_runtime(plane)
    profile = plane.runtime(first.resource_id)
    snapshot = plane.runtime_snapshot(first.resource_id).snapshot

    repeated = plane.register_remote_runtime(profile, snapshot)

    assert repeated.created is False
    assert repeated.credential_id == first.credential_id
    assert repeated.secret == ""


def test_sqlite_credential_survives_restart_without_persisting_plaintext(tmp_path: Path) -> None:
    db_path = tmp_path / "plane.sqlite3"
    master_key = Fernet.generate_key().decode("ascii")
    plane = ResourcePlane(store=SQLiteResourceStore(db_path), credential_key=master_key)
    issued = _register_remote_runtime(plane)
    plane.store.close()

    raw = db_path.read_bytes()
    assert issued.secret.encode("utf-8") not in raw

    reopened = ResourcePlane(store=SQLiteResourceStore(db_path), credential_key=master_key)
    assert reopened.verify_runtime_credential(issued.resource_id, issued.credential_id, issued.secret)
    reopened.store.close()


def test_unknown_or_wrong_secret_is_rejected() -> None:
    plane = _plane()
    issued = _register_remote_runtime(plane)
    with pytest.raises(ValueError):
        plane.verify_runtime_credential(issued.resource_id, issued.credential_id, "wrong-secret")
    with pytest.raises(ValueError):
        plane.verify_runtime_credential("runtime:missing", issued.credential_id, issued.secret)


def test_rotate_credential_replaces_secret_and_invalidates_previous_credential() -> None:
    plane = _plane()
    issued = _register_remote_runtime(plane)
    rotated = plane.rotate_runtime_credential(issued.resource_id)
    assert rotated.credential_id != issued.credential_id
    assert plane.verify_runtime_credential(issued.resource_id, rotated.credential_id, rotated.secret)
    with pytest.raises(ValueError):
        plane.verify_runtime_credential(issued.resource_id, issued.credential_id, issued.secret)


def test_failed_credential_rotation_keeps_previous_credential_usable(monkeypatch) -> None:
    plane = _plane()
    issued = _register_remote_runtime(plane)

    def broken_rotate(_record):
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(plane.store, "rotate_credential", broken_rotate)
    with pytest.raises(RuntimeError):
        plane.rotate_runtime_credential(issued.resource_id)
    assert plane.verify_runtime_credential(issued.resource_id, issued.credential_id, issued.secret)


def test_remote_registration_rolls_back_profile_when_initial_credential_persistence_fails() -> None:
    plane = _plane()
    first = _register_remote_runtime(plane, "runtime:edge-exec-1")
    plane.ensure_node("node:edge-2", placement=Placement.EDGE, trust=TrustLevel.TRUSTED)
    conflicting = RuntimeProfile(
        runtimeId="runtime:edge-exec-2",
        kind=RuntimeKind.EXECUTION_BACKEND,
        nodeId="node:edge-2",
        placement=Placement.EDGE,
        capabilities=["repo.read"],
        trust=TrustLevel.TRUSTED,
        endpoint=ResourceEndpoint(protocol="https", address="https://edge-2/exec"),
        ownerScope="scope-a",
    )
    snapshot = RuntimeSnapshot(
        runtimeId="runtime:edge-exec-2", availableSlots=1, utilization=0.0
    )
    with pytest.raises(ValueError):
        plane.register_remote_runtime(
            conflicting, snapshot, credential_id=first.credential_id, secret="s"
        )
    with pytest.raises(KeyError):
        plane.runtime("runtime:edge-exec-2")


def test_nonce_can_be_consumed_only_once_until_expiry() -> None:
    plane = _plane()
    issued = _register_remote_runtime(plane)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=5)
    assert plane.consume_nonce(issued.resource_id, "nonce-1", expires, now=now)
    assert not plane.consume_nonce(issued.resource_id, "nonce-1", expires, now=now)


def test_signed_request_uses_method_path_timestamp_nonce_and_body_digest() -> None:
    plane = _plane()
    issued = _register_remote_runtime(plane)
    body = b'{"availableSlots": 1}'
    timestamp, nonce, signature = _signed_headers(
        issued.secret, method="POST", path="/api/v2/resources/x/observation", body=body
    )
    record = ResourceRequestAuthenticator(plane).authenticate(
        resource_id=issued.resource_id,
        credential_id=issued.credential_id,
        method="POST",
        path="/api/v2/resources/x/observation",
        timestamp=timestamp,
        nonce=nonce,
        signature=signature,
        body=body,
    )
    assert record.resource_id == issued.resource_id


def test_signed_request_rejects_tampering_wrong_credential_and_replay() -> None:
    plane = _plane()
    issued = _register_remote_runtime(plane)
    authenticator = ResourceRequestAuthenticator(plane)
    body = b"{}"
    timestamp, nonce, signature = _signed_headers(issued.secret, body=body)

    common = dict(
        resource_id=issued.resource_id,
        method="POST",
        path="/observe",
        timestamp=timestamp,
        nonce=nonce,
        signature=signature,
        body=body,
    )
    authenticator.authenticate(credential_id=issued.credential_id, **common)

    with pytest.raises(ResourceRequestReplay):
        authenticator.authenticate(credential_id=issued.credential_id, **common)
    with pytest.raises(ResourceRequestInvalid):
        authenticator.authenticate(
            credential_id=issued.credential_id, **{**common, "body": b'{"tampered": 1}'}
        )
    with pytest.raises(ResourceRequestInvalid):
        authenticator.authenticate(credential_id="rc_wrong", **common)
    with pytest.raises(ResourceRequestNotFound):
        authenticator.authenticate(
            credential_id=issued.credential_id,
            **{**common, "resource_id": "runtime:missing"},
        )


def test_signed_request_rejects_expired_timestamp() -> None:
    plane = _plane()
    issued = _register_remote_runtime(plane)
    stale_timestamp = int(time.time()) - 3600
    nonce = f"n-old-{stale_timestamp}"
    signature = build_resource_signature(
        issued.secret,
        method="POST",
        path="/observe",
        timestamp=stale_timestamp,
        nonce=nonce,
        body=b"{}",
    )
    with pytest.raises(ResourceRequestExpired):
        ResourceRequestAuthenticator(plane).authenticate(
            resource_id=issued.resource_id,
            credential_id=issued.credential_id,
            method="POST",
            path="/observe",
            timestamp=stale_timestamp,
            nonce=nonce,
            signature=signature,
            body=b"{}",
        )


def test_node_signed_request_shares_the_same_contract() -> None:
    plane = _plane()
    profile = NodeProfile(
        nodeId="node:edge-9",
        placement=Placement.EDGE,
        trust=TrustLevel.TRUSTED,
        ownerScope="scope-a",
    )
    snapshot = NodeSnapshot(
        nodeId="node:edge-9",
        healthStatus=NodeHealthStatus.ONLINE,
        lastHeartbeat=datetime.now(timezone.utc),
    )
    issued = plane.register_remote_node(profile, snapshot)
    body = b"{}"
    timestamp, nonce, signature = _signed_headers(issued.secret, body=body)
    authenticator = NodeRequestAuthenticator(plane)

    record = authenticator.authenticate(
        node_id=issued.node_id,
        credential_id=issued.credential_id,
        method="POST",
        path="/observe",
        timestamp=timestamp,
        nonce=nonce,
        signature=signature,
        body=body,
    )
    assert record.resource_id == issued.node_id
    with pytest.raises(ResourceRequestReplay):
        authenticator.authenticate(
            node_id=issued.node_id,
            credential_id=issued.credential_id,
            method="POST",
            path="/observe",
            timestamp=timestamp,
            nonce=nonce,
            signature=signature,
            body=body,
        )
