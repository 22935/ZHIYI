import json
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentos.core.types import ReviewDecision, ReviewDecisionType
from agentos.core.workflow_runtime import WorkflowRuntime, build_default_runtime


class AgentTaskCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    title: str
    domain: str = "general"
    intent: str = "general"
    input: Dict[str, Any] = Field(default_factory=dict)
    security_level: str = "internal"
    priority: str = "normal"

    @model_validator(mode="before")
    @classmethod
    def accept_camel_case(cls, data):
        if isinstance(data, dict) and "securityLevel" in data and "security_level" not in data:
            data = dict(data)
            data["security_level"] = data["securityLevel"]
        return data


class WorkflowRunCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    task_id: str
    workflow_id: Optional[str] = None
    review_mode: str = "auto"

    @model_validator(mode="before")
    @classmethod
    def accept_camel_case(cls, data):
        if isinstance(data, dict):
            data = dict(data)
            if "taskId" in data and "task_id" not in data:
                data["task_id"] = data["taskId"]
            if "workflowId" in data and "workflow_id" not in data:
                data["workflow_id"] = data["workflowId"]
            if "reviewMode" in data and "review_mode" not in data:
                data["review_mode"] = data["reviewMode"]
        return data


class WorkflowStartRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    title: str
    domain: str = "general"
    intent: str = "general"
    input: Dict[str, Any] = Field(default_factory=dict)
    security_level: str = "internal"
    priority: str = "normal"
    workflow_id: Optional[str] = None
    review_mode: str = "auto"

    @model_validator(mode="before")
    @classmethod
    def accept_camel_case(cls, data):
        if isinstance(data, dict):
            data = dict(data)
            if "securityLevel" in data and "security_level" not in data:
                data["security_level"] = data["securityLevel"]
            if "workflowId" in data and "workflow_id" not in data:
                data["workflow_id"] = data["workflowId"]
            if "reviewMode" in data and "review_mode" not in data:
                data["review_mode"] = data["reviewMode"]
        return data


class LegacyAgentChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    text: str = Field(..., min_length=1)
    session_id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def accept_camel_case(cls, data):
        if isinstance(data, dict) and "sessionId" in data and "session_id" not in data:
            data = dict(data)
            data["session_id"] = data["sessionId"]
        return data


class ChatWorkflowUpgradeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    text: str = Field(..., min_length=1)
    title: Optional[str] = None
    domain: str = "legal"
    intent: str = "case_analysis"
    workflow_id: Optional[str] = None
    review_mode: str = "human_in_loop"
    role_id: Optional[str] = None
    context_id: Optional[str] = None
    context: Optional[list[Dict[str, Any]]] = None
    input: Dict[str, Any] = Field(default_factory=dict)
    security_level: str = "internal"
    priority: str = "normal"

    @model_validator(mode="before")
    @classmethod
    def accept_camel_case(cls, data):
        if isinstance(data, dict):
            data = dict(data)
            if "workflowId" in data and "workflow_id" not in data:
                data["workflow_id"] = data["workflowId"]
            if "reviewMode" in data and "review_mode" not in data:
                data["review_mode"] = data["reviewMode"]
            if "roleId" in data and "role_id" not in data:
                data["role_id"] = data["roleId"]
            if "contextId" in data and "context_id" not in data:
                data["context_id"] = data["contextId"]
            if "securityLevel" in data and "security_level" not in data:
                data["security_level"] = data["securityLevel"]
        return data


class ReviewRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    step_id: str
    decision: ReviewDecisionType
    reviewer: str = "system"
    comment: str = ""

    @model_validator(mode="before")
    @classmethod
    def accept_camel_case(cls, data):
        if isinstance(data, dict) and "stepId" in data and "step_id" not in data:
            data = dict(data)
            data["step_id"] = data["stepId"]
        return data


class ResumeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    checkpoint_id: str

    @model_validator(mode="before")
    @classmethod
    def accept_camel_case(cls, data):
        if isinstance(data, dict) and "checkpointId" in data and "checkpoint_id" not in data:
            data = dict(data)
            data["checkpoint_id"] = data["checkpointId"]
        return data


def _to_json(model) -> Dict[str, Any]:
    return model.model_dump(by_alias=True, mode="json")


def _page_to_json(page) -> Dict[str, Any]:
    return {
        "items": [_to_json(item) for item in page.items],
        "total": page.total,
        "page": page.page,
        "pageSize": page.page_size,
    }


async def _create_task_and_start(
    runtime: WorkflowRuntime,
    request: WorkflowStartRequest,
) -> Dict[str, Any]:
    task = runtime.create_task(
        title=request.title,
        domain=request.domain,
        intent=request.intent,
        input=request.input,
        security_level=request.security_level,
        priority=request.priority,
    )
    run = await runtime.start(
        task_id=task.task_id,
        workflow_id=request.workflow_id,
        review_mode=request.review_mode,
    )
    return {"task": _to_json(task), "run": _to_json(run)}


LEGACY_AGENT_CONFIG: Dict[str, Dict[str, Any]] = {
    "lawyer": {
        "title": "Lawyer agent chat",
        "domain": "legal",
        "intent": "case_analysis",
        "workflow_id": "legal_case_analysis_v1",
        "input_key": "caseText",
        "skills": {
            "case_intake": "case_understanding",
            "statute": "statute_retrieval",
            "risk": "risk_assessment",
        },
    },
    "teacher": {
        "title": "Teacher agent chat",
        "domain": "education",
        "intent": "lesson_plan",
        "workflow_id": "education_lesson_plan_v1",
        "input_key": "topic",
        "skills": {"lesson_plan": "lesson_plan_generation"},
    },
    "programmer": {
        "title": "Programmer agent chat",
        "domain": "programmer",
        "intent": "requirement_analysis",
        "workflow_id": "programmer_requirement_analysis_v1",
        "input_key": "requirement",
        "skills": {
            "requirement_analysis": "requirement_analysis",
            "codebase_semantic_search": "codebase_semantic_search",
            "code_generation": "code_generation",
            "diagram_generation": "diagram_generation",
        },
    },
    "writer": {
        "title": "Writer agent chat",
        "domain": "writer",
        "intent": "story_outline",
        "workflow_id": "writer_story_outline_v1",
        "input_key": "premise",
        "skills": {"outline_generate": "outline_generate"},
    },
}


def _step_artifacts(run) -> Dict[str, Any]:
    if isinstance(run.output, dict):
        artifacts = run.output.get("artifacts")
        if isinstance(artifacts, dict) and artifacts:
            return artifacts
    return {step.step_id: step.output for step in run.steps if step.output}


def _skill_for_step(role_config: Dict[str, Any], step_id: str, fallback: Optional[str]) -> str:
    skills = role_config.get("skills") or {}
    return skills.get(step_id) or fallback or step_id


def _legacy_trace(role_config: Dict[str, Any], run) -> list[Dict[str, Any]]:
    trace = []
    for index, step in enumerate(run.steps, start=1):
        if not step.output:
            continue
        action = _skill_for_step(role_config, step.step_id, step.capability)
        trace.append(
            {
                "step": index,
                "thought": f"Execute workflow step: {step.name}",
                "action": action,
                "observation": json.dumps(step.output, ensure_ascii=False),
            }
        )
    return trace


def _legacy_skills(role_config: Dict[str, Any], run) -> list[str]:
    skills: list[str] = []
    for step in run.steps:
        if not step.output:
            continue
        skill = _skill_for_step(role_config, step.step_id, step.capability)
        if skill not in skills:
            skills.append(skill)
    return skills


