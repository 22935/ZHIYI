"""Pure standard-library signing primitives shared by AgentOS and Local Runtime."""

from __future__ import annotations

import hashlib
import hmac


def canonical_resource_request(
    *, method: str, path: str, timestamp: int, nonce: str, body: bytes
) -> bytes:
    body_digest = hashlib.sha256(body).hexdigest()
    return "\n".join((method.upper(), path, str(timestamp), nonce, body_digest)).encode("utf-8")


def build_resource_signature(
    secret: str,
    *,
    method: str,
    path: str,
    timestamp: int,
    nonce: str,
    body: bytes,
) -> str:
    key = hashlib.sha256(secret.encode("utf-8")).digest()
    return hmac.new(
        key,
        canonical_resource_request(
            method=method,
            path=path,
            timestamp=timestamp,
            nonce=nonce,
            body=body,
        ),
        hashlib.sha256,
    ).hexdigest()


__all__ = ["build_resource_signature", "canonical_resource_request"]
