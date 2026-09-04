from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import sqlite3

import pytest
from cryptography.fernet import Fernet

from components.resource.service import ResourceService
from components.resource.auth import (
    ResourceRequestAuthenticator,
    ResourceRequestExpired,
    ResourceRequestReplay,
    build_resource_signature,
)
from components.resource.store import SQLiteResourceStore
from contracts.resource import DeploymentTier, ResourceEndpoint, ResourceProfile, ResourceSnapshot, ResourceType


NOW = datetime(2026, 9, 2, tzinfo=timezone.utc)


def _service() -> ResourceService:
    resources = ResourceService()
    resources.register(
        ResourceProfile(
            resourceId="edge-auth",
            resourceType=ResourceType.WORKER,
            deploymentTier=DeploymentTier.EDGE,
            capabilities=["vision.infer"],
            ownerScope="tenant-a",
            executionEndpoint=ResourceEndpoint(
                protocol="https",
                address="https://edge-auth.example.test/execute",
            ),
        ),
        ResourceSnapshot(resourceId="edge-auth", availableSlots=1, utilization=0.0),
    )
    return resources


def test_issue_credential_returns_secret_once_and_verifies_without_storing_plaintext() -> None:
    resources = _service()

    issued = resources.issue_credential("edge-auth")

    assert issued.resource_id == "edge-auth"
    assert issued.owner_scope == "tenant-a"
    assert len(issued.secret) >= 32
    verified = resources.verify_credential("edge-auth", issued.credential_id, issued.secret)
    assert verified.resource_id == "edge-auth"
    assert verified.owner_scope == "tenant-a"
    assert issued.secret not in repr(verified)


def test_sqlite_credential_survives_restart_without_persisting_plaintext(tmp_path) -> None:
    db_path = tmp_path / "resources.sqlite3"
    encryption_key = Fernet.generate_key()
    first_store = SQLiteResourceStore(db_path)
    first = ResourceService(store=first_store, credential_key=encryption_key)
    profile_service = _service()
    first.register(profile_service.profile("edge-auth"), profile_service.snapshot("edge-auth").snapshot)
    issued = first.issue_credential("edge-auth")
    first_store.close()

    assert issued.secret.encode() not in db_path.read_bytes()

    second_store = SQLiteResourceStore(db_path)
    second = ResourceService(store=second_store, credential_key=encryption_key)
    try:
        verified = second.verify_credential("edge-auth", issued.credential_id, issued.secret)
        assert verified.owner_scope == "tenant-a"
    finally:
        second_store.close()


def test_resource_database_does_not_store_hmac_key_in_plain_or_derived_form(tmp_path) -> None:
    db_path = tmp_path / "resources.sqlite3"
    encryption_key = Fernet.generate_key()
    store = SQLiteResourceStore(db_path)
    resources = ResourceService(store=store, credential_key=encryption_key)
    profile_service = _service()
    resources.register(
        profile_service.profile("edge-auth"),
        profile_service.snapshot("edge-auth").snapshot,
    )
    issued = resources.issue_credential("edge-auth")
    record = resources.credential("edge-auth")
    store.close()

    database_bytes = db_path.read_bytes()
    assert issued.secret.encode() not in database_bytes
    assert record.secret_digest.encode() in database_bytes
    assert record.encrypted_secret != issued.secret
    assert record.encrypted_secret != record.secret_digest


def test_sqlite_store_rejects_legacy_credential_schema_instead_of_using_unsafe_keys(tmp_path) -> None:
    db_path = tmp_path / "resources.sqlite3"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "CREATE TABLE resource_credentials ("
            "resource_id TEXT PRIMARY KEY, credential_id TEXT NOT NULL UNIQUE, "
            "owner_scope TEXT NOT NULL, secret_hash TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(RuntimeError, match="legacy resource credential schema"):
        SQLiteResourceStore(db_path)


def test_unknown_or_wrong_secret_is_rejected() -> None:
    resources = _service()
    issued = resources.issue_credential("edge-auth")

    with pytest.raises(ValueError, match="credential"):
        resources.verify_credential("edge-auth", "missing", issued.secret)
    with pytest.raises(ValueError, match="credential"):
        resources.verify_credential("edge-auth", issued.credential_id, "wrong-secret")


def test_rotate_credential_replaces_secret_and_invalidates_previous_credential() -> None:
    resources = _service()
    previous = resources.issue_credential("edge-auth")

    rotated = resources.rotate_credential("edge-auth")

    assert rotated.resource_id == previous.resource_id
    assert rotated.owner_scope == previous.owner_scope
    assert rotated.credential_id != previous.credential_id
    assert rotated.secret != previous.secret
    assert resources.verify_credential("edge-auth", rotated.credential_id, rotated.secret)
    with pytest.raises(ValueError, match="credential"):
        resources.verify_credential("edge-auth", previous.credential_id, previous.secret)


def test_failed_credential_rotation_keeps_previous_credential_usable(monkeypatch) -> None:
    resources = _service()
    previous = resources.issue_credential("edge-auth")

    def fail_rotation(record) -> None:
        raise RuntimeError("credential persistence unavailable")

    monkeypatch.setattr(resources.store, "rotate_credential", fail_rotation)
    with pytest.raises(RuntimeError, match="persistence unavailable"):
        resources.rotate_credential("edge-auth")

    assert resources.verify_credential("edge-auth", previous.credential_id, previous.secret)


