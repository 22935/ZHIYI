"""Small stdlib-only HTTP helpers for the real edge/cloud demo."""

from __future__ import annotations

import hashlib
import hmac
import json
from http.server import BaseHTTPRequestHandler
from time import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def canonical_signature(
    secret: str,
    *,
    method: str,
    path: str,
    timestamp: int,
    nonce: str,
    body: bytes,
) -> str:
    key = hashlib.sha256(secret.encode("utf-8")).digest()
    canonical = "\n".join(
        (method.upper(), path, str(timestamp), nonce, hashlib.sha256(body).hexdigest())
    ).encode("utf-8")
    return hmac.new(key, canonical, hashlib.sha256).hexdigest()


def signed_json_request(
    url: str,
    *,
    credential_id: str,
    secret: str,
    payload: dict,
) -> tuple[int, dict]:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    timestamp = int(time())
    nonce = hashlib.sha256(f"{timestamp}:{id(body)}".encode()).hexdigest()[:32]
    request = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Resource-Credential": credential_id,
            "X-Resource-Timestamp": str(timestamp),
            "X-Resource-Nonce": nonce,
            "X-Resource-Signature": canonical_signature(
                secret,
                method="POST",
                path=urlsplit_path(url),
                timestamp=timestamp,
                nonce=nonce,
                body=body,
            ),
        },
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        try:
            body = json.loads(error.read())
        except Exception:
            body = {"error": str(error)}
        return error.code, body
    except URLError as error:
        return 503, {"error": str(error.reason)}


def urlsplit_path(url: str) -> str:
    from urllib.parse import urlsplit

    return urlsplit(url).path or "/"


def read_json(handler: BaseHTTPRequestHandler) -> dict:
    size = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(size)
    value = json.loads(raw or b"{}")
    if not isinstance(value, dict):
        raise ValueError("request JSON must be an object")
    return value


def write_json(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def verify_signed_headers(
    handler: BaseHTTPRequestHandler,
    *,
    credential_id: str,
    secret: str,
    body: bytes,
    consumed_nonces: set[str],
) -> tuple[bool, str]:
    supplied_credential = handler.headers.get("X-Resource-Credential", "")
    timestamp_text = handler.headers.get("X-Resource-Timestamp", "")
    nonce = handler.headers.get("X-Resource-Nonce", "")
    signature = handler.headers.get("X-Resource-Signature", "")
    if not all((supplied_credential, timestamp_text, nonce, signature)):
        return False, "missing signature headers"
    if supplied_credential != credential_id:
        return False, "credential mismatch"
    try:
        timestamp = int(timestamp_text)
    except ValueError:
        return False, "invalid timestamp"
    if abs(int(time()) - timestamp) > 300:
        return False, "expired timestamp"
    if nonce in consumed_nonces:
        return False, "replayed nonce"
    expected = canonical_signature(
        secret,
        method=handler.command,
        path=handler.path.split("?", 1)[0],
        timestamp=timestamp,
        nonce=nonce,
        body=body,
    )
    if not hmac.compare_digest(expected, signature):
        return False, "invalid signature"
    consumed_nonces.add(nonce)
    return True, "ok"
