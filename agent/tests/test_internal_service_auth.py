from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.security.internal_auth import (
    INTERNAL_SERVICE_TOKEN_HEADER,
    InternalServiceAuthMiddleware,
    current_trusted_user,
    require_valid_internal_token_configuration,
)


TOKEN = "0123456789abcdef0123456789abcdef"
HEADER = INTERNAL_SERVICE_TOKEN_HEADER.decode("ascii")
IDENTITY_HEADERS = {
    "X-Authenticated-User-Id": "11111111-1111-1111-1111-111111111111",
    "X-Authenticated-User-Subject": "p2-user",
    "X-Authenticated-User-Role": "USER",
}


def _client() -> TestClient:
    app = FastAPI()
    app.add_middleware(InternalServiceAuthMiddleware, token=TOKEN)

    @app.get("/health/live")
    async def live():
        return {"status": "UP"}

    @app.post("/ai/chat/text")
    async def business():
        actor = current_trusted_user()
        return {"ok": True, "userId": actor.user_id if actor else None}

    return TestClient(app)


def test_correct_token_allows_business_route():
    response = _client().post("/ai/chat/text", headers={HEADER: TOKEN, **IDENTITY_HEADERS})
    assert response.status_code == 200
    assert response.json()["userId"] == IDENTITY_HEADERS["X-Authenticated-User-Id"]


def test_missing_wrong_empty_and_duplicate_tokens_are_rejected():
    client = _client()
    assert client.post("/ai/chat/text").status_code == 401
    assert client.post("/ai/chat/text", headers={HEADER: "x" * 32}).status_code == 403
    assert client.post("/ai/chat/text", headers={HEADER: ""}).status_code == 403
    duplicate = client.post("/ai/chat/text", headers=[(HEADER, TOKEN), (HEADER, TOKEN)])
    assert duplicate.status_code == 403
    assert duplicate.json() == {"detail": "access denied"}


def test_valid_service_token_without_trusted_user_is_rejected():
    assert _client().post("/ai/chat/text", headers={HEADER: TOKEN}).status_code == 403


def test_client_identity_without_service_token_is_rejected():
    response = _client().post("/ai/chat/text", headers=IDENTITY_HEADERS)
    assert response.status_code == 401


def test_health_endpoint_does_not_require_internal_token():
    assert _client().get("/health/live").status_code == 200


def test_invalid_production_configuration_fails_without_echoing_value():
    try:
        require_valid_internal_token_configuration("too-short")
    except RuntimeError as error:
        assert str(error) == "internal service authentication is missing or invalid"
        assert "too-short" not in str(error)
    else:
        raise AssertionError("invalid token was accepted")