def test_remote_registration_rolls_back_profile_when_initial_credential_persistence_fails(monkeypatch) -> None:
    resources = ResourceService()
    profile = ResourceProfile(
        resourceId="edge-atomic",
        resourceType=ResourceType.WORKER,
        deploymentTier=DeploymentTier.EDGE,
        capabilities=["analysis"],
        ownerScope="tenant-a",
        executionEndpoint=ResourceEndpoint(protocol="http", address="http://edge-atomic:9000"),
    )

    def fail_registration(profile, snapshot, credential) -> None:
        raise RuntimeError("credential persistence unavailable")

    monkeypatch.setattr(resources.store, "register_remote", fail_registration)
    with pytest.raises(RuntimeError, match="persistence unavailable"):
        resources.register_remote(
            profile,
            ResourceSnapshot(resourceId="edge-atomic", availableSlots=1, utilization=0.0),
        )

    with pytest.raises(KeyError, match="unknown resource"):
        resources.profile("edge-atomic")


def test_nonce_can_be_consumed_only_once_until_expiry() -> None:
    resources = _service()
    expires_at = NOW + timedelta(minutes=5)

    assert resources.consume_nonce("edge-auth", "nonce-1", expires_at, now=NOW) is True
    assert resources.consume_nonce("edge-auth", "nonce-1", expires_at, now=NOW) is False
    assert resources.consume_nonce("edge-auth", "nonce-2", NOW - timedelta(seconds=1), now=NOW) is False


def test_signed_request_uses_method_path_timestamp_nonce_and_body_digest() -> None:
    resources = _service()
    issued = resources.issue_credential("edge-auth")
    body = b'{"availableSlots":1}'
    timestamp = int(NOW.timestamp())
    nonce = "nonce-signed-1"
    signature = build_resource_signature(
        issued.secret,
        method="POST",
        path="/agentos/v2/resources/edge-auth/observation",
        timestamp=timestamp,
        nonce=nonce,
        body=body,
    )
    authenticator = ResourceRequestAuthenticator(resources, clock_skew=timedelta(minutes=5))

    record = authenticator.authenticate(
        resource_id="edge-auth",
        credential_id=issued.credential_id,
        method="POST",
        path="/agentos/v2/resources/edge-auth/observation",
        timestamp=timestamp,
        nonce=nonce,
        signature=signature,
        body=body,
        now=NOW,
    )

    assert record.owner_scope == "tenant-a"


def test_signed_request_rejects_tampering_wrong_credential_and_replay() -> None:
    resources = _service()
    issued = resources.issue_credential("edge-auth")
    body = b'{"availableSlots":1}'
    timestamp = int(NOW.timestamp())
    authenticator = ResourceRequestAuthenticator(resources, clock_skew=timedelta(minutes=5))
    signature = build_resource_signature(
        issued.secret,
        method="POST",
        path="/agentos/v2/resources/edge-auth/observation",
        timestamp=timestamp,
        nonce="nonce-signed-2",
        body=body,
    )

    with pytest.raises(ValueError, match="signature"):
        authenticator.authenticate(
            resource_id="edge-auth",
            credential_id=issued.credential_id,
            method="POST",
            path="/agentos/v2/resources/edge-auth/observation",
            timestamp=timestamp,
            nonce="nonce-signed-2",
            signature=signature,
            body=b'{"availableSlots":0}',
            now=NOW,
        )
    with pytest.raises(ValueError, match="credential"):
        authenticator.authenticate(
            resource_id="edge-auth",
            credential_id="wrong",
            method="POST",
            path="/agentos/v2/resources/edge-auth/observation",
            timestamp=timestamp,
            nonce="nonce-signed-3",
            signature=signature,
            body=body,
            now=NOW,
        )
    authenticator.authenticate(
        resource_id="edge-auth",
        credential_id=issued.credential_id,
        method="POST",
        path="/agentos/v2/resources/edge-auth/observation",
        timestamp=timestamp,
        nonce="nonce-signed-4",
        signature=build_resource_signature(
            issued.secret,
            method="POST",
            path="/agentos/v2/resources/edge-auth/observation",
            timestamp=timestamp,
            nonce="nonce-signed-4",
            body=body,
        ),
        body=body,
        now=NOW,
    )
    with pytest.raises(ResourceRequestReplay):
        authenticator.authenticate(
            resource_id="edge-auth",
            credential_id=issued.credential_id,
            method="POST",
            path="/agentos/v2/resources/edge-auth/observation",
            timestamp=timestamp,
            nonce="nonce-signed-4",
            signature=build_resource_signature(
                issued.secret,
                method="POST",
                path="/agentos/v2/resources/edge-auth/observation",
                timestamp=timestamp,
                nonce="nonce-signed-4",
                body=body,
            ),
            body=body,
            now=NOW,
        )


def test_signed_request_rejects_expired_timestamp() -> None:
    resources = _service()
    issued = resources.issue_credential("edge-auth")
    timestamp = int((NOW - timedelta(minutes=6)).timestamp())
    body = b"{}"
    with pytest.raises(ResourceRequestExpired):
        ResourceRequestAuthenticator(resources, clock_skew=timedelta(minutes=5)).authenticate(
            resource_id="edge-auth",
            credential_id=issued.credential_id,
            method="POST",
            path="/agentos/v2/resources/edge-auth/observation",
            timestamp=timestamp,
            nonce="nonce-expired",
            signature=build_resource_signature(
                issued.secret,
                method="POST",
                path="/agentos/v2/resources/edge-auth/observation",
                timestamp=timestamp,
                nonce="nonce-expired",
                body=body,
            ),
            body=body,
            now=NOW,
        )
