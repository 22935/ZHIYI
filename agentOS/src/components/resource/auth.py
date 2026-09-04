"""Resource-level request signing for remote edge/cloud nodes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac

from .service import ResourceService
from .store import ResourceCredentialRecord


class ResourceRequestExpired(ValueError):
    """The signed request timestamp is outside the accepted clock skew."""


class ResourceRequestReplay(ValueError):
    """The signed request nonce has already been consumed."""


class ResourceRequestNotFound(ValueError):
    """The request names an unknown resource."""


class ResourceRequestInvalid(ValueError):
    """The credential or signature does not match the named resource."""


def _canonical_request(
    *, method: str, path: str, timestamp: int, nonce: str, body: bytes
) -> bytes:
    body_digest = hashlib.sha256(body).hexdigest()
    return "\n".join(
        (method.upper(), path, str(timestamp), nonce, body_digest)
    ).encode("utf-8")


def build_resource_signature(
    secret: str,
    *,
    method: str,
    path: str,
    timestamp: int,
    nonce: str,
    body: bytes,
) -> str:
    """Build the hex HMAC signature used by a registered resource node.

    The client derives its HMAC key from the one-time registration secret. The
    server stores only this derived SHA-256 digest, so a database dump does not
    reveal the registration secret itself.
    """
    key = hashlib.sha256(secret.encode("utf-8")).digest()
    return hmac.new(
        key,
        _canonical_request(
            method=method,
            path=path,
            timestamp=timestamp,
            nonce=nonce,
            body=body,
        ),
        hashlib.sha256,
    ).hexdigest()


class ResourceRequestAuthenticator:
    """Verify identity, freshness, integrity, and replay protection."""

    def __init__(
        self,
        resource_service: ResourceService,
        *,
        clock_skew: timedelta = timedelta(minutes=5),
    ) -> None:
        if clock_skew <= timedelta(0):
            raise ValueError("clock skew must be positive")
        self.resource_service = resource_service
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
            record = self.resource_service.credential(resource_id)
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

        expected = hmac.new(
            self.resource_service.credential_hmac_key(resource_id, credential_id),
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
        if not self.resource_service.consume_nonce(
            resource_id, nonce, expires_at, now=current
        ):
            raise ResourceRequestReplay("resource request nonce was already used")
        return record