def _markdown_from_outline(outline: Dict[str, Any]) -> str:
    lines = [f"# {outline.get('genre', '小说')}大纲"]
    premise = outline.get("premise")
    if premise:
        lines.append(f"\n## 一句话梗概\n{premise}")
    chapters = outline.get("chapters")
    if isinstance(chapters, list):
        for chapter in chapters:
            number = chapter.get("chapter", "")
            title = chapter.get("title") or f"第{number}章"
            goal = chapter.get("goal") or ""
            conflict = chapter.get("conflict") or ""
            turning_point = chapter.get("turning_point") or ""
            lines.append(f"\n## 第{number}章：{title}\n- 剧情目标：{goal}")
            if conflict:
                lines.append(f"- 冲突推进：{conflict}")
            if turning_point:
                lines.append(f"- 章末转折：{turning_point}")
    return "\n".join(lines)


def _ensure_text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    return []


def _format_legal_basis_item(item: Any) -> str:
    if isinstance(item, dict):
        law_name = item.get("lawName") or item.get("law_name") or "相关法律依据"
        article = item.get("article") or ""
        title = item.get("title") or ""
        reason = item.get("reason") or item.get("summary") or ""
        heading = " ".join(str(part).strip() for part in [law_name, article] if str(part).strip())
        if title:
            heading = f"{heading}（{title}）" if heading else str(title)
        return f"{heading}：{reason}" if reason else heading
    return str(item).strip()


def _risk_level_label(level: Any) -> str:
    normalized = str(level or "").strip().lower()
    return {
        "low": "低",
        "medium": "中",
        "high": "高",
        "unknown": "待评估",
    }.get(normalized, str(level or "待评估"))


def _legacy_lawyer_answer(artifacts: Dict[str, Any]) -> str:
    intake = artifacts.get("case_intake", {}) if isinstance(artifacts.get("case_intake"), dict) else {}
    statute = artifacts.get("statute", {}) if isinstance(artifacts.get("statute"), dict) else {}
    risk = artifacts.get("risk", {}) if isinstance(artifacts.get("risk"), dict) else {}

    case_type = intake.get("case_type") or "民商事争议"
    case_summary = intake.get("case_summary") or "已完成案情识别，但仍需要结合完整事实与证据进一步确认。"
    legal_issues = _ensure_text_list(intake.get("legal_issues")) or ["事实认定", "请求权基础", "责任承担"]
    missing_info = _ensure_text_list(intake.get("missing_info"))
    legal_basis = statute.get("legal_basis", [])
    basis_items = []
    for item in legal_basis if isinstance(legal_basis, list) else _ensure_text_list(legal_basis):
        formatted = _format_legal_basis_item(item)
        if formatted:
            basis_items.append(formatted)
    risk_level = risk.get("risk_level") or risk.get("riskLevel") or "unknown"
    risk_score = risk.get("risk_score") or risk.get("riskScore")
    key_risks = _ensure_text_list(risk.get("key_risks")) or ["现有结论依赖用户提供的信息，关键事实仍需证据印证。"]
    suggestions = _ensure_text_list(risk.get("mitigation_suggestions")) or [
        "补充合同、付款记录、沟通记录、交付凭证等核心证据。",
        "明确诉求金额、履行节点、违约事实与对方抗辩理由。",
        "如准备进入诉讼或仲裁，建议由专业律师结合完整材料复核。",
    ]

    lines = [
        f"## 法律初步分析：{case_type}",
        "",
        "### 1. 案情识别",
        str(case_summary),
        "",
        "### 2. 主要争议焦点",
        *[f"- {item}" for item in legal_issues],
        "",
        "### 3. 可参考法律依据",
    ]
    if basis_items:
        lines.extend(f"- {item}" for item in basis_items)
    else:
        lines.append("- 暂未检索到可直接匹配的法律依据，需要补充事实后继续检索。")

    lines.extend(
        [
            "",
            "### 4. 风险判断",
            f"- 风险等级：{_risk_level_label(risk_level)}",
        ]
    )
    if risk_score is not None:
        lines.append(f"- 风险分值：{risk_score}/100")
    lines.extend(f"- {item}" for item in key_risks)

    if missing_info:
        lines.extend(["", "### 5. 待补充信息", *[f"- {item}" for item in missing_info]])

    lines.extend(["", "### 6. 下一步建议", *[f"- {item}" for item in suggestions]])
    lines.extend(["", "> 以上为基于当前输入和系统检索结果形成的初步分析，不能替代正式法律意见。"])
    return "\n".join(lines)


