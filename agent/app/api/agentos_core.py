"""AgentOS Core 的 FastAPI 路由层，负责任务创建、工作流启动、状态查询、审核、恢复和兼容聊天入口。"""


import hashlib
import json
import uuid
import logging
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentos.core.execution import RunExecutionCoordinator
from agentos.core.models.types import ReviewDecision, ReviewDecisionType, WorkflowRun, WorkflowStatus
from agentos.core.plugin_scope import PluginScopeError
from agentos.core.runtime import ReviewConflictError, WorkflowRuntime
from agentos.core.workflow.progress import ProgressAssembler
from agentos.stores.workflow_store import WorkflowRunNotTerminalError
from app.execution.runtime import build_default_runtime
from app.llm.gateway import get_llm_gateway
from app.llm.schemas import CHAT_ROUTE_DECISION_SCHEMA
from app.security.internal_auth import current_trusted_user
from app.observability.context import execution_context
from app.services.taskmaterialservice import (
    MaterialError,
    extract_material,
    task_material_store,
)

logger = logging.getLogger(__name__)


class IdempotencyConflictError(ValueError):
    pass


def _input_with_authenticated_actor(payload: Dict[str, Any]) -> Dict[str, Any]:
    actor = current_trusted_user()
    if actor is None:
        return payload
    authenticated = {
        **payload,
        "authenticatedUserId": actor.user_id,
        "authenticatedSubject": actor.subject,
        "authenticatedRole": actor.role,
    }
    if actor.tenant_id:
        authenticated["authenticatedTenantId"] = actor.tenant_id
    return authenticated


class AgentTaskCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    title: str
    domain: str = "general"
    intent: str = "general"
    role_type: Optional[str] = None
    task_type: Optional[str] = None
    input: Dict[str, Any] = Field(default_factory=dict)
    security_level: str = "internal"
    priority: str = "normal"

    enabled_plugin_ids: Optional[list[str]] = Field(
        default=None, alias="enabledPluginIds"
    )
    planning_diversity: Optional[Literal["stable", "balanced", "exploratory"]] = Field(
        default=None, alias="planningDiversity"
    )
    planning_seed: Optional[int] = Field(
        default=None, alias="planningSeed", ge=0, le=2**53 - 1
    )

    @model_validator(mode="before")
    @classmethod
    def accept_camel_case(cls, data):
        if isinstance(data, dict):
            data = dict(data)
            if "securityLevel" in data and "security_level" not in data:
                data["security_level"] = data["securityLevel"]
            if "roleType" in data and "role_type" not in data:
                data["role_type"] = data["roleType"]
            if "taskType" in data and "task_type" not in data:
                data["task_type"] = data["taskType"]
        return data


class WorkflowRunCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    task_id: str
    workflow_id: Optional[str] = None
    review_mode: str = "auto"
    enabled_plugin_ids: Optional[list[str]] = Field(
        default=None, alias="enabledPluginIds"
    )

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
    role_type: Optional[str] = None
    task_type: Optional[str] = None
    input: Dict[str, Any] = Field(default_factory=dict)
    security_level: str = "internal"
    priority: str = "normal"
    workflow_id: Optional[str] = None
    review_mode: str = "auto"
    client_request_id: Optional[str] = Field(default=None, alias="clientRequestId")
    enabled_plugin_ids: Optional[list[str]] = Field(
        default=None, alias="enabledPluginIds"
    )
    planning_diversity: Optional[Literal["stable", "balanced", "exploratory"]] = Field(
        default=None, alias="planningDiversity"
    )
    planning_seed: Optional[int] = Field(
        default=None, alias="planningSeed", ge=0, le=2**53 - 1
    )

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
            if "roleType" in data and "role_type" not in data:
                data["role_type"] = data["roleType"]
            if "taskType" in data and "task_type" not in data:
                data["task_type"] = data["taskType"]
            if "clientRequestId" in data and "client_request_id" not in data:
                data["client_request_id"] = data["clientRequestId"]
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
    role_type: Optional[str] = None
    task_type: Optional[str] = None
    workflow_id: Optional[str] = None
    review_mode: str = "human_in_loop"
    role_id: Optional[str] = None
    context_id: Optional[str] = None
    context: Optional[list[Dict[str, Any]]] = None
    input: Dict[str, Any] = Field(default_factory=dict)
    security_level: str = "internal"
    priority: str = "normal"
    enabled_plugin_ids: Optional[list[str]] = Field(
        default=None, alias="enabledPluginIds"
    )

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
            if "roleType" in data and "role_type" not in data:
                data["role_type"] = data["roleType"]
            if "taskType" in data and "task_type" not in data:
                data["task_type"] = data["taskType"]
        return data


class ReviewRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    step_id: str
    decision: ReviewDecisionType
    reviewer: str = "system"
    comment: str = ""
    operation_id: Optional[str] = Field(default=None, alias="operationId")
    expected_run_updated_at: Optional[str] = Field(default=None, alias="expectedRunUpdatedAt")
    expected_step_status: Optional[str] = Field(default=None, alias="expectedStepStatus")

    @model_validator(mode="before")
    @classmethod
    def accept_camel_case(cls, data):
        if isinstance(data, dict):
            data = dict(data)
            aliases = {
                "stepId": "step_id",
                "operationId": "operation_id",
                "expectedRunUpdatedAt": "expected_run_updated_at",
                "expectedStepStatus": "expected_step_status",
            }
            for alias, field in aliases.items():
                if alias in data and field not in data:
                    data[field] = data[alias]
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
    payload = model.model_dump(by_alias=True, mode="json")
    payload.pop("idempotencyKey", None)
    payload.pop("idempotencyFingerprint", None)
    return payload


_SENSITIVE_RUNTIME_FIELD = (
    "authorization",
    "password",
    "secret",
    "token",
    "cookie",
    "apikey",
    "api_key",
    "stack",
    "traceback",
)


def _safe_runtime_projection(value: Any, *, depth: int = 0) -> Any:
    """Bound and redact runtime audit data before returning it to UI clients."""

    if depth > 6:
        return "[truncated]"
    if isinstance(value, dict):
        projected: Dict[str, Any] = {}
        for key, item in list(value.items())[:100]:
            normalized = str(key).lower().replace("-", "_")
            projected[str(key)] = (
                "[redacted]"
                if any(marker in normalized for marker in _SENSITIVE_RUNTIME_FIELD)
                else _safe_runtime_projection(item, depth=depth + 1)
            )
        return projected
    if isinstance(value, list):
        return [_safe_runtime_projection(item, depth=depth + 1) for item in value[:100]]
    if isinstance(value, str) and len(value) > 2000:
        return f"{value[:2000]}…"
    return value


