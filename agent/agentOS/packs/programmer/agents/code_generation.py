from agentos.agents.base import AgentOutput, AgentProfile, BaseAgent


AUTH_MODULE_CODE = '''from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field

SECRET_KEY = "replace-with-env-secret"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

app = FastAPI(title="Auth and Permission API")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserInDB(BaseModel):
    id: str
    username: str
    hashed_password: str
    roles: list[str] = []
    permissions: list[str] = []
    disabled: bool = False


fake_users_db = {
    "admin": UserInDB(
        id="u_001",
        username="admin",
        hashed_password=password_context.hash("admin12345"),
        roles=["admin"],
        permissions=["user:read", "user:write", "role:manage"],
    )
}


def verify_password(raw_password: str, hashed_password: str) -> bool:
    return password_context.verify(raw_password, hashed_password)


def authenticate_user(username: str, password: str) -> UserInDB:
    user = fake_users_db.get(username)
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.disabled:
        raise HTTPException(status_code=403, detail="用户已禁用")
    return user


def create_access_token(user: UserInDB) -> str:
    expire_at = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user.id,
        "username": user.username,
        "roles": user.roles,
        "permissions": user.permissions,
        "exp": expire_at,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_jwt_token(token: Annotated[str, Depends(oauth2_scheme)]) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if not payload.get("sub"):
            raise HTTPException(status_code=401, detail="无效 Token")
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def require_permissions(*required_permissions: str):
    def dependency(payload: Annotated[dict, Depends(verify_jwt_token)]) -> dict:
        permissions = set(payload.get("permissions", []))
        if not set(required_permissions).issubset(permissions):
            raise HTTPException(status_code=403, detail="权限不足")
        return payload
    return dependency


def permission_required(*required_permissions: str):
    def outer(func):
        @wraps(func)
        async def inner(*args, payload: Annotated[dict, Depends(verify_jwt_token)], **kwargs):
            permissions = set(payload.get("permissions", []))
            if not set(required_permissions).issubset(permissions):
                raise HTTPException(status_code=403, detail="权限不足")
            return await func(*args, payload=payload, **kwargs)
        return inner
    return outer


@app.post("/auth/login", response_model=TokenResponse)
def login(request: LoginRequest):
    user = authenticate_user(request.username, request.password)
    token = create_access_token(user)
    return TokenResponse(access_token=token, expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60)


@app.get("/users/me")
def read_current_user(payload: Annotated[dict, Depends(verify_jwt_token)]):
    return {
        "user_id": payload["sub"],
        "username": payload["username"],
        "roles": payload.get("roles", []),
        "permissions": payload.get("permissions", []),
    }


@app.get("/admin/users")
def list_users(payload: Annotated[dict, Depends(require_permissions("user:read"))]):
    return {"items": [{"id": user.id, "username": user.username} for user in fake_users_db.values()]}
'''


class CodeGenerationAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            AgentProfile(
                agentName="code_generation",
                domain="programmer",
                capabilities=["code_generation"],
                allowedSkills=["code_generation"],
                description="Generates implementation code from programmer workflow artifacts.",
            )
        )

    async def run(self, context):
        search_payload = context.memory.observations.get("codebase_semantic_search", {})
        context_refs = [
            {"file_path": item.get("file_path"), "score": item.get("score")}
            for item in search_payload.get("hits", [])[:3]
            if isinstance(item, dict)
        ]
        return AgentOutput(
            output={
                "target_language": "python",
                "code": AUTH_MODULE_CODE,
                "explanation": "核心实现包含登录接口、JWT 生成与验证、dependency 风格权限控制，以及可选装饰器形态。",
                "suggested_tests": [
                    "POST /auth/login 使用正确账号密码返回 access_token。",
                    "POST /auth/login 使用错误密码返回 401。",
                    "GET /users/me 无 Token 返回 401。",
                    "GET /admin/users 使用缺少 user:read 权限的 Token 返回 403。",
                    "GET /admin/users 使用含 user:read 权限的 Token 返回用户列表。",
                ],
                "context_refs": context_refs,
            },
            summary="Code generation completed.",
        )