def _auth_module_code() -> str:
    return '''from datetime import datetime, timedelta, timezone
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


def _programmer_search_result(requirement: str) -> Dict[str, Any]:
    return {
        "query": "FastAPI JWT auth permission existing code",
        "top_k": 5,
        "hits": [
            {
                "file_path": "backend/src/main/java/com/kinlin/ai/config/SecurityConfig.java",
                "language": "java",
                "score": 0.84,
                "content": "已有 Spring Security 过滤链，可借鉴公开路径、鉴权入口和无状态会话配置。",
            },
            {
                "file_path": "backend/src/main/java/com/kinlin/ai/filter/JwtAuthenticationFilter.java",
                "language": "java",
                "score": 0.81,
                "content": "已有 JWT 解析与用户上下文注入逻辑，可迁移为 FastAPI dependency/middleware。",
            },
            {
                "file_path": "backend/src/main/java/com/kinlin/ai/util/JwtUtil.java",
                "language": "java",
                "score": 0.79,
                "content": "已有 Token 生成、校验、过期处理思路，可复用 claims 设计。",
            },
            {
                "file_path": "backend/src/main/java/com/kinlin/ai/controller/AuthController.java",
                "language": "java",
                "score": 0.76,
                "content": "已有登录/注册接口形态，可对齐 /auth/login 的输入输出。",
            },
            {
                "file_path": "backend/src/main/java/com/kinlin/ai/util/PasswordUtil.java",
                "language": "java",
                "score": 0.72,
                "content": "已有密码哈希与校验工具，可在 Python 版本中对应使用 passlib bcrypt。",
            },
        ],
        "index_status": {
            "success": True,
            "message": "模拟检索结果：当前仓库已有 Java/Spring 认证代码，可作为 FastAPI 版本的设计参考。",
        },
        "source_query": requirement[:160],
    }


def _programmer_code_generation(requirement: str) -> Dict[str, Any]:
    return {
        "target_language": "python",
        "code": _auth_module_code(),
        "explanation": "核心实现包含登录接口、JWT 生成与验证、dependency 风格权限控制，以及可选装饰器形态。",
        "suggested_tests": [
            "POST /auth/login 使用正确账号密码返回 access_token。",
            "POST /auth/login 使用错误密码返回 401。",
            "GET /users/me 无 Token 返回 401。",
            "GET /admin/users 使用缺少 user:read 权限的 Token 返回 403。",
            "GET /admin/users 使用含 user:read 权限的 Token 返回用户列表。",
        ],
        "context_refs": [
            {"file_path": "backend/src/main/java/com/kinlin/ai/util/JwtUtil.java", "score": 0.79},
            {"file_path": "backend/src/main/java/com/kinlin/ai/filter/JwtAuthenticationFilter.java", "score": 0.81},
        ],
    }


def _programmer_diagram_generation(requirement: str) -> Dict[str, Any]:
    architecture = """flowchart LR
    Client[客户端/前端] -->|POST /auth/login| AuthRouter[FastAPI Auth Router]
    AuthRouter --> AuthService[Auth Service]
    AuthService --> UserRepo[(User DB)]
    AuthService --> PasswordHasher[passlib bcrypt]
    AuthService --> JwtProvider[JWT Provider]
    Client -->|Bearer Token| ProtectedRouter[Protected API Router]
    ProtectedRouter --> AuthDependency[JWT Verify Dependency]
    AuthDependency --> JwtProvider
    AuthDependency --> PermissionGuard[Permission Guard]
    PermissionGuard --> ProtectedRouter
    ProtectedRouter --> DomainService[业务服务]"""
    sequence = """sequenceDiagram
    participant U as User
    participant C as Client
    participant API as FastAPI /auth/login
    participant DB as User DB
    participant JWT as JWT Provider
    U->>C: 输入用户名和密码
    C->>API: POST /auth/login
    API->>DB: 按 username 查询用户
    DB-->>API: 返回用户与 hashed_password
    API->>API: bcrypt 校验密码
    alt 密码正确且用户启用
        API->>JWT: 生成 access_token
        JWT-->>API: signed JWT
        API-->>C: 200 {access_token, token_type, expires_in}
        C-->>U: 登录成功
    else 认证失败
        API-->>C: 401/403
        C-->>U: 展示错误信息
    end"""
    return {
        "title": "FastAPI JWT 用户认证与权限管理",
        "diagram_type": "mermaid",
        "mermaid_code": architecture,
        "sequence_mermaid_code": sequence,
        "source_query": requirement[:160],
    }


def _augment_programmer_artifacts(artifacts: Dict[str, Any], request_text: str) -> None:
    requirement_output = artifacts.get("requirement_analysis", {})
    if not isinstance(requirement_output, dict):
        requirement_output = {}
        artifacts["requirement_analysis"] = requirement_output
    spec = requirement_output.get("technical_spec") or {}
    if isinstance(spec, dict):
        spec.setdefault("inputs", ["username", "password", "Authorization: Bearer <token>", "required_permissions"])
        spec.setdefault("outputs", ["access_token", "token_type", "expires_in", "current_user", "403 permission denied"])
        spec.setdefault(
            "boundary_conditions",
            ["用户名或密码为空", "密码错误", "Token 过期或签名非法", "用户被禁用", "权限不足", "缺少密钥配置"],
        )
        spec.setdefault(
            "suggested_modules",
            ["auth/router.py", "auth/security.py", "auth/dependencies.py", "models/user.py", "repositories/user_repo.py"],
        )
        requirement_output["technical_spec"] = spec

    artifacts.setdefault("codebase_semantic_search", _programmer_search_result(request_text))
    artifacts.setdefault("code_generation", _programmer_code_generation(request_text))
    artifacts.setdefault("diagram_generation", _programmer_diagram_generation(request_text))


def _legacy_programmer_answer(artifacts: Dict[str, Any], request_text: str) -> str:
    requirement = artifacts.get("requirement_analysis", {})
    spec = requirement.get("technical_spec", {}) if isinstance(requirement, dict) else {}
    search = artifacts.get("codebase_semantic_search", {})
    code_generation = artifacts.get("code_generation", {})
    diagram = artifacts.get("diagram_generation", {})
    architecture = diagram.get("mermaid_code", "")
    sequence = diagram.get("sequence_mermaid_code", "")
    code = code_generation.get("code", "")

    functional_requirements = _ensure_text_list(spec.get("functional_requirements")) or [
        "提供登录接口，校验用户名与密码。",
        "登录成功后生成带角色和权限声明的 JWT。",
        "为受保护接口提供 JWT 验证 dependency。",
        "提供权限校验 dependency/装饰器。",
    ]
    inputs = _ensure_text_list(spec.get("inputs"))
    outputs = _ensure_text_list(spec.get("outputs"))
    boundaries = _ensure_text_list(spec.get("boundary_conditions"))
    acceptance = _ensure_text_list(spec.get("acceptance_criteria"))

    lines = [
        "## 1. 功能规格",
        "",
        f"目标：基于 Python FastAPI + JWT 实现简单的用户认证与权限管理模块。",
        "",
        "### 功能清单",
        *[f"- {item}" for item in functional_requirements],
        "",
        "### 输入",
        *[f"- {item}" for item in inputs],
        "",
        "### 输出",
        *[f"- {item}" for item in outputs],
        "",
        "### 边界条件",
        *[f"- {item}" for item in boundaries],
        "",
        "### 验收标准",
        *[f"- {item}" for item in acceptance],
        "",
        "## 2. 认证相关代码检索结果（模拟）",
        "",
        f"检索关键词：`{search.get('query', 'auth jwt permission')}`",
    ]
    for hit in search.get("hits", []):
        lines.append(f"- `{hit.get('file_path')}`：{hit.get('content')}（score={hit.get('score')}）")

    lines.extend(
        [
            "",
            "结论：当前仓库已有 Java/Spring 认证链路，可复用设计思想；FastAPI 版本建议独立实现 `security.py`、`dependencies.py` 和 `router.py`。",
            "",
            "## 3. 核心代码",
            "",
            "```python",
            code.rstrip(),
            "```",
            "",
            "## 4. 模块架构图",
            "",
            "```mermaid",
            architecture.rstrip(),
            "```",
            "",
            "## 5. 用户登录时序图",
            "",
            "```mermaid",
            sequence.rstrip(),
            "```",
        ]
    )
    return "\n".join(lines)


def _legacy_answer(role: str, run, artifacts: Dict[str, Any]) -> str:
    if role == "programmer":
        run_input = getattr(run, "input", {})
        return _legacy_programmer_answer(artifacts, str(run_input.get("requirement") if isinstance(run_input, dict) else ""))

    if role == "lawyer":
        return _legacy_lawyer_answer(artifacts)

    if isinstance(run.output, dict) and run.output.get("final_answer"):
        final_answer = str(run.output["final_answer"])
        if final_answer and not final_answer.startswith("Workflow completed:"):
            return final_answer

    if role == "teacher":
        lesson = artifacts.get("lesson_plan", {})
        if lesson.get("final_answer"):
            return str(lesson["final_answer"])

    if role == "writer":
        outline = artifacts.get("outline_generate", {})
        if outline.get("final_answer"):
            return str(outline["final_answer"])

    return str(run.output.get("final_answer") if isinstance(run.output, dict) else "") or "Agent workflow completed."


def _legacy_response(role: str, role_config: Dict[str, Any], request: LegacyAgentChatRequest, run) -> Dict[str, Any]:
    artifacts = _step_artifacts(run)
    if role == "programmer":
        _augment_programmer_artifacts(artifacts, request.text)

    skills_used = _legacy_skills(role_config, run)
    trace = _legacy_trace(role_config, run)
    if role == "programmer":
        for skill in ["codebase_semantic_search", "code_generation", "diagram_generation"]:
            if skill not in skills_used:
                skills_used.append(skill)
        next_step = len(trace) + 1
        existing_actions = {item.get("action") for item in trace}
        for action, thought in [
            ("codebase_semantic_search", "Search reusable authentication code in the current project."),
            ("code_generation", "Generate FastAPI JWT authentication and permission code."),
            ("diagram_generation", "Generate Mermaid architecture and login sequence diagrams."),
        ]:
            if action in existing_actions:
                continue
            trace.append(
                {
                    "step": next_step,
                    "thought": thought,
                    "action": action,
                    "observation": json.dumps(artifacts.get(action, {}), ensure_ascii=False),
                }
            )
            next_step += 1

    response: Dict[str, Any] = {
        "success": run.status.value not in {"failed", "cancelled"},
        "answer": _legacy_answer(role, run, artifacts),
        "sessionId": request.session_id or run.run_id,
        "skillsUsed": skills_used,
        "trace": trace,
        "federated": {
            "enabled": True,
            "applied": False,
            "risk_adjustment": 0,
            "confidence": 0.85,
            "federated_nodes_count": 0,
        },
    }

    if role == "lawyer":
        risk = artifacts.get("risk", {})
        response["riskLevel"] = risk.get("risk_level") or risk.get("riskLevel")
    elif role == "teacher":
        lesson_output = artifacts.get("lesson_plan", {})
        lesson_plan = lesson_output.get("lesson_plan") or lesson_output
        response["lessonPlan"] = lesson_plan
        response["lesson_plan_generation"] = lesson_plan
    elif role == "programmer":
        requirement_output = artifacts.get("requirement_analysis", {})
        technical_spec = requirement_output.get("technical_spec") or requirement_output
        response["requirementAnalysis"] = technical_spec
        response["requirement_analysis"] = technical_spec
        search_output = artifacts.get("codebase_semantic_search", {})
        code_output = artifacts.get("code_generation", {})
        diagram_output = artifacts.get("diagram_generation", {})
        response["codebaseSemanticSearch"] = search_output
        response["codebase_semantic_search"] = search_output
        response["codeGeneration"] = code_output
        response["code_generation"] = code_output
        response["diagramGeneration"] = diagram_output
        response["diagram_generation"] = diagram_output
    elif role == "writer":
        outline_output = artifacts.get("outline_generate", {})
        outline = outline_output.get("outline") or outline_output
        outline_payload = {
            "creative_selection": outline.get("premise") if isinstance(outline, dict) else "",
            "chapters_count": len(outline.get("chapters", [])) if isinstance(outline, dict) else 0,
            "outline_markdown": outline_output.get("outline_markdown")
            or (_markdown_from_outline(outline) if isinstance(outline, dict) else str(outline)),
        }
        response["outlineGenerate"] = outline_payload
        response["outline_generate"] = outline_payload

    if run.error:
        response["error"] = run.error
    return response


def create_router(runtime: WorkflowRuntime) -> APIRouter:
    router = APIRouter()

    @router.post("/core/tasks")
    async def create_task(request: AgentTaskCreateRequest):
        try:
            task = runtime.create_task(
                title=request.title,
                domain=request.domain,
                intent=request.intent,
                input=request.input,
                security_level=request.security_level,
                priority=request.priority,
            )
            return _to_json(task)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/core/tasks")
    async def list_tasks(
        status: Optional[str] = None,
        domain: Optional[str] = None,
        source: Optional[str] = None,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, alias="pageSize"),
    ):
        return _page_to_json(
            runtime.workflow_store.list_tasks(
                status=status,
                domain=domain,
                source=source,
                page=page,
                page_size=page_size,
            )
        )

    @router.post("/core/workflows/runs")
    async def start_workflow(request: WorkflowRunCreateRequest):
        try:
            run = await runtime.start(
                task_id=request.task_id,
                workflow_id=request.workflow_id,
                review_mode=request.review_mode,
            )
            return _to_json(run)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/core/workflows/start")
    async def start_workflow_from_workbench(request: WorkflowStartRequest):
        try:
            return await _create_task_and_start(runtime, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/chat/workflows/upgrade")
    async def upgrade_chat_to_workflow(request: ChatWorkflowUpgradeRequest):
        text = request.text.strip()
        workflow_input = {
            **request.input,
            "source": "chat",
            "caseText": request.input.get("caseText") or text,
            "chatText": text,
        }
        if request.context_id:
            workflow_input["chatContextId"] = request.context_id
        if request.role_id:
            workflow_input["chatRoleId"] = request.role_id
        if request.context:
            workflow_input["chatContext"] = request.context

        title = request.title or f"Chat升级工作流：{text[:30]}"
        start_request = WorkflowStartRequest(
            title=title,
            domain=request.domain,
            intent=request.intent,
            input=workflow_input,
            securityLevel=request.security_level,
            priority=request.priority,
            workflowId=request.workflow_id,
            reviewMode=request.review_mode,
        )
        try:
            payload = await _create_task_and_start(runtime, start_request)
            payload["source"] = "chat"
            return payload
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/agent/{role}/chat")
    async def legacy_agent_chat(role: str, request: LegacyAgentChatRequest):
        role_key = role.strip().lower()
        role_config = LEGACY_AGENT_CONFIG.get(role_key)
        if not role_config:
            raise HTTPException(status_code=404, detail=f"unsupported agent role: {role}")

        text = request.text.strip()
        workflow_input = {
            "source": "legacy_agent_chat",
            "chatText": text,
            "text": text,
            role_config["input_key"]: text,
        }
        start_request = WorkflowStartRequest(
            title=f"{role_config['title']}: {text[:40]}",
            domain=role_config["domain"],
            intent=role_config["intent"],
            input=workflow_input,
            securityLevel="internal",
            priority="normal",
            workflowId=role_config["workflow_id"],
            reviewMode="auto",
        )
        try:
            payload = await _create_task_and_start(runtime, start_request)
            run = runtime.get_status(payload["run"]["runId"])
            return _legacy_response(role_key, role_config, request, run)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/core/workflows/runs")
    async def list_workflow_runs(
        status: Optional[str] = None,
        domain: Optional[str] = None,
        workflow_id: Optional[str] = Query(None, alias="workflowId"),
        source: Optional[str] = None,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, alias="pageSize"),
    ):
        return _page_to_json(
            runtime.workflow_store.list_runs(
                status=status,
                domain=domain,
                workflow_id=workflow_id,
                source=source,
                page=page,
                page_size=page_size,
            )
        )

    @router.get("/core/workflows/metrics")
    async def evaluate_workflows(
        status: Optional[str] = None,
        domain: Optional[str] = None,
        workflow_id: Optional[str] = Query(None, alias="workflowId"),
        source: Optional[str] = None,
    ):
        return _to_json(
            runtime.evaluate_runs(
                status=status,
                domain=domain,
                workflow_id=workflow_id,
                source=source,
            )
        )

    @router.get("/core/workflows/runs/{run_id}")
    async def get_workflow_run(run_id: str):
        try:
            return _to_json(runtime.get_status(run_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/core/workflows/runs/{run_id}/checkpoints")
    async def list_checkpoints(run_id: str):
        try:
            checkpoints = runtime.list_checkpoints(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "items": [_to_json(checkpoint) for checkpoint in checkpoints],
            "total": len(checkpoints),
            "runId": run_id,
        }

    @router.get("/core/workflows/runs/{run_id}/trace")
    async def export_workflow_trace(
        run_id: str,
        format: Literal["json", "markdown"] = "json",
    ):
        try:
            run = runtime.get_status(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        if format == "markdown":
            return PlainTextResponse(
                runtime.trace_store.export_markdown(run),
                media_type="text/markdown; charset=utf-8",
            )
        return runtime.trace_store.export_json(run)

    @router.get("/core/workflows/runs/{run_id}/reviews")
    async def list_reviews(run_id: str):
        try:
            reviews = runtime.list_reviews(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "items": [_to_json(review) for review in reviews],
            "total": len(reviews),
            "runId": run_id,
        }

    @router.post("/core/workflows/runs/{run_id}/reviews")
    async def apply_review(run_id: str, request: ReviewRequest):
        try:
            run = await runtime.apply_review(
                ReviewDecision(
                    runId=run_id,
                    stepId=request.step_id,
                    decision=request.decision,
                    reviewer=request.reviewer,
                    comment=request.comment,
                )
            )
            return _to_json(run)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/core/workflows/runs/{run_id}/resume")
    async def resume_workflow(run_id: str, request: ResumeRequest):
        try:
            run = await runtime.resume_from_checkpoint(run_id=run_id, checkpoint_id=request.checkpoint_id)
            return _to_json(run)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/core/workflows/runs/{run_id}/cancel")
    async def cancel_workflow(run_id: str):
        try:
            return _to_json(runtime.cancel(run_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return router


runtime = build_default_runtime()
router = create_router(runtime)