def _runtime_summary(value: Any, *, limit: int = 320) -> str:
    if value in (None, "", {}, []):
        return ""
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(
            _safe_runtime_projection(value),
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
    return text if len(text) <= limit else f"{text[:limit]}…"


def _safe_runtime_event(event: Any) -> Dict[str, Any]:
    payload = _to_json(event)
    payload["payload"] = _safe_runtime_projection(payload.get("payload") or {})
    return payload


def _require_run_access(run: WorkflowRun) -> None:
    owner_user_id = str(run.input.get("authenticatedUserId") or "").strip()
    if not owner_user_id:
        # Legacy/internal runs predate ownership metadata and retain the existing gateway boundary.
        return
    actor = current_trusted_user()
    owner_tenant_id = str(run.input.get("authenticatedTenantId") or "").strip()
    if actor is None or actor.user_id != owner_user_id:
        raise HTTPException(status_code=404, detail=f"workflow run not found: {run.run_id}")
    if owner_tenant_id and actor.tenant_id != owner_tenant_id:
        raise HTTPException(status_code=404, detail=f"workflow run not found: {run.run_id}")


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
    request = _normalize_acg_start_request(request)
    request = _resolve_source_materials(request)
    task = runtime.create_task(
        title=request.title,
        domain=request.domain,
        intent=request.intent,
        input=_input_with_authenticated_actor(request.input),
        security_level=request.security_level,
        priority=request.priority,
        role_type=request.role_type,
        task_type=request.task_type,
        workflow_id=request.workflow_id,
        enabled_plugin_ids=request.enabled_plugin_ids,
    )
    with execution_context(workflow_id=request.workflow_id or "", task_id=task.task_id):
        logger.info("AgentOS task created; starting workflow")
        run = await runtime.start(
            task_id=task.task_id,
            workflow_id=request.workflow_id,
            review_mode=request.review_mode,
            enabled_plugin_ids=request.enabled_plugin_ids,
        )
        _bind_source_materials(request.input, task_id=task.task_id, run_id=run.run_id)
        logger.info("AgentOS workflow run started")
    return {"task": _to_json(task), "run": _to_json(run)}


def _workflow_start_idempotency_key(client_request_id: str | None) -> str | None:
    request_id = (client_request_id or "").strip()
    if not request_id:
        return None
    actor = current_trusted_user()
    caller = "anonymous"
    if actor is not None:
        tenant = actor.tenant_id or "default"
        caller = f"tenant:{tenant}:user:{actor.user_id or actor.subject or 'authenticated'}"
    material = f"{caller}:workflow_start:{request_id}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _workflow_start_fingerprint(request: WorkflowStartRequest) -> str:
    critical = {
        "title": request.title,
        "domain": request.domain,
        "intent": request.intent,
        "roleType": request.role_type,
        "taskType": request.task_type,
        "input": request.input,
        "securityLevel": request.security_level,
        "priority": request.priority,
        "workflowId": request.workflow_id,
        "reviewMode": request.review_mode,
        "enabledPluginIds": request.enabled_plugin_ids,
        "planningDiversity": request.planning_diversity,
        "planningSeed": request.planning_seed,
    }
    canonical = json.dumps(critical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _create_task_and_submit(
    runtime: WorkflowRuntime,
    coordinator: RunExecutionCoordinator,
    request: WorkflowStartRequest,
) -> Dict[str, Any]:
    request = _normalize_acg_start_request(request)
    request = _resolve_source_materials(request)
    idempotency_key = _workflow_start_idempotency_key(request.client_request_id)
    idempotency_fingerprint = _workflow_start_fingerprint(request)
    existing = (
        runtime.workflow_store.find_run_by_idempotency_key(idempotency_key)
        if idempotency_key
        else None
    )
    if existing is not None:
        if existing.idempotency_fingerprint != idempotency_fingerprint:
            raise IdempotencyConflictError(
                "clientRequestId was already used with different workflow start parameters"
            )
        task = runtime.task_manager.get_task(existing.task_id)
        if existing.status.value not in {"completed", "failed", "cancelled"}:
            await coordinator.submit(existing.run_id)
        latest = runtime.workflow_store.get_run(existing.run_id)
        return {"accepted": True, "task": _to_json(task), "run": _to_json(latest)}

    task = runtime.create_task(
        title=request.title,
        domain=request.domain,
        intent=request.intent,
        input=_input_with_authenticated_actor(request.input),
        security_level=request.security_level,
        priority=request.priority,
        role_type=request.role_type,
        task_type=request.task_type,
        workflow_id=request.workflow_id,
        enabled_plugin_ids=request.enabled_plugin_ids,
    )
    _, run = runtime.prepare_run(
        task_id=task.task_id,
        workflow_id=request.workflow_id,
        review_mode=request.review_mode,
        idempotency_key=idempotency_key,
        idempotency_fingerprint=idempotency_fingerprint,
        enabled_plugin_ids=request.enabled_plugin_ids,
    )
    _bind_source_materials(request.input, task_id=task.task_id, run_id=run.run_id)
    try:
        await coordinator.submit(run.run_id)
    except Exception as exc:
        await runtime.fail_run_safely(
            run.run_id,
            error_code="background_submission_failed",
            error_message=runtime._safe_error_message(exc),
        )
        raise
    latest = runtime.workflow_store.get_run(run.run_id)
    return {"accepted": True, "task": _to_json(task), "run": _to_json(latest)}


def _normalize_acg_start_request(request: WorkflowStartRequest) -> WorkflowStartRequest:
    source = str(request.input.get("source") or "").strip()
    normalized_input = dict(request.input)
    if source in {"acg", "acg-workbench"}:
        normalized_input["source"] = "acg"
    if request.planning_diversity is not None:
        normalized_input["planningDiversity"] = request.planning_diversity
    if request.planning_seed is not None:
        normalized_input["planningSeed"] = request.planning_seed
    return request.model_copy(update={"input": normalized_input})


def _resolve_source_materials(request: WorkflowStartRequest) -> WorkflowStartRequest:
    raw_materials = request.input.get("sourceMaterials")
    if raw_materials in (None, []):
        return request
    if not isinstance(raw_materials, list) or len(raw_materials) != 1 or not isinstance(raw_materials[0], dict):
        raise MaterialError("MATERIAL_COUNT_INVALID", "ACG 当前只支持一个合同材料", status_code=422)
    reference = raw_materials[0]
    material_id = str(reference.get("materialId") or "").strip()
    material = task_material_store.get(material_id, include_text=True)
    extracted_text = str(material.pop("extractedText"))
    working_text = str(request.input.get("contractText") or extracted_text).strip()
    if not working_text:
        raise MaterialError("MATERIAL_TEXT_EMPTY", "合同正文不能为空", status_code=422)
    working_hash = hashlib.sha256(working_text.encode("utf-8")).hexdigest()
    canonical = {
        "materialId": material_id,
        "purpose": "contract",
        "originalFilename": material["originalFilename"],
        "mediaType": material["mediaType"],
        "size": material["size"],
        "sha256": material["sha256"],
        "extractedTextSha256": material["extractedTextSha256"],
        "workingTextSha256": working_hash,
        "edited": working_hash != material["extractedTextSha256"],
        "textLength": len(working_text),
        "extraction": material["extraction"],
        "uri": f"material://{material_id}",
    }
    normalized_input = {**request.input, "contractText": working_text, "sourceMaterials": [canonical]}
    return request.model_copy(update={"input": normalized_input})


def _bind_source_materials(workflow_input: Dict[str, Any], *, task_id: str, run_id: str) -> None:
    for material in workflow_input.get("sourceMaterials") or []:
        if isinstance(material, dict) and material.get("materialId"):
            task_material_store.bind(str(material["materialId"]), task_id=task_id, run_id=run_id)


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


def _compact_chat_text(text: str) -> str:
    return "".join(str(text or "").strip().lower().split())


def _contains_any(text: str, markers: list[str]) -> bool:
    normalized = _compact_chat_text(text)
    return any(marker.lower() in normalized for marker in markers)


def _is_smalltalk(text: str) -> bool:
    normalized = _compact_chat_text(text).strip(".,!?;:，。！？；：")
    return normalized in {
        "",
        "hi",
        "hello",
        "hey",
        "你好",
        "您好",
        "你好啊",
        "您好啊",
        "你好呀",
        "在吗",
        "谢谢",
        "感谢",
        "你是谁",
        "你是什么角色",
        "你的角色是什么",
        "你是什么智能体",
        "你是什么模型",
        "你用什么模型",
        "你是哪个模型",
        "你基于什么模型",
        "底层模型是什么",
        "模型是什么",
        "介绍一下",
        "你能做什么",
    }


def _is_model_identity_question(text: str) -> bool:
    return _contains_any(
        text,
        [
            "你是什么模型",
            "你用什么模型",
            "你是哪个模型",
            "你基于什么模型",
            "底层模型",
            "模型是什么",
            "什么大模型",
            "llm",
            "大语言模型",
        ],
    )


def _should_use_legal_case_workflow(text: str) -> bool:
    return _contains_any(
        text,
        [
            "合同",
            "违约",
            "赔偿",
            "证据",
            "起诉",
            "仲裁",
            "诉讼",
            "纠纷",
            "案情",
            "审查",
            "条款",
            "借款",
            "欠款",
            "劳动",
            "工伤",
            "离婚",
            "侵权",
            "被告",
            "原告",
            "法院",
            "律师函",
            "协议",
            "租赁",
            "买卖",
            "交付",
            "付款",
            "定金",
            "工资",
            "加班",
            "辞退",
            "交通事故",
        ],
    )


def _is_contract_review_intent(text: str) -> bool:
    normalized = _compact_chat_text(text)
    explicit_markers = [
        "合同审查",
        "审查合同",
        "合同条款",
        "条款审查",
        "帮我看合同",
        "看看合同",
        "修改合同",
        "合同风险",
        "软件开发服务合同",
        "租赁合同",
        "买卖合同",
    ]
    contract_context_markers = [
        "甲方",
        "乙方",
        "条款",
        "验收",
        "违约金",
        "知识产权",
        "保密",
        "修改建议",
        "风险点",
    ]
    return _contains_any(text, explicit_markers) or (
        "合同" in normalized and _contains_any(text, contract_context_markers)
    )


def _is_general_legal_question(text: str) -> bool:
    return _contains_any(
        text,
        [
            "违法吗",
            "合法吗",
            "犯法吗",
            "犯罪吗",
            "是否违法",
            "是否犯罪",
            "会坐牢",
            "怎么判",
            "什么罪",
            "vpn",
            "翻墙",
            "代理",
        ],
    )


def _direct_smalltalk_answer(role: str) -> str:
    if role == "lawyer":
        return (
            "你好，我是知弈 AgentOS 的律师智能体。"
            "可以帮你做法律咨询、合同审查、风险识别和诉讼思路梳理。"
            "你可以直接说具体问题。"
        )
    if role == "teacher":
        return "你好，我是教师智能体。可以帮你设计课程、拆解知识点、生成练习和教学反馈。"
    if role == "programmer":
        return "你好，我是程序员智能体。可以帮你分析需求、阅读代码、生成实现方案和调试问题。"
    if role == "writer":
        return "你好，我是写作智能体。可以帮你做选题、提纲、人物设定、章节规划和文本润色。"
    return "你好，请直接告诉我你想处理的问题。"


def _direct_model_answer(role: str) -> str:
    role_name = {
        "lawyer": "律师智能体",
        "teacher": "教师智能体",
        "programmer": "程序员智能体",
        "writer": "写作智能体",
    }.get(role, "智能体")
    try:
        model_name = str(get_llm_gateway().model or "").strip()
    except Exception:
        model_name = ""

    if model_name:
        return f"我是知弈 AgentOS 的{role_name}。当前会话使用的语言模型是 {model_name}。"
    return f"我是知弈 AgentOS 的{role_name}。当前运行环境未提供可公开的模型名称。"


def _direct_agent_response(
    role: str,
    role_config: Dict[str, Any],
    request: LegacyAgentChatRequest,
    answer: str,
    observation: str,
    risk_level: Optional[str] = None,
    route_decision: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    routing = {
        "decision": "direct",
        "workflowRequired": False,
        "reason": observation,
    }
    if route_decision:
        routing.update(route_decision)
        routing["decision"] = "direct"
        routing["workflowRequired"] = False

    response: Dict[str, Any] = {
        "success": True,
        "answer": answer,
        "sessionId": request.session_id or f"session_{role}_{uuid.uuid4().hex[:12]}",
        "skillsUsed": [],
        "trace": [],
        "routing": routing,
        "federated": {
            "enabled": True,
            "applied": False,
            "risk_adjustment": 0,
            "confidence": 0.85,
            "federated_nodes_count": 0,
        },
    }
    if role == "lawyer":
        response["riskLevel"] = risk_level or "low"
    return response


def _allowed_legacy_workflow_ids(role: str, role_config: Dict[str, Any]) -> set[str]:
    workflow_ids = {str(role_config["workflow_id"])}
    if role == "lawyer":
        workflow_ids.add("legal_contract_review_v1")
    return workflow_ids


def _fallback_route_decision(role: str, role_config: Dict[str, Any], text: str) -> Dict[str, Any]:
    if _is_smalltalk(text):
        direct_answer_type = "model_intro" if _is_model_identity_question(text) else "role_intro"
        return {
            "decision": "direct",
            "workflowRequired": False,
            "reason": "smalltalk_or_capability_intro",
            "directAnswerType": direct_answer_type,
            "source": "rules",
            "confidence": 0.9,
        }

    workflow_id = _legacy_workflow_id_for_chat(role, role_config, text)
    return {
        "decision": "workflow",
        "workflowRequired": True,
        "workflowId": workflow_id,
        "reason": "professional_task",
        "directAnswerType": "none",
        "source": "rules",
        "confidence": 0.65,
    }


def _route_prompt(role: str, role_config: Dict[str, Any], text: str) -> str:
    workflow_options = [
        {
            "workflow_id": role_config["workflow_id"],
            "when_to_use": "专业任务需要该角色的常规多步骤技能链处理。",
        }
    ]
    if role == "lawyer":
        workflow_options.append(
            {
                "workflow_id": "legal_contract_review_v1",
                "when_to_use": "用户明确要求审查、修改、评估合同条款，或提供了合同文本需要条款风险识别。",
            }
        )

    return "\n".join(
        [
            "你是 AgentOS 的路由判定器，只负责判断用户输入是否需要进入工作流。",
            "请返回严格 JSON，不要输出解释文字。",
            "判定原则：",
            "1. 问候、身份/能力/底层模型介绍、寒暄，decision=direct。",
            "2. 普通问答若不需要多步骤工具/工作流，decision=direct。",
            "3. 明确需要专业产物、检索、分析链、合同审查、课程设计、需求分析、提纲生成等，decision=workflow。",
            "4. 只有明确合同审查/条款修改/合同文本风险识别时，才选择 legal_contract_review_v1。",
            "5. 不要因为出现“合同”“交付”“付款”等单个词就选择合同审查图；诉讼风险、违约咨询通常走律师常规案件分析。",
            "",
            f"当前角色：{role}",
            f"可选工作流：{json.dumps(workflow_options, ensure_ascii=False)}",
            f"用户输入：{text}",
            "",
            "JSON 字段：decision, workflow_id, reason, confidence, direct_answer_type。",
            "direct_answer_type 可选 smalltalk、role_intro、model_intro、general_question、none。",
            "direct 时 workflow_id 填 none；常规角色工作流可填 legacy_default 或具体 workflow_id。",
        ]
    )


def _normalise_route_decision(
    *,
    raw: Dict[str, Any],
    role: str,
    role_config: Dict[str, Any],
    source: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    decision = str(raw.get("decision") or "").strip().lower()
    if decision not in {"direct", "workflow"}:
        return None

    try:
        confidence = float(raw.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence < 0.5:
        return None

    direct_answer_type = str(raw.get("direct_answer_type") or raw.get("directAnswerType") or "none").strip().lower()
    reason = str(raw.get("reason") or "").strip() or "llm_route_decision"
    route: Dict[str, Any] = {
        "decision": decision,
        "workflowRequired": decision == "workflow",
        "reason": reason,
        "confidence": confidence,
        "directAnswerType": direct_answer_type,
        "source": source,
    }
    if provider:
        route["provider"] = provider
    if model:
        route["model"] = model

    if decision == "direct":
        return route

    workflow_id = str(raw.get("workflow_id") or raw.get("workflowId") or "").strip()
    if workflow_id in {"", "none", "null", "legacy_default"}:
        workflow_id = str(role_config["workflow_id"])

    if workflow_id not in _allowed_legacy_workflow_ids(role, role_config):
        return None

    route.update(
        {
            "workflowId": workflow_id,
        }
    )
    return route


def _llm_route_decision(role: str, role_config: Dict[str, Any], text: str) -> Optional[Dict[str, Any]]:
    try:
        gateway = get_llm_gateway()
        response = gateway.generate_json(
            _route_prompt(role, role_config, text),
            CHAT_ROUTE_DECISION_SCHEMA,
            temperature=0,
        )
        data = response.get("data")
        if not isinstance(data, dict):
            return None
        return _normalise_route_decision(
            raw=data,
            role=role,
            role_config=role_config,
            source="llm",
            provider=str(response.get("provider") or gateway.provider_name),
            model=str(response.get("model") or gateway.model),
        )
    except Exception:
        return None


def _classify_legacy_chat_route(role: str, role_config: Dict[str, Any], text: str) -> Dict[str, Any]:
    rule_decision = _fallback_route_decision(role, role_config, text)
    if rule_decision.get("decision") == "direct":
        return rule_decision

    llm_decision = _llm_route_decision(role, role_config, text)
    if llm_decision is not None:
        if (
            role == "lawyer"
            and llm_decision.get("decision") == "direct"
            and _is_general_legal_question(text)
            and not _is_smalltalk(text)
        ):
            return rule_decision
        return llm_decision
    return rule_decision


def _legacy_workflow_id_for_chat(role: str, role_config: Dict[str, Any], text: str) -> str:
    if role == "lawyer" and _is_contract_review_intent(text):
        return "legal_contract_review_v1"
    return str(role_config["workflow_id"])


def _legacy_workflow_intent(role_config: Dict[str, Any], workflow_id: str) -> str:
    if workflow_id == "legal_contract_review_v1":
        return "contract_review"
    return str(role_config["intent"])


def _legacy_workflow_input(role_config: Dict[str, Any], workflow_id: str, text: str) -> Dict[str, Any]:
    workflow_input = {
        "source": "legacy_agent_chat",
        "chatText": text,
        "text": text,
    }
    if workflow_id == "legal_contract_review_v1":
        workflow_input.update(
            {
                "contractText": text,
                "caseText": text,
            }
        )
        return workflow_input

    workflow_input[role_config["input_key"]] = text
    return workflow_input


def _direct_agent_chat_response(
    role: str,
    role_config: Dict[str, Any],
    request: LegacyAgentChatRequest,
    route_decision: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    text = request.text.strip()
    if route_decision and route_decision.get("decision") == "direct":
        direct_answer_type = str(route_decision.get("directAnswerType") or "").lower()
        if direct_answer_type == "model_intro" or _is_model_identity_question(text):
            return _direct_agent_response(
                role=role,
                role_config=role_config,
                request=request,
                answer=_direct_model_answer(role),
                observation=str(route_decision.get("reason") or "model_identity_intro"),
                risk_level="low",
                route_decision=route_decision,
            )

        return _direct_agent_response(
            role=role,
            role_config=role_config,
            request=request,
            answer=_direct_smalltalk_answer(role),
            observation=str(route_decision.get("reason") or "smalltalk_or_capability_intro"),
            risk_level="low",
            route_decision=route_decision,
        )

    if _is_smalltalk(text):
        answer = _direct_model_answer(role) if _is_model_identity_question(text) else _direct_smalltalk_answer(role)
        return _direct_agent_response(
            role=role,
            role_config=role_config,
            request=request,
            answer=answer,
            observation="smalltalk_or_capability_intro",
            risk_level="low",
        )

    return None


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


def _contract_review_risk_level(artifacts: Dict[str, Any]) -> str:
    risk_output = artifacts.get("risk_detect", {}) if isinstance(artifacts.get("risk_detect"), dict) else {}
    risks = risk_output.get("risks", [])
    levels = [str(item.get("level", "")).lower() for item in risks if isinstance(item, dict)]
    if "high" in levels:
        return "high"
    if "medium" in levels:
        return "medium"
    if "low" in levels:
        return "low"
    return "unknown"


def _legacy_contract_review_answer(artifacts: Dict[str, Any]) -> str:
    parse_output = artifacts.get("parse_contract", {}) if isinstance(artifacts.get("parse_contract"), dict) else {}
    risk_output = artifacts.get("risk_detect", {}) if isinstance(artifacts.get("risk_detect"), dict) else {}
    evidence_output = (
        artifacts.get("legal_evidence_match", {})
        if isinstance(artifacts.get("legal_evidence_match"), dict)
        else {}
    )
    suggestion_output = (
        artifacts.get("suggestion_generate", {})
        if isinstance(artifacts.get("suggestion_generate"), dict)
        else {}
    )

    contract_type = parse_output.get("contract_type") or "未识别"
    risks = risk_output.get("risks", [])
    evidences = evidence_output.get("evidences", [])
    suggestions = suggestion_output.get("revision_suggestions", [])

    lines = [
        f"## 合同审查摘要：{contract_type}",
        "",
        f"分析状态：{risk_output.get('analysis_status') or 'unknown'}。",
        "",
        "### 1. 主要风险",
    ]
    if risks:
        for item in risks[:5]:
            if not isinstance(item, dict):
                continue
            title = item.get("title") or item.get("id") or "未命名风险"
            level = _risk_level_label(item.get("level"))
            reason = item.get("reason") or ""
            lines.append(f"- {title}（风险：{level}）：{reason}")
    else:
        lines.append("- 未生成可验证的风险条目。")

    lines.extend(["", "### 2. 依据匹配"])
    if evidences:
        for item in evidences[:5]:
            if not isinstance(item, dict):
                continue
            source = item.get("sourceName") or item.get("source_type") or "相关依据"
            citation = item.get("citationText") or item.get("summary") or ""
            lines.append(f"- {source}：{citation}")
    else:
        lines.append("- 暂无可展示的依据匹配结果。")

    lines.extend(["", "### 3. 修改建议"])
    if suggestions:
        for item in suggestions[:5]:
            if not isinstance(item, dict):
                continue
            title = item.get("title") or item.get("riskId") or "相关条款"
            suggestion = item.get("suggestion") or ""
            lines.append(f"- {title}：{suggestion}")
    else:
        lines.append("- 未生成修改建议。")

    lines.extend(["", "> 当前流程停在人工审核节点；确认风险和建议后，可继续生成正式审查报告。"])
    return "\n".join(lines)


def _legacy_lawyer_answer(artifacts: Dict[str, Any]) -> str:
    if any(key in artifacts for key in ("parse_contract", "risk_detect", "legal_evidence_match", "suggestion_generate")):
        return _legacy_contract_review_answer(artifacts)

    intake = artifacts.get("case_intake", {}) if isinstance(artifacts.get("case_intake"), dict) else {}
    statute = artifacts.get("statute", {}) if isinstance(artifacts.get("statute"), dict) else {}
    risk = artifacts.get("risk", {}) if isinstance(artifacts.get("risk"), dict) else {}

    case_type = intake.get("case_type") or "未识别"
    case_summary = intake.get("case_summary") or "未生成案情摘要。"
    legal_issues = _ensure_text_list(intake.get("legal_issues"))
    missing_info = _ensure_text_list(intake.get("missing_info"))
    legal_basis = statute.get("legal_basis", [])
    basis_items = []
    for item in legal_basis if isinstance(legal_basis, list) else _ensure_text_list(legal_basis):
        formatted = _format_legal_basis_item(item)
        if formatted:
            basis_items.append(formatted)
    risk_level = risk.get("risk_level") or risk.get("riskLevel") or "unknown"
    risk_score = risk.get("risk_score") or risk.get("riskScore")
    key_risks = _ensure_text_list(risk.get("key_risks"))
    suggestions = _ensure_text_list(risk.get("mitigation_suggestions"))

    lines = [
        f"## 法律初步分析：{case_type}",
        "",
        "### 1. 案情识别",
        str(case_summary),
        "",
        "### 2. 主要争议焦点",
        *([f"- {item}" for item in legal_issues] or ["- 未生成争议焦点。"]),
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
    if key_risks:
        lines.extend(f"- {item}" for item in key_risks)
    else:
        lines.append("- 未生成风险结论。")

    if missing_info:
        lines.extend(["", "### 5. 待补充信息", *[f"- {item}" for item in missing_info]])

    lines.extend(["", "### 6. 下一步建议"])
    lines.extend([f"- {item}" for item in suggestions] or ["- 未生成下一步建议。"])
    lines.extend(["", "> 当前结果不构成法律意见；未生成的专业结论不会由固定模板补齐。"])
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
        "context_refs": [],
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

    code_generation = artifacts.setdefault("code_generation", _programmer_code_generation(request_text))
    search_output = artifacts.get("codebase_semantic_search")
    if isinstance(code_generation, dict) and isinstance(search_output, dict):
        code_generation["context_refs"] = [
            {
                "file_path": item.get("file_path"),
                "line": item.get("line"),
                "score": item.get("score"),
            }
            for item in list(search_output.get("hits") or [])[:5]
            if isinstance(item, dict) and item.get("file_path")
        ]
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
        "目标：基于 Python FastAPI + JWT 实现简单的用户认证与权限管理模块。",
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
        "## 2. 认证相关代码检索结果（真实只读索引）",
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

    answer = str(run.output.get("final_answer") if isinstance(run.output, dict) else "").strip()
    if answer:
        return answer
    status = getattr(run.status, "value", run.status)
    return f"工作流未生成可展示结果（状态：{status}）。"


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
        response["riskLevel"] = risk.get("risk_level") or risk.get("riskLevel") or _contract_review_risk_level(artifacts)
        if isinstance(artifacts.get("risk_detect"), dict):
            response["contractReview"] = {
                "parseContract": artifacts.get("parse_contract", {}),
                "riskDetect": artifacts.get("risk_detect", {}),
                "legalEvidenceMatch": artifacts.get("legal_evidence_match", {}),
                "suggestionGenerate": artifacts.get("suggestion_generate", {}),
            }
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
    response["workflowRunId"] = run.run_id
    response["workflowId"] = run.workflow_id
    response["workflowStatus"] = run.status.value
    response["runtimeEngine"] = getattr(run, "runtime_engine", None)
    response["implementationId"] = getattr(run, "implementation_id", None)
    response["routing"] = {
        "decision": "workflow",
        "workflowRequired": True,
        "workflowId": run.workflow_id,
        "runtimeEngine": getattr(run, "runtime_engine", None),
        "implementationId": getattr(run, "implementation_id", None),
    }
    return response


def create_router(
    runtime: WorkflowRuntime,
    coordinator: RunExecutionCoordinator | None = None,
) -> APIRouter:
    router = APIRouter()
    execution_coordinator = coordinator or RunExecutionCoordinator(runtime)
    progress_assembler = ProgressAssembler()

    @router.post("/core/materials", status_code=201)
    async def upload_task_material(file: UploadFile = File(...)):
        try:
            task_material_store.cleanup_drafts()
            content = await file.read(10 * 1024 * 1024 + 1)
            extraction = await extract_material(content, file.filename or "")
            return task_material_store.create(
                filename=file.filename or "unknown",
                media_type=file.content_type or "application/octet-stream",
                content=content,
                extraction=extraction,
            )
        except MaterialError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"error": exc.code, "message": str(exc)},
            )

    @router.delete("/core/materials/{material_id}", status_code=204)
    async def delete_task_material(material_id: str):
        try:
            task_material_store.delete_draft(material_id)
            return None
        except MaterialError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"error": exc.code, "message": str(exc)},
            )

    @router.post("/core/tasks")
    async def create_task(request: AgentTaskCreateRequest):
        try:
            task_input = dict(request.input)
            if request.planning_diversity is not None:
                task_input["planningDiversity"] = request.planning_diversity
            if request.planning_seed is not None:
                task_input["planningSeed"] = request.planning_seed
            task = runtime.create_task(
                title=request.title,
                domain=request.domain,
                intent=request.intent,
                input=_input_with_authenticated_actor(task_input),
                security_level=request.security_level,
                priority=request.priority,
                role_type=request.role_type,
                task_type=request.task_type,
                enabled_plugin_ids=request.enabled_plugin_ids,
            )
            with execution_context(task_id=task.task_id):
                logger.info("AgentOS task created")
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
            with execution_context(workflow_id=request.workflow_id or "", task_id=request.task_id):
                run = await runtime.start(
                    task_id=request.task_id,
                    workflow_id=request.workflow_id,
                    review_mode=request.review_mode,
                    enabled_plugin_ids=request.enabled_plugin_ids,
                )
                logger.info("AgentOS workflow run started")
            return _to_json(run)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/core/workflows/start")
    async def start_workflow_from_workbench(request: WorkflowStartRequest):
        try:
            return await _create_task_and_start(runtime, request)
        except MaterialError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/core/plugins")
    async def list_installed_plugins():
        return runtime.plugin_scope_resolver.installed_plugin_projection()

    @router.post("/core/workflows/start-async", status_code=202)
    async def start_workflow_async(request: WorkflowStartRequest):
        try:
            return await _create_task_and_submit(runtime, execution_coordinator, request)
        except MaterialError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except PluginScopeError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": exc.code, "message": exc.detail},
            ) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail="workflow execution could not be submitted") from exc

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
            roleType=request.role_type,
            taskType=request.task_type,
            enabledPluginIds=request.enabled_plugin_ids,
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
        route_decision = _classify_legacy_chat_route(role_key, role_config, text)
        if route_decision.get("decision") == "direct":
            direct_response = _direct_agent_chat_response(role_key, role_config, request, route_decision)
            if direct_response is not None:
                return direct_response

        workflow_id = str(route_decision.get("workflowId") or _legacy_workflow_id_for_chat(role_key, role_config, text))
        workflow_input = _legacy_workflow_input(role_config, workflow_id, text)
        start_request = WorkflowStartRequest(
            title=f"{role_config['title']}: {text[:40]}",
            domain=role_config["domain"],
            intent=_legacy_workflow_intent(role_config, workflow_id),
            input=workflow_input,
            securityLevel="internal",
            priority="normal",
            workflowId=workflow_id,
            reviewMode="human_in_loop" if workflow_id == "legal_contract_review_v1" else "auto",
        )
        try:
            payload = await _create_task_and_start(runtime, start_request)
            run = runtime.get_status(payload["run"]["runId"])
            response = _legacy_response(role_key, role_config, request, run)
            response["routing"].update(route_decision)
            response["routing"]["workflowId"] = run.workflow_id
            return response
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/core/workflows/runs")
    async def list_workflow_runs(
        status: Optional[str] = None,
        statuses: Optional[str] = None,
        domain: Optional[str] = None,
        workflow_id: Optional[str] = Query(None, alias="workflowId"),
        task_id: Optional[str] = Query(None, alias="taskId"),
        lifecycle_phase: Optional[str] = Query(None, alias="lifecyclePhase"),
        source: Optional[str] = None,
        summary: bool = False,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    ):
        if workflow_id:
            workflow_id = runtime.resolve_workflow_id(workflow_id)
        actor = current_trusted_user()
        requested_statuses = [item.strip() for item in (statuses or "").split(",") if item.strip()]
        result = runtime.workflow_store.list_runs(
            status=status,
            statuses=requested_statuses or None,
            domain=domain,
            workflow_id=workflow_id,
            task_id=task_id,
            lifecycle_phase=lifecycle_phase,
            source=source,
            owner_user_id=actor.user_id if actor else None,
            owner_tenant_id=actor.tenant_id if actor else None,
            page=page,
            page_size=page_size,
        )
        if not summary:
            return _page_to_json(result)
        summary_items = []
        for run in result.items:
            try:
                task_title = runtime.workflow_store.get_task(run.task_id).title
            except KeyError:
                task_title = None
            summary_items.append(
                {
                    **_to_json(progress_assembler.assemble(run)),
                    "source": run.input.get("source"),
                    "title": task_title,
                    "createdAt": run.created_at,
                }
            )
        return {
            "items": summary_items,
            "total": result.total,
            "page": result.page,
            "pageSize": result.page_size,
        }

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
            run = runtime.get_status(run_id)
            _require_run_access(run)
            try:
                task_title = runtime.workflow_store.get_task(run.task_id).title
            except KeyError:
                task_title = None
            graph = run.runtime_graph
            dynamic_step_count = (
                sum(
                    1
                    for node in graph.nodes
                    if node.node_type.value == "step" and node.created_graph_version > 1
                )
                if graph is not None
                else 0
            )
            return {
                **_to_json(run),
                "runtimeGraph": (
                    _safe_runtime_projection(_to_json(graph)) if graph is not None else None
                ),
                "title": task_title,
                "graphVersion": graph.graph_version if graph is not None else None,
                "appliedPatches": [_to_json(item) for item in graph.applied_patches] if graph is not None else [],
                "runtimeEvents": (
                    [_safe_runtime_event(item) for item in graph.runtime_events]
                    if graph is not None
                    else []
                ),
                "dynamicStepCount": dynamic_step_count,
                "bindingSwitchCount": (
                    sum(node.binding_switch_count for node in graph.nodes) if graph is not None else 0
                ),
                "branchDecisions": (
                    [_to_json(item) for item in graph.branch_decisions] if graph is not None else []
                ),
                "skippedByConditionCount": (
                    sum(
                        node.status.value == "skipped_by_condition" for node in graph.nodes
                    )
                    if graph is not None
                    else 0
                ),
                "conditionalDecisionCount": (
                    len(graph.branch_decisions) if graph is not None else 0
                ),
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/core/workflows/runs/{run_id}/progress")
    async def get_workflow_progress(run_id: str):
        try:
            run = runtime.get_status(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Workflow progress store read failed", extra={"runId": run_id})
            raise HTTPException(status_code=503, detail="workflow progress is temporarily unavailable") from exc
        _require_run_access(run)
        return _to_json(progress_assembler.assemble(run))

    @router.get("/core/workflows/runs/{run_id}/checkpoints")
    async def list_checkpoints(run_id: str):
        try:
            _require_run_access(runtime.get_status(run_id))
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

        _require_run_access(run)

        if format == "markdown":
            return PlainTextResponse(
                runtime.trace_store.export_markdown(run),
                media_type="text/markdown; charset=utf-8",
            )
        return runtime.trace_store.export_json(run)

    @router.get("/core/workflows/runs/{run_id}/acg")
    async def get_acg_view(run_id: str):
        """ACG 引擎可视化聚合视图：拓扑蓝图 + 数据血缘 + 恢复轨迹 + 低熵指标。

        供前端 ACG 拓扑图 / 数据血缘 / 恢复轨迹面板直接消费。
        """
        try:
            run = runtime.get_status(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        _require_run_access(run)

        events = runtime.trace_store.events(run)

        def _by_type(*types: str) -> list[Dict[str, Any]]:
            wanted = set(types)
            return [
                _to_json(e) for e in events if e.event_type.value in wanted
            ]

        # 低熵指标聚合：平均节省率、累计可获取/投递 token
        consumed = [e for e in events if e.event_type.value == "data_consumed"]
        tokens_available = sum(int(e.payload.get("tokensAvailable", 0)) for e in consumed if e.payload)
        tokens_delivered = sum(int(e.payload.get("tokensDelivered", 0)) for e in consumed if e.payload)
        effective_saving = (
            round(max(0.0, 1.0 - tokens_delivered / tokens_available), 4)
            if tokens_available > 0
            else 0.0
        )
        provenance = run.provenance or {
            "schemaVersion": 2,
            "productions": [],
            "consumptions": [],
            "interactions": [],
            "integrityStatus": "valid",
        }
        interactions = provenance.get("interactions") if isinstance(provenance, dict) else []
        if not isinstance(interactions, list):
            interactions = []
        contract_violations = _by_type("contract_violation")
        graph = run.runtime_graph
        runtime_blueprint = run.acg_blueprint
        if graph is not None:
            structure = graph.to_blueprint(effective_only=True).model_dump(
                by_alias=True, mode="json"
            )
            runtime_blueprint = {
                **dict(run.acg_blueprint or {}),
                "graphId": graph.graph_id,
                "nodes": structure["nodes"],
                "edges": structure["edges"],
                "metadata": {
                    **dict((run.acg_blueprint or {}).get("metadata") or {}),
                    "runtimeGraphVersion": graph.graph_version,
                },
            }
        dynamic_step_count = (
            sum(
                1
                for node in graph.nodes
                if node.node_type.value == "step" and node.created_graph_version > 1
            )
            if graph is not None
            else 0
        )

        # 交付物：把每个步骤的实际产出（风险/证据/建议/报告等）汇总，
        # 供前端「审查结论」面板展示真正交付给用户的成果，而非仅引擎内部视角。
        step_outputs = [
            {
                "stepId": step.step_id,
                "name": step.name,
                "status": step.status.value if hasattr(step.status, "value") else str(step.status),
                "output": step.output or {},
            }
            for step in run.steps
            if step.output
        ]
        # Compatibility: deliverables historically meant every non-empty Step output.
        deliverables = step_outputs
        final_artifacts: list[Dict[str, Any]] = []
        for step in run.steps:
            artifact = (step.output or {}).get("artifact")
            if not isinstance(artifact, dict):
                continue
            content = artifact.get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            final_artifacts.append(
                {
                    "artifactId": str(
                        artifact.get("artifactId") or f"artifact_{run.run_id}_{step.step_id}"
                    ),
                    "type": str(artifact.get("type") or "report"),
                    "title": str(artifact.get("title") or step.name),
                    "mediaType": str(artifact.get("mediaType") or "text/markdown"),
                    "content": content,
                    "structuredData": _safe_runtime_projection(
                        artifact.get("structuredData")
                        if isinstance(artifact.get("structuredData"), dict)
                        else {}
                    ),
                    "stepId": step.step_id,
                }
            )
        # 最终报告（若有 report_generate 类步骤产出 markdown，单独提取置顶展示）
        final_report = None
        for step in run.steps:
            out = step.output or {}
            md = (
                out.get("final_answer")
                or out.get("report_markdown")
                or out.get("report")
                or out.get("final_report")
            )
            if isinstance(md, str) and md.strip():
                final_report = md
        run_output = run.output or {}
        if not final_report:
            md = (
                run_output.get("final_answer")
                or run_output.get("report_markdown")
                or run_output.get("report")
            )
            if isinstance(md, str) and md.strip():
                final_report = md
        if final_report and not final_artifacts:
            final_artifacts.append(
                {
                    "artifactId": f"artifact_legacy_{run.run_id}",
                    "type": "report",
                    "title": "Workflow final report",
                    "mediaType": "text/markdown",
                    "content": final_report,
                    "structuredData": {},
                    "stepId": None,
                    "legacy": True,
                }
            )

        step_states = []
        for step in run.steps:
            node = graph.get_node(step.step_id) if graph is not None else None
            step_states.append(
                {
                    "stepId": step.step_id,
                    "status": step.status.value if hasattr(step.status, "value") else str(step.status),
                    "agentName": step.agent_name,
                    "attempt": step.attempt,
                    "retryCount": step.retry_count,
                    "currentBinding": node.current_binding if node is not None else None,
                    "bindingHistory": node.binding_history if node is not None else [],
                    "bindingSwitchCount": node.binding_switch_count if node is not None else 0,
                    "attempts": (
                        [
                            {
                                "attemptId": attempt.attempt_id,
                                "attemptNumber": attempt.attempt_number,
                                "graphVersion": attempt.graph_version,
                                "bindingId": attempt.binding_id,
                                "agentName": attempt.agent_name,
                                "modelName": attempt.model_name,
                                "status": attempt.status.value,
                                "startedAt": attempt.started_at,
                                "endedAt": attempt.ended_at,
                                "errorSummary": _runtime_summary(attempt.error),
                            }
                            for attempt in node.attempts
                        ]
                        if node is not None
                        else []
                    ),
                    "sourcePatchId": node.source_patch_id if node is not None else None,
                    "createdGraphVersion": node.created_graph_version if node is not None else 1,
                    "outputVersion": node.output_version if node is not None else 0,
                    "outputSummary": _runtime_summary(node.output) if node is not None else "",
                    "errorSummary": _runtime_summary(node.error) if node is not None else "",
                }
            )

        return {
            "runId": run.run_id,
            "status": run.status.value,
            "engine": run.runtime_engine,
            "acgBlueprint": runtime_blueprint,
            "graphVersion": graph.graph_version if graph is not None else None,
            "appliedPatches": [_to_json(item) for item in graph.applied_patches] if graph is not None else [],
            "runtimeEvents": (
                [_safe_runtime_event(item) for item in graph.runtime_events]
                if graph is not None
                else []
            ),
            "dynamicStepCount": dynamic_step_count,
            "bindingSwitchCount": (
                sum(node.binding_switch_count for node in graph.nodes) if graph is not None else 0
            ),
            "branchDecisions": (
                [_to_json(item) for item in graph.branch_decisions] if graph is not None else []
            ),
            "selectedEdgeIds": (
                [edge_id for item in graph.branch_decisions for edge_id in item.selected_edge_ids]
                if graph is not None
                else []
            ),
            "terminatedEdgeIds": (
                [edge_id for item in graph.branch_decisions for edge_id in item.terminated_edge_ids]
                if graph is not None
                else []
            ),
            "skippedByConditionCount": (
                sum(node.status.value == "skipped_by_condition" for node in graph.nodes)
                if graph is not None
                else 0
            ),
            "conditionalDecisionCount": (
                len(graph.branch_decisions) if graph is not None else 0
            ),
            "completedStepIds": run.completed_step_ids,
            "activeStepIds": run.active_step_ids,
            "stepStates": step_states,
            "provenance": provenance,
            "interactions": interactions,
            "contractViolations": contract_violations,
            "recoveryTrace": _by_type("step_failed", "run_recovered"),
            "scheduleTrace": _by_type("step_scheduled"),
            "deliverables": deliverables,
            "stepOutputs": step_outputs,
            "finalArtifacts": final_artifacts,
            "finalReport": final_report,
            "lowEntropyMetrics": {
                "averageSavingRatio": effective_saving,
                "effectiveSavingRatio": effective_saving,
                "tokensAvailable": tokens_available,
                "tokensDelivered": tokens_delivered,
                "tokensSaved": max(0, tokens_available - tokens_delivered),
                "recoveryCount": run.recovery_count,
                "interactionCount": len(interactions),
                "contractViolationCount": len(contract_violations),
                "integrityStatus": provenance.get("integrityStatus", "legacy_or_invalid"),
            },
        }

    @router.get("/core/workflows/runs/{run_id}/reviews")
    async def list_reviews(run_id: str):
        try:
            _require_run_access(runtime.get_status(run_id))
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
            existing_run = runtime.get_status(run_id)
            _require_run_access(existing_run)
            actor = current_trusted_user()
            run = await runtime.apply_review(
                ReviewDecision(
                    runId=run_id,
                    stepId=request.step_id,
                    decision=request.decision,
                    reviewer=actor.user_id if actor else request.reviewer,
                    comment=request.comment,
                    operationId=request.operation_id,
                    expectedRunUpdatedAt=request.expected_run_updated_at,
                    expectedStepStatus=request.expected_step_status,
                )
            )
            return _to_json(run)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ReviewConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/core/workflows/runs/{run_id}/resume")
    async def resume_workflow(run_id: str, request: ResumeRequest):
        try:
            _require_run_access(runtime.get_status(run_id))
            run = await runtime.resume_from_checkpoint(run_id=run_id, checkpoint_id=request.checkpoint_id)
            return _to_json(run)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/core/workflows/runs/{run_id}/cancel")
    async def cancel_workflow(run_id: str):
        try:
            _require_run_access(runtime.get_status(run_id))
            return _to_json(runtime.cancel(run_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.delete("/core/workflows/runs/{run_id}")
    async def delete_workflow_run(run_id: str):
        try:
            run = runtime.get_status(run_id)
            _require_run_access(run)
            material_ids = [
                str(item.get("materialId"))
                for item in (run.input.get("sourceMaterials") or [])
                if isinstance(item, dict) and item.get("materialId")
            ]
            if execution_coordinator.is_active(run_id) or run.status in {
                WorkflowStatus.PENDING,
                WorkflowStatus.PLANNING,
                WorkflowStatus.RUNNING,
                WorkflowStatus.RETRYING,
            }:
                return JSONResponse(
                    status_code=409,
                    content={
                        "code": "RUN_NOT_TERMINAL",
                        "message": "当前任务仍未结束，请先完成或取消任务。",
                    },
                )
            if run.status == WorkflowStatus.WAITING_REVIEW:
                return JSONResponse(
                    status_code=409,
                    content={
                        "code": "RUN_WAITING_REVIEW",
                        "message": "当前任务正在等待审核，请完成审核或取消任务后再删除。",
                    },
                )
            result = runtime.workflow_store.delete_run(run_id)
            if result.task_deleted:
                runtime.trace_store.delete_task_events(result.task_id)
            try:
                task_material_store.release_run(run_id, material_ids)
            except Exception:
                logger.exception(
                    "workflow_run_material_release_failed",
                    extra={"runId": run_id, "materialIds": material_ids},
                )
            return {
                "runId": result.run_id,
                "taskId": result.task_id,
                "deleted": True,
                "taskDeleted": result.task_deleted,
            }
        except WorkflowRunNotTerminalError as exc:
            if exc.status == WorkflowStatus.WAITING_REVIEW:
                return JSONResponse(
                    status_code=409,
                    content={
                        "code": "RUN_WAITING_REVIEW",
                        "message": "当前任务正在等待审核，请完成审核或取消任务后再删除。",
                    },
                )
            return JSONResponse(
                status_code=409,
                content={
                    "code": "RUN_NOT_TERMINAL",
                    "message": "当前任务仍未结束，请先完成或取消任务。",
                },
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return router


runtime = build_default_runtime()
coordinator = RunExecutionCoordinator(runtime)
router = create_router(runtime, coordinator)
