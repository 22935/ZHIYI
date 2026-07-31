from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.sse_test import router
from app.middleware.trace import TraceIdMiddleware
from app.security.internal_auth import INTERNAL_SERVICE_TOKEN_HEADER, InternalServiceAuthMiddleware


TOKEN = "0123456789abcdef0123456789abcdef"
HEADERS = {
    INTERNAL_SERVICE_TOKEN_HEADER.decode("ascii"): TOKEN,
    "X-Authenticated-User-Id": "11111111-1111-4111-8111-111111111111",
    "X-Authenticated-User-Subject": "p2-user",
    "X-Authenticated-User-Role": "USER",
}


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/ai")
    app.add_middleware(InternalServiceAuthMiddleware, token=TOKEN)
    app.add_middleware(TraceIdMiddleware)
    return TestClient(app)


def test_proxy_provider_preserves_supported_status_and_method():
    client = _client()
    for status in (200, 400, 401, 403, 404, 409, 422, 500):
        response = client.post(f"/ai/test/proxy/{status}", headers=HEADERS)
        assert response.status_code == status
        assert response.json()["method"] == "POST"
        assert response.json()["trace_id"] == response.headers["X-Trace-Id"]
        assert response.json()["user_id"] == HEADERS["X-Authenticated-User-Id"]
        assert response.json()["role"] == "USER"


def test_proxy_provider_remains_internal_and_rejects_unknown_status():
    client = _client()
    assert client.get("/ai/test/proxy/200").status_code == 401
    assert client.get("/ai/test/proxy/418", headers=HEADERS).status_code == 400
