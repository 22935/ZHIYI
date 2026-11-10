"""Reference-first HTTP projection of the single ``ExecutionRuntime``."""

from __future__ import annotations

import hashlib
import json
import logging
import asyncio
from tempfile import SpooledTemporaryFile
from sqlite3 import Error as SQLiteError
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, File, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from contracts.mission_semantic import MissionSemanticContent, MissionSemanticEditRequest, MissionSemanticRequest
from contracts.mission_revision import MissionRevisionDecision, MissionRevisionConflict, revision_observation, revision_successor_key
import sqlite3
from components.mission_manager.semantic_resolver import MissionSemanticResolver

from app.execution.coordinator import RunExecutionCoordinator
from app.execution.run_capabilities import assert_mutable_run, project_run_capabilities
from app.api.agentos_c2 import create_c2_router, project_initial_control
from app.security.internal_auth import current_trusted_user, current_semantic_principal
from contracts.workflow import MissionRecordState, ReviewDecision, ReviewDecisionType, RunRecordState, RuntimeRunRecord, StepStatus, WorkflowStatus
from contracts.content import ContentKind
from domain.models import MissionStatus, RunStatus
from domain.repository import EntityNotFoundError
from components.planner import ACGPlanningError, TaskDecompositionError
from components.resource.infrastructure.signing.request_authenticator import (
    NodeRequestAuthenticator,
    ResourceRequestAuthenticator,
    ResourceRequestExpired,
    ResourceRequestInvalid,
    ResourceRequestNotFound,
    ResourceRequestReplay,
)
from contracts.resource import (
    NodeProfile,
    NodeSnapshot,
    RuntimeProfile,
    RuntimeSnapshot,
)
from components.mission_manager.state_machine import InvalidStateTransition
from components.resource.infrastructure.runtime_store import StaleResourceObservation
from app.tools.permissions import normalize_relative_path


class WorkspaceBinaryFallbackNeeded(Exception):
    """文本编辑链拒绝（FS_NOT_TEXT/FS_TOO_LARGE）：读取端点改走二进制读 + 预览提取。

    只在读取链内做控制流；保存/列表调用方各自映射回 409/413/415。
    """
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
from runtime import ExecutionRuntime
from runtime.planning_interaction import RuntimePlanningInteraction, CopilotMessageRequest, PlannerAnswerRequest, CopilotPermissionRequest
from runtime.planning_operations import TaskOperationPreviewRequest, TaskOperationApplyRequest
from runtime.review import ReviewConflictError
from runtime import IdentityQueryService
from runtime.workspace import (
    MissionWorkspaceProjection,
    WorkspaceDiagnostic,
    WorkspaceEntryKind,
    WorkspaceRunSummary,
)
from support.stores.workflow_store import RuntimeRunRecordNotTerminalError
from runtime.live_events import RuntimeEventOverflow, runtime_event_broker
from contracts.runtime_events import RuntimeEvent
from components.attachments import AttachmentError
from contracts.attachments import InputAttachmentStatus
from app.api.agentos_contracts import (
    MissionResponse,
    OperationResponse,
    ReviewResponse,
    RunResponse,
    project_control_run,
)
from components.marketplace.contracts import CustomResourceRequest


logger = logging.getLogger(__name__)


class RunCancelRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', populate_by_name=True)
    expected_runtime_revision: int | None = Field(default=None, alias='expectedRuntimeRevision', strict=True, ge=0)


class WorkspaceFileSaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    path: str = Field(min_length=1, max_length=4096)
    content: str = Field(max_length=1_048_576)
    expected_version: str = Field(alias="expectedVersion", min_length=1, max_length=512)
    operation_id: str = Field(alias="operationId", pattern=r"^[a-zA-Z0-9_-]{16,80}$")


class MissionCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    domain: str = "general"
    intent: str = "general"
    workflow_id: str | None = Field(default=None, alias="workflowId")
    review_mode: Literal['auto', 'human_in_loop'] = Field(default="auto", alias="reviewMode")
    input: dict[str, Any] = Field(default_factory=dict)
    security_level: str = Field(default="internal", alias="securityLevel")
    priority: str = "normal"
    enabled_plugin_ids: list[str] | None = Field(default=None, alias="enabledPluginIds")
    material_refs: list[str] | None = Field(default=None, alias="materialRefs")
    attachment_ids: list[str] | None = Field(default=None, alias="attachmentIds")
    client_request_id: str | None = Field(default=None, alias="clientRequestId", max_length=200)
    semantics: MissionSemanticContent | None = None


class MissionRunCreateRequest(BaseModel):
    """Create another execution for an existing Mission without changing task identity."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    workflow_id: str | None = Field(default=None, alias="workflowId")
    review_mode: Literal['auto', 'human_in_loop'] = Field(default="auto", alias="reviewMode")
    input: dict[str, Any] = Field(default_factory=dict)
    enabled_plugin_ids: list[str] | None = Field(default=None, alias="enabledPluginIds")
    material_refs: list[str] | None = Field(default=None, alias="materialRefs")
    attachment_ids: list[str] | None = Field(default=None, alias="attachmentIds")
    client_request_id: str = Field(alias="clientRequestId", min_length=1, max_length=200)
    source_run_id: str = Field(alias="sourceRunId", min_length=1)
    rerun_reason: str = Field(alias="rerunReason", min_length=1, max_length=80)


class SingleStepRetryRequest(BaseModel):
    """Resume a failed ACG step in a successor or the current Run."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    client_request_id: str = Field(alias="clientRequestId", min_length=1, max_length=200)
    reason: str = Field(default="operator_requested", min_length=1, max_length=500)
    expected_runtime_revision: int | None = Field(
        default=None, alias="expectedRuntimeRevision", ge=0
    )
    mode: Literal["successor_run", "current_run"] = "successor_run"


class MaterialCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    content: str
    media_type: str = Field(default="text/plain", alias="mediaType", min_length=1)


class RemoteResourceObservationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    available_slots: int = Field(alias="availableSlots", ge=0)
    observation_sequence: int = Field(alias="observationSequence", ge=0)
    utilization: float = Field(ge=0.0, le=1.0)
    latency_ms: float | None = Field(default=None, alias="latencyMs", ge=0.0)
    observed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), alias="observedAt"
    )


class ResourceEnabledRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    enabled: bool


class MarketplaceInstallRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    catalog_id: str = Field(alias="catalogId", min_length=1, max_length=160)


class RemoteNodeObservationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    observation_sequence: int = Field(alias="observationSequence", ge=0)
    cpu_utilization: float = Field(default=0.0, alias="cpuUtilization", ge=0.0, le=1.0)
    gpu_utilization: float = Field(default=0.0, alias="gpuUtilization", ge=0.0, le=1.0)
    available_memory_mb: int = Field(default=0, alias="availableMemoryMb", ge=0)
    queued_tasks: int = Field(default=0, alias="queuedTasks", ge=0)
    latency_ms: float | None = Field(default=None, alias="latencyMs", ge=0.0)
    observed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), alias="observedAt"
    )


class RemoteResourceRegistrationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    profile: RuntimeProfile
    snapshot: RuntimeSnapshot
    registration_id: str | None = Field(default=None, alias="registrationId", min_length=1, max_length=300)


class NodeRegistrationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    profile: NodeProfile
    snapshot: NodeSnapshot
    registration_id: str | None = Field(default=None, alias="registrationId", min_length=1, max_length=300)


class ReviewApplyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    step_id: str = Field(alias="stepId", min_length=1)
    decision: ReviewDecisionType
    reviewer: str = "system"
    comment: str = Field(default="", max_length=2000)
    operation_id: str = Field(alias="operationId", min_length=1)
    expected_run_updated_at: datetime | None = Field(
        default=None, alias="expectedRunUpdatedAt"
    )
    expected_step_status: StepStatus | None = Field(
        default=None, alias="expectedStepStatus"
    )


class EvolutionRollbackRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    target_version: int = Field(alias="targetVersion", ge=0)
    reviewer: str = Field(min_length=1)


class EvolutionApprovalRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    reviewer: str = Field(min_length=1)


_SENSITIVE_KEYS = (
    "authorization", "password", "secret", "token", "cookie", "api_key",
    "apikey", "prompt", "arguments", "response", "content", "input",
)


def _redact(value: Any, *, depth: int = 0) -> Any:
    if depth > 6:
        return "[truncated]"
    if isinstance(value, dict):
        return {
            str(key): (
                "[redacted]"
                if any(marker in str(key).lower().replace("-", "_") for marker in _SENSITIVE_KEYS)
                else _redact(item, depth=depth + 1)
            )
            for key, item in list(value.items())[:100]
        }
    if isinstance(value, list):
        return [_redact(item, depth=depth + 1) for item in value[:100]]
    if isinstance(value, str):
        return value[:2000]
    return value


def _actor_input(payload: dict[str, Any]) -> dict[str, Any]:
    actor = current_trusted_user()
    if actor is None:
        return dict(payload)
    result = {
        **payload,
        "authenticatedUserId": actor.user_id,
        "authenticatedSubject": actor.subject,
        "authenticatedRole": actor.role,
    }
    if actor.tenant_id:
        result["authenticatedTenantId"] = actor.tenant_id
    else:
        result.pop("authenticatedTenantId", None)
    return result


def _csv_values(value: str | None) -> tuple[str, ...] | None:
    values = tuple(dict.fromkeys(item.strip() for item in (value or "").split(",") if item.strip()))
    return values or None


def _declared_capability_hint(runtime: ExecutionRuntime) -> dict[str, Any] | None:
    """零调用阶段从运行时声明的模型能力推导资源横幅提示。

    历史缺陷：capability 仅从已完成调用的审计投影取值，任务开始时前端只能
    显示“API 未声明”。此回退读取注入的模型运行时静态登记（catalog 声明），
    让模型名/策略/上下文窗口在第一个调用发生前就可见。
    """
    guarded = getattr(runtime, "_model_runtime", None)
    describer = getattr(guarded, "describe_model", None)
    if not callable(describer):
        inner = getattr(guarded, "delegate", None)
        describer = getattr(inner, "describe_model", None)
    if not callable(describer):
        return None
    try:
        envelope = describer()
    except Exception:
        logger.warning("declared capability lookup failed", exc_info=True)
        return None
    data = (
        envelope.model_dump(by_alias=True, mode="json", exclude_none=True)
        if hasattr(envelope, "model_dump")
        else None
    )
    if not isinstance(data, dict) or not (data.get("model") or data.get("provider")):
        return None
    return data


def _require_access(run: RuntimeRunRecord) -> None:
    owner = str(run.input.get("authenticatedUserId") or "")
    if not owner:
        return
    actor = current_trusted_user()
    tenant = str(run.input.get("authenticatedTenantId") or "")
    if actor is None or actor.user_id != owner or (tenant and actor.tenant_id != tenant):
        raise HTTPException(status_code=404, detail="run not found")


def _identity_run_deleted(run: Any) -> bool:
    """Identity 侧 Run 的软删除标记存于 metadata；与 runtime 的 recordState 语义一致。"""
    metadata = getattr(run, "metadata", None)
    return isinstance(metadata, dict) and metadata.get("recordState") == "deleted"


def _state(run: RuntimeRunRecord) -> dict[str, Any]:
    raw = run.execution_state if isinstance(run.execution_state, dict) else {}
    allowed = (
        "graphId", "graphVersion", "checkpointId", "outputRefs", "contextRefs",
        "memoryRefs", "phaseCapsuleRefs", "traceRefs", "provenanceRefs", "graphPatchRefs",
        "outputSummaries", "resourceBindings", "bindingHistory",
        "bindingRequirements", "executionBindings", "schedulingDecisions",
        "evolutionPolicyVersion", "parentRunId", "sourceRunId", "rerunReason",
        "supersedesRunId", "supersededByRunId", "sourcePatchId",
        "consensusResults", "controlFrames", "loopIterations",
        "loopPaths", "debateSessions", "recoveryOutcome", "singleStepRetry",
        "retryTargetStepId", "reusedStepIds",
    )
    state = {key: raw[key] for key in allowed if key in raw}
    review_payload = raw.get("reviewPayload")
    if isinstance(review_payload, dict):
        review_fields = {
            "subjectType", "subjectId", "stepId", "controlId", "reasonCode",
            "iteration", "votes", "approvals", "committedParticipants", "quorum",
            "accepted", "strategy", "auditDecisionRef", "auditOutcome", "traceRef",
        }
        state["reviewPayload"] = {
            key: review_payload[key]
            for key in review_fields
            if review_payload.get(key) is not None
        }
    return state


_HISTORY_INPUT_KEYS = (
    "taskName", "taskGoal", "userIntent", "materialText", "materialIds", "materialRefs",
    "attachmentIds", "inputAttachments", "constraints",
    "expectedArtifacts", "planningMode", "planningDiversity", "planningSeed", "webSearchEnabled",
    "capabilityProfile",
    "thinkingMode", "pluginData", "contractText", "contractType", "legalReviewGoal",
    "evidenceFirst", "riskParallel", "conservativeReview",
)


def _history_value(value: Any) -> Any:
    if isinstance(value, str):
        return value
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return value
    if isinstance(value, list):
        return [_history_value(item) for item in value[:100] if isinstance(item, (str, int, float, bool, dict, list))]
    if isinstance(value, dict):
        return {
            str(key): _history_value(item)
            for key, item in list(value.items())[:100]
            if not any(marker in str(key).lower().replace("-", "_") for marker in _SENSITIVE_KEYS)
        }
    return None


def _usage_number(usage: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = usage.get(key)
        if isinstance(value, (int, float)) and value >= 0:
            return int(value)
    return 0


def _context_pack_summary(step_id: str, context_ref: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    """Project ContextPack metadata without returning the model input body."""
    if not isinstance(payload, dict):
        return {
            "stepId": step_id,
            "contextRef": context_ref,
            "available": False,
        }

    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    source_data = payload.get("sourceData") if isinstance(payload.get("sourceData"), dict) else {}

    def string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value[:100] if isinstance(item, str)]

    def bounded_string(value: Any) -> str:
        return str(value or "")[:500]

    def non_negative_int(value: Any) -> int:
        return int(value) if isinstance(value, (int, float)) and value >= 0 else 0

    saving_ratio = payload.get("savingRatio")
    if not isinstance(saving_ratio, (int, float)):
        saving_ratio = 0.0

    return {
        "stepId": step_id,
        "contextRef": context_ref,
        "available": True,
        "objective": bounded_string(payload.get("objective")),
        "stepGoal": bounded_string(payload.get("stepGoal")),
        "sourceStepIds": string_list(payload.get("sourceStepIds")),
        "evidenceRefs": string_list(payload.get("evidenceRefs")),
        "missingFields": string_list(payload.get("missingFields")),
        "contractStatus": bounded_string(payload.get("contractStatus") or "unknown"),
        "tokensDelivered": non_negative_int(payload.get("tokensDelivered")),
        "tokensAvailable": non_negative_int(payload.get("tokensAvailable")),
        "savingRatio": float(saving_ratio),
        "fieldCount": len(data),
        "sourceCount": len(source_data),
        "dataKeys": [str(key) for key in list(data)[:100]],
        "sourceDataKeys": [str(key) for key in list(source_data)[:100]],
    }


_RUNTIME_KIND_TO_LEGACY_TYPE = {
    "execution_backend": "worker",
    "model_server": "model",
    "tool_service": "tool",
}


def _project_runtime_profile(profile: RuntimeProfile, node: NodeProfile | None = None) -> dict[str, Any]:
    """把 Runtime 画像投影为资源中心既有行形状（resourceType/deploymentTier）。"""
    compute = (
        node.compute.model_dump(by_alias=True, mode="json")
        if node is not None
        else {}
    )
    return {
        "resourceId": profile.runtime_id,
        "resourceType": _RUNTIME_KIND_TO_LEGACY_TYPE.get(profile.kind.value, "worker"),
        "runtimeKind": profile.kind.value,
        "displayName": profile.display_name,
        "deploymentTier": profile.placement.value,
        "capabilities": list(profile.capabilities),
        "domains": list(profile.domains),
        "labels": dict(profile.labels),
        "location": profile.location,
        "dataZone": profile.data_zone,
        "costMetadata": dict(profile.cost_metadata),
        "capacity": profile.capacity,
        "ownerScope": profile.owner_scope,
        "provider": profile.provider,
        "sourceType": profile.source_type,
        "adapter": profile.adapter,
        "privacyLevel": None,
        "executionEndpoint": (
            profile.endpoint.model_dump(by_alias=True, mode="json")
            if profile.endpoint is not None
            else None
        ),
        "computeCapacity": compute,
        "modelIds": list(profile.model_ids),
        "enabled": profile.enabled,
        "metadata": dict(profile.metadata),
        "version": profile.version,
        "nodeId": profile.node_id,
        "trust": profile.trust.value,
    }


def _project_model_endpoint(endpoint, host_runtime: RuntimeProfile | None = None) -> dict[str, Any]:
    """把模型端点投影为资源中心的 model 行；与执行后端行并列展示。"""
    capabilities = ["model.generate"]
    features = endpoint.features.model_dump(by_alias=True)
    capabilities.extend(sorted(key for key, value in features.items() if value is True))
    return {
        "resourceId": endpoint.endpoint_id,
        "resourceType": "model",
        "runtimeKind": "model_endpoint",
        "displayName": endpoint.model,
        "hostRuntimeId": endpoint.runtime_id,
        "provider": endpoint.provider,
        "sourceType": endpoint.source_type,
        "adapter": endpoint.adapter,
        "model": endpoint.model,
        "contextWindowTokens": endpoint.context_window_tokens,
        "maxOutputTokens": endpoint.max_output_tokens,
        "deploymentTier": endpoint.placement.value,
        "capabilities": capabilities,
        "domains": [],
        "labels": dict(endpoint.labels),
        "location": None,
        "dataZone": None,
        "costMetadata": dict(endpoint.cost_metadata),
        "capacity": 1,
        # Runtime 承载端点以宿主归属为权威；注册表共享端点则显式保留自身归属。
        "ownerScope": host_runtime.owner_scope if host_runtime is not None else endpoint.owner_scope,
        "privacyLevel": None,
        "executionEndpoint": None,
        "computeCapacity": {},
        "modelIds": [endpoint.model],
        "enabled": endpoint.enabled,
        "metadata": {
            **dict(endpoint.metadata),
            "provider": endpoint.provider,
            "model": endpoint.model,
            "modelVersion": endpoint.model_version,
            "contextWindowTokens": endpoint.context_window_tokens,
            "maxOutputTokens": endpoint.max_output_tokens,
            "features": features,
            "tier": endpoint.tier,
        },
        "version": endpoint.version,
        "nodeId": None,
        "trust": None,
    }


def _model_call_projection(run: RuntimeRunRecord) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for event in run.trace:
        event_type = getattr(event.event_type, "value", event.event_type)
        if event_type != "model_called":
            continue
        payload = dict(event.payload) if isinstance(event.payload, dict) else {}
        usage = dict(payload.get("usage") or {})
        prompt_details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}
        completion_details = usage.get("completion_tokens_details") or usage.get("output_tokens_details") or {}
        input_tokens = _usage_number(usage, "input_tokens", "prompt_tokens", "inputTokens")
        output_tokens = _usage_number(usage, "output_tokens", "completion_tokens", "outputTokens")
        cache_read = _usage_number(
            usage, "cache_read_tokens", "cache_read_input_tokens", "cached_tokens", "cacheReadTokens"
        ) or _usage_number(prompt_details if isinstance(prompt_details, dict) else {}, "cached_tokens")
        cache_write = _usage_number(
            usage, "cache_write_tokens", "cache_creation_input_tokens", "cacheWriteTokens"
        )
        reasoning = _usage_number(usage, "reasoning_tokens", "reasoningTokens") or _usage_number(
            completion_details if isinstance(completion_details, dict) else {}, "reasoning_tokens"
        )
        capability = payload.get("capability") if isinstance(payload.get("capability"), dict) else None
        output_policy = str(payload.get("outputPolicy") or "api_controlled").strip().lower()
        context_window = (
            capability.get("contextWindowTokens") if isinstance(capability, dict) else None
        )
        context_pressure = (
            min(1.0, input_tokens / int(context_window))
            if isinstance(context_window, int) and context_window > 0
            else None
        )
        calls.append({
            "callId": event.event_id,
            "stepId": event.step_id,
            "provider": payload.get("provider"),
            "model": payload.get("model"),
            "createdAt": event.created_at,
            "latencyMs": int(payload.get("latencyMs") or 0),
            "usage": {
                "inputTokens": input_tokens,
                "outputTokens": output_tokens,
                "cacheReadTokens": cache_read,
                "cacheWriteTokens": cache_write,
                "reasoningTokens": reasoning,
                "totalTokens": _usage_number(usage, "total_tokens", "totalTokens") or input_tokens + output_tokens,
            },
            "finishReason": payload.get("finishReason"),
            "outputPolicy": output_policy,
            "requestedOutputTokens": payload.get("requestedOutputTokens"),
            "effectiveOutputTokens": payload.get("effectiveOutputTokens"),
            "effectiveReason": payload.get("effectiveReason"),
            "outputExhausted": bool(payload.get("outputExhausted")),
            "partIndex": payload.get("partIndex"),
            "callChainId": payload.get("callChainId"),
            "capability": capability,
            "contextPressure": context_pressure,
        })
    return calls


def project_history_config(
    run: RuntimeRunRecord,
    *,
    title: str | None = None,
) -> dict[str, Any]:
    """Return only the owner-visible configuration needed to reopen a historical workbench."""
    raw = run.input if isinstance(run.input, dict) else {}
    return {
        "runId": run.run_id,
        "title": title or str(raw.get("taskName") or ""),
        "reviewMode": run.review_mode,
        "enabledPluginIds": list(run.enabled_plugin_ids),
        "input": {
            key: _history_value(raw[key])
            for key in _HISTORY_INPUT_KEYS
            if key in raw
        },
    }


def _legacy_provenance_items(value: Any, allowed: set[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        {key: _redact(item[key]) for key in allowed if key in item}
        for item in value[:100]
        if isinstance(item, dict)
    ]


def project_run(run: RuntimeRunRecord, *, title: str | None = None) -> dict[str, Any]:
    """Project lifecycle and references without task input or output bodies."""
    state = _state(run)
    return {
        "runId": run.run_id,
        "missionId": run.mission_id,
        "title": title,
        "workflowId": run.workflow_id,
        "domain": run.domain,
        "source": str(run.input.get("source") or "") or None,
        "runtimeEngine": run.runtime_engine,
        "status": run.status.value,
        "lifecyclePhase": run.lifecycle_phase.value if run.lifecycle_phase else None,
        "lifecycleMessage": run.lifecycle_message,
        "currentStepId": run.current_step_id,
        "completedStepIds": list(run.completed_step_ids),
        "activeStepIds": list(run.active_step_ids),
        "skippedStepIds": list(run.execution_state.get("skippedStepIds") or []),
        "outputRef": run.output.get("outputRef") if isinstance(run.output, dict) else None,
        "runtimeRevision": run.runtime_revision,
        "executionState": state,
        "steps": [
            {
                "stepId": step.step_id,
                "name": step.name,
                "agentName": step.agent_name,
                "capability": step.capability,
                "status": step.status.value,
                "attempt": step.attempt,
                "retryCount": step.retry_count,
                "reviewRequired": step.requires_review,
                "outputRef": (state.get("outputRefs") or {}).get(step.step_id),
                "outputSummary": (state.get("outputSummaries") or {}).get(step.step_id, ""),
                "startedAt": step.started_at,
                "completedAt": step.completed_at,
            }
            for step in run.steps
        ],
        "createdAt": run.created_at,
        "updatedAt": run.updated_at,
        "startedAt": run.started_at,
    }


def project_graph(run: RuntimeRunRecord) -> dict[str, Any]:
    blueprint = dict(run.acg_blueprint or {})
    state = _state(run)
    return {
        "runId": run.run_id,
        "graphId": blueprint.get("graphId") or state.get("graphId"),
        "graphVersion": blueprint.get("version") or state.get("graphVersion"),
        "nodes": list(blueprint.get("nodes") or []),
        "edges": list(blueprint.get("edges") or []),
        "completedStepIds": list(run.completed_step_ids),
        "activeStepIds": list(run.active_step_ids),
        "skippedStepIds": list(run.execution_state.get("skippedStepIds") or []),
        "graphPatchRefs": list(state.get("graphPatchRefs") or []),
        "resourceBindings": dict(state.get("resourceBindings") or {}),
    }


def _idempotency(request: MissionCreateRequest | MissionRunCreateRequest) -> tuple[str | None, str | None]:
    if not request.client_request_id:
        return None, None
    actor = current_trusted_user()
    caller = f"{getattr(actor, 'tenant_id', '')}:{getattr(actor, 'user_id', '')}" if actor else "internal"
    key = hashlib.sha256(f"{caller}:agentos-v2:{request.client_request_id}".encode()).hexdigest()
    body = request.model_dump(by_alias=True, mode="json", exclude={"client_request_id"})
    if isinstance(request, MissionCreateRequest) and request.semantics is None:
        body.pop("semantics", None)  # Preserve pre-S00-03 legacy fingerprints.
    fingerprint = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return key, fingerprint


def _single_step_retry_idempotency(
    run_id: str,
    step_id: str,
    request: SingleStepRetryRequest,
) -> tuple[str, str]:
    actor = current_trusted_user()
    caller = f"{getattr(actor, 'tenant_id', '')}:{getattr(actor, 'user_id', '')}" if actor else "internal"
    key = hashlib.sha256(
        f"{caller}:agentos-v2:single-step-retry:{run_id}:{step_id}:{request.client_request_id}".encode()
    ).hexdigest()
    body = {
        "runId": run_id,
        "stepId": step_id,
        **request.model_dump(by_alias=True, mode="json", exclude={"client_request_id"}),
    }
    fingerprint = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return key, fingerprint


def create_router(
    runtime: ExecutionRuntime,
    coordinator: RunExecutionCoordinator,
) -> APIRouter:
    router = APIRouter(prefix="/agentos/v2")
    router.include_router(create_c2_router(runtime, coordinator))
    interaction = RuntimePlanningInteraction(runtime)
    identity_adapter = getattr(runtime, "identity_lifecycle", None)
    identity_repositories = getattr(identity_adapter, "repositories", None)
    identity_queries = (
        IdentityQueryService(
            identity_repositories,
            getattr(runtime, "content_manifest_store", None),
        )
        if identity_repositories is not None
        else None
    )

    def require_identity_queries() -> IdentityQueryService:
        if identity_queries is None:
            raise HTTPException(status_code=503, detail="identity query source unavailable")
        return identity_queries

    def require_mission_owner_access(mission_id: str):
        require_identity_queries()
        mission = identity_repositories.missions.get(mission_id)
        if mission is None:
            raise HTTPException(status_code=404, detail="mission not found")
        actor = current_trusted_user()
        tenant = str(mission.metadata.get("tenantId") or "")
        if actor is not None and (
            mission.user_id != actor.user_id
            or (tenant and tenant != actor.tenant_id)
        ):
            raise HTTPException(status_code=404, detail="mission not found")
        return mission

    def require_mission_access(mission_id: str):
        query = require_identity_queries()
        require_mission_owner_access(mission_id)
        try:
            detail = query.get_mission(mission_id)
        except EntityNotFoundError as exc:
            raise HTTPException(status_code=404, detail="mission not found") from exc
        return detail

    def require_run_access(run_id: str):
        query = require_identity_queries()
        run = identity_repositories.runs.get(run_id)
        if run is None or _identity_run_deleted(run):
            raise HTTPException(status_code=404, detail="run not found")
        require_mission_owner_access(run.mission_id)
        return query, run

    def require_run_write_scope(run):
        # Reuse current Mission write authority, not the last UI offer.
        mission = runtime.workflow_store.get_mission(run.mission_id)
        if mission.record_state != MissionRecordState.ACTIVE:
            raise HTTPException(409, 'Mission is not active')
        semantic = getattr(runtime, 'mission_semantic_service', None)
        if semantic:
            principal = current_semantic_principal()
            if principal is None:
                raise HTTPException(403, 'trusted principal required')
            try:
                semantic.require_write_access(principal, run.mission_id)
            except PermissionError as exc:
                raise HTTPException(403, 'semantic access denied') from exc

    def load_run(run_id: str, *, readonly: bool = False, mutable: bool = False, write: bool = False) -> RuntimeRunRecord:
        try:
            read = runtime.workflow_store.get_run if mutable else (
                getattr(runtime, "get_status_cached", runtime.get_status) if readonly else runtime.get_status)
            run = read(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc
        _require_access(run)
        if run.record_state is RunRecordState.DELETED:
            raise HTTPException(status_code=404, detail="run not found")
        if mutable or write:
            require_run_write_scope(run)
        if mutable:
            try:
                assert_mutable_run(run)
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        return run

    def require_current_mission_read(mission_id: str, *, required: bool = False):
        """Use the formal authority on every read; never cache a grant here."""
        service = getattr(runtime, "mission_semantic_service", None)
        if service is None:
            if required:
                raise HTTPException(status_code=503, detail="mission semantic source unavailable")
            return None  # Existing, non-semantic legacy hosts retain their contract.
        principal = current_semantic_principal()
        if principal is None:
            raise HTTPException(status_code=403, detail="trusted semantic principal is required")
        try:
            snapshot = service.get_effective_snapshot(principal, mission_id)
            mission = runtime.workflow_store.get_mission(mission_id)
            if mission.record_state is MissionRecordState.DELETED:
                raise HTTPException(status_code=404, detail="mission not found")
            return snapshot, mission
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail="semantic access denied") from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="mission not found") from exc
        except (ValueError, RuntimeError, SQLiteError, AttributeError, TypeError) as exc:
            raise HTTPException(status_code=503, detail="mission semantic source unavailable") from exc

    def load_content_run(run_id: str) -> RuntimeRunRecord:
        run = load_run(run_id, readonly=True)
        require_current_mission_read(
            run.mission_id, required="missionIntentBasis" in run.execution_state,
        )
        return run

    def project(run: RuntimeRunRecord) -> dict[str, Any]:
        try:
            title = runtime.workflow_store.get_mission(run.mission_id).title
        except KeyError:
            title = None
        result = project_run(run, title=title)
        if identity_queries is not None:
            identity_run = identity_repositories.runs.get(run.run_id)
            if identity_run is not None:
                result["identity"] = {
                    "source": "agentos-v2",
                    "blueprintId": identity_run.blueprint_id,
                    "graphVersion": identity_run.graph_version,
                    "status": identity_run.status.value,
                }
        return result

    def require_manifest_access(manifest_id: str):
        try:
            manifest = runtime.content_manifest_store.get_manifest(manifest_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="content manifest not found") from exc
        actor = current_trusted_user()
        if manifest.owner_type == "user" and actor is not None and manifest.owner_id != actor.user_id:
            raise HTTPException(status_code=404, detail="content manifest not found")
        if manifest.owner_type == "run":
            run = load_content_run(manifest.owner_id)
            if identity_repositories is not None:
                identity_run = identity_repositories.runs.get(run.run_id)
                if identity_run is not None:
                    from runtime.workspace import artifact_is_public
                    for binding in identity_repositories.run_artifact_bindings.list_for_run(run.run_id):
                        artifact = identity_repositories.artifacts.get(binding.artifact_id)
                        if artifact is not None and artifact.content_ref == manifest_id:
                            if not artifact_is_public(identity_run, artifact):
                                raise HTTPException(status_code=404, detail="content manifest not found")
                            return manifest
            # The content store can seal bytes before the Identity outbox is
            # projected. A formal manual-review Run cannot use that raw-content
            # fallback to publish an unapproved final during the projection gap.
            if (run.review_mode == 'human_in_loop' and run.execution_state.get('planningCommitRequired')
                    and run.status is not WorkflowStatus.COMPLETED):
                raise HTTPException(status_code=404, detail="content manifest not found")
        return manifest

    def project_identity_artifact(detail: Any) -> dict[str, Any]:
        """Join a V2 RunArtifactBinding with its sealed ContentManifest metadata."""
        artifact = detail.artifact
        try:
            manifest = runtime.content_manifest_store.get_manifest(artifact.content_ref)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="artifact content not found") from exc
        if manifest.kind is not ContentKind.ARTIFACT or not manifest.sealed:
            raise HTTPException(status_code=404, detail="artifact content not found")
        if manifest.owner_type != "run" or manifest.owner_id != artifact.origin_run_id:
            raise HTTPException(status_code=404, detail="artifact content not found")
        load_content_run(manifest.owner_id)
        return {
            **manifest.model_dump(by_alias=True, mode="json"),
            **artifact.model_dump(by_alias=True, mode="json"),
            **detail.binding.model_dump(by_alias=True, mode="json"),
            "manifestId": artifact.content_ref,
        }

    def require_resource_operator(owner_scope: str) -> None:
        actor = current_trusted_user()
        if actor is None:
            raise HTTPException(status_code=401, detail="trusted operator context required")
        if actor.role.strip().lower() not in {"admin", "operator", "system"}:
            raise HTTPException(status_code=403, detail="resource registration requires operator role")
        if actor.tenant_id and actor.tenant_id != owner_scope:
            raise HTTPException(status_code=403, detail="resource owner scope does not match operator tenant")

    def prepare_execution_input(
        payload: dict[str, Any],
        material_refs: list[str] | None,
        attachment_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Resolve actor ownership and sealed materials for a Mission or Run command."""
        if any(key in payload for key in ('workspaceBinding', 'allowedRoot', 'grantId', 'workspaceId', 'resourceId', 'securityProfile')):
            raise HTTPException(status_code=422, detail='Workspace authority cannot be supplied as input')
        if runtime.mission_semantic_service is not None and current_semantic_principal() is None:
            raise HTTPException(status_code=403, detail="trusted semantic principal is required")
        if any(key in payload for key in ("missionIntentBasis", "missionIntentBasisRef", "semanticPrincipal", "inheritParentBasis")):
            raise HTTPException(status_code=422, detail="semantic control fields cannot be supplied as input")
        if runtime.planning_commit_authority is not None and any(key in payload for key in (
            "principal", "executionPermit", "executionPermitId", "graphActivation", "graphId", "graphVersion",
            "executionReceipt", "executionState", "planningCommitRequired", "compiledACGPackage", "handoffId",
        )):
            raise HTTPException(status_code=422, detail="C2 control fields cannot be supplied as input")
        execution_input = _actor_input(payload)
        refs = list(dict.fromkeys([
            *(material_refs or []),
            *(execution_input.get("materialRefs") or []),
        ]))
        requested_attachments = list(dict.fromkeys([
            *(attachment_ids or []),
            *(execution_input.get("attachmentIds") or []),
        ]))
        if requested_attachments:
            attachment_service = getattr(runtime, "attachment_service", None)
            if attachment_service is None:
                raise AttachmentError(
                    "UPLOAD_FAILED", "attachment service is unavailable", status_code=503
                )
            actor = current_trusted_user()
            owner_user_id = actor.user_id if actor is not None else "internal"
            attachments = [
                attachment_service.get(item, owner_user_id=owner_user_id)
                for item in requested_attachments
            ]
            failed = [item for item in attachments if item.status is InputAttachmentStatus.FAILED]
            if failed:
                raise AttachmentError(
                    "PARSING_FAILED", "one or more attachments failed parsing", status_code=422
                )
            not_ready = [
                item.attachment_id for item in attachments
                if item.status is not InputAttachmentStatus.READY or not item.extracted_content_ref
            ]
            if not_ready:
                raise AttachmentError(
                    "ATTACHMENT_NOT_READY", "attachment is not ready", status_code=409
                )
            if attachment_service.limits.max_total_bytes is not None and sum(item.size_bytes for item in attachments) > attachment_service.limits.max_total_bytes:
                raise AttachmentError(
                    "ATTACHMENT_CONTEXT_TOO_LARGE",
                    "total attachment size exceeds the configured Mission limit",
                    status_code=413,
                )
            refs.extend(str(item.extracted_content_ref) for item in attachments)
            execution_input["attachmentIds"] = requested_attachments
            execution_input["inputAttachments"] = [
                {
                    "attachmentId": item.attachment_id,
                    "filename": item.original_filename,
                    "mimeType": item.mime_type,
                    "extension": item.extension,
                    "sizeBytes": item.size_bytes,
                    "sha256": item.sha256,
                    "status": item.status.value,
                    "materialRef": item.extracted_content_ref,
                    "characterCount": item.character_count,
                    "parser": item.parser,
                }
                for item in attachments
            ]
        inline_material = execution_input.pop("materialText", None)
        if isinstance(inline_material, str) and inline_material:
            actor = current_trusted_user()
            inline_manifest = runtime.content_manifest_store.create_from_bytes(
                content=inline_material.encode("utf-8"),
                kind=ContentKind.MATERIAL,
                owner_type="user",
                owner_id=(actor.user_id if actor is not None else "internal"),
                media_type="text/plain",
            )
            refs.append(inline_manifest.manifest_id)
        for manifest_id in refs:
            manifest = require_manifest_access(manifest_id)
            if manifest.kind is not ContentKind.MATERIAL or not manifest.sealed:
                raise ValueError("materialRefs must reference sealed material manifests")
        if refs:
            execution_input["materialRefs"] = list(dict.fromkeys(refs))
            execution_input["sourceMaterials"] = [
                runtime.content_manifest_store.get_manifest(item).model_dump(
                    by_alias=True, mode="json"
                )
                for item in execution_input["materialRefs"]
            ]
        return execution_input

    @router.post("/materials", status_code=status.HTTP_201_CREATED)
    async def create_material(request: MaterialCreateRequest):
        actor = current_trusted_user()
        manifest = runtime.content_manifest_store.create_from_bytes(
            content=request.content.encode("utf-8"),
            kind=ContentKind.MATERIAL,
            owner_type="user",
            owner_id=(actor.user_id if actor is not None else "internal"),
            media_type=request.media_type,
        )
        return manifest.model_dump(by_alias=True, mode="json")

    def attachment_projection(attachment: Any) -> dict[str, Any]:
        projected = attachment.model_dump(
            by_alias=True,
            mode="json",
            exclude={"owner_user_id", "owner_tenant_id", "storage_key"},
        )
        projected["filename"] = attachment.original_filename
        if attachment.status is InputAttachmentStatus.FAILED:
            projected["errorCode"] = "PARSING_FAILED"
        return projected

    @router.post("/attachments", status_code=status.HTTP_201_CREATED)
    async def upload_attachment(file: UploadFile = File(...)):
        service = getattr(runtime, "attachment_service", None)
        if service is None:
            raise HTTPException(status_code=503, detail={"code": "UPLOAD_FAILED", "message": "attachment service is unavailable"})
        actor = current_trusted_user()
        owner_user_id = actor.user_id if actor is not None else "internal"
        try:
            content = await file.read(
                service.limits.max_file_bytes + 1
                if service.limits.max_file_bytes is not None else -1
            )
            attachment = service.upload(
                content=content,
                filename=file.filename or "",
                mime_type=file.content_type,
                owner_user_id=owner_user_id,
                owner_tenant_id=(actor.tenant_id if actor is not None else None),
            )
            return attachment_projection(attachment)
        except AttachmentError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail={"code": exc.code, "message": str(exc)},
            ) from exc
        finally:
            await file.close()

    @router.get("/attachments/{attachment_id}")
    async def get_attachment(attachment_id: str):
        service = getattr(runtime, "attachment_service", None)
        if service is None:
            raise HTTPException(status_code=503, detail={"code": "UPLOAD_FAILED", "message": "attachment service is unavailable"})
        actor = current_trusted_user()
        try:
            attachment = service.get(
                attachment_id,
                owner_user_id=(actor.user_id if actor is not None else "internal"),
            )
            return attachment_projection(attachment)
        except AttachmentError as exc:
            raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)}) from exc

    @router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_attachment(attachment_id: str):
        service = getattr(runtime, "attachment_service", None)
        if service is None:
            raise HTTPException(status_code=503, detail={"code": "UPLOAD_FAILED", "message": "attachment service is unavailable"})
        actor = current_trusted_user()
        try:
            service.delete(
                attachment_id,
                owner_user_id=(actor.user_id if actor is not None else "internal"),
            )
        except AttachmentError as exc:
            raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)}) from exc

    @router.get("/materials/{manifest_id}")
    async def get_material(manifest_id: str):
        manifest = require_manifest_access(manifest_id)
        return manifest.model_dump(by_alias=True, mode="json")

    @router.get("/identity/health")
    async def get_identity_health():
        require_identity_queries()
        projection_stats = identity_repositories.projection_events.stats()
        inbox_stats = identity_repositories.inbox_events.stats()
        startup = getattr(runtime, "identity_reconciliation_report", None)
        startup_failures = list(getattr(startup, "failures", []) or [])
        backlog_count = (
            projection_stats["backlog"]
            + inbox_stats["backlog"]
            + int(getattr(startup, "outbox_backlog", 0) or 0)
        )
        failed_count = (
            projection_stats["failed"]
            + inbox_stats["failed"]
            + int(getattr(startup, "outbox_failed_count", 0) or 0)
        )
        timestamps = [
            value for value in (
                projection_stats["oldestEventAt"],
                inbox_stats["oldestEventAt"],
                getattr(startup, "oldest_event_at", None),
            )
            if value is not None
        ]
        return {
            "status": "healthy" if not backlog_count and not failed_count and not startup_failures else "degraded",
            "source": "agentos-v2",
            "backlogCount": backlog_count,
            "failedCount": failed_count,
            "oldestEventAt": min(timestamps) if timestamps else None,
            "unappliedEventCount": projection_stats["backlog"],
            "inboxBacklog": inbox_stats["backlog"],
            "outboxBacklog": int(getattr(startup, "outbox_backlog", 0) or 0),
            "startupReconciliation": {
                "examinedMissions": int(getattr(startup, "examined_tasks", 0) or 0),
                "examinedRuns": int(getattr(startup, "examined_runs", 0) or 0),
                "repairedMissions": int(getattr(startup, "repaired_tasks", 0) or 0),
                "repairedRuns": int(getattr(startup, "repaired_runs", 0) or 0),
                "replayedEvents": int(getattr(startup, "replayed_events", 0) or 0),
                "failureCount": len(startup_failures),
            },
        }

    @router.get("/resources")
    async def get_resources():
        """Return the ResourcePlane's runtime and model-endpoint catalog.

        This is a read-only system projection.  In particular, the persisted
        snapshot health is deliberately returned as-is: the API must not turn
        resource registration or scheduler eligibility into an ``online`` or
        ``healthy`` claim.
        """
        plane = getattr(runtime, "resource_plane", None)
        if plane is None:
            raise HTTPException(status_code=503, detail="resource query source unavailable")

        items: list[dict[str, Any]] = []
        for profile in plane.runtimes():
            versioned = plane.runtime_snapshot(profile.runtime_id)
            health = plane.health_monitor.health(profile.runtime_id)
            health_status = (
                "online"
                if health.healthy
                else ("unknown" if health.last_heartbeat is None else "offline")
            )
            try:
                host_node = plane.node(profile.node_id)
            except KeyError:
                host_node = None
            items.append({
                "profile": _project_runtime_profile(profile, host_node),
                "snapshot": versioned.snapshot.model_dump(by_alias=True, mode="json"),
                "snapshotVersion": versioned.version,
                "health": {
                    "healthy": health.healthy,
                    "status": health_status,
                    "reliability": health.reliability,
                    "latencyMs": health.latency_ms,
                    "lastHeartbeat": (
                        health.last_heartbeat.isoformat()
                        if health.last_heartbeat is not None
                        else None
                    ),
                    "healthSource": type(plane.health_monitor.store).__name__,
                },
            })
        for endpoint in plane.model_endpoints():
            try:
                host_runtime = plane.runtime(endpoint.runtime_id) if endpoint.runtime_id else None
            except KeyError:
                host_runtime = None
            host_health = (
                plane.health_monitor.health(host_runtime.runtime_id)
                if host_runtime is not None else None
            )
            endpoint_status = (
                "online" if host_health is not None and host_health.healthy
                else ("offline" if host_health is not None and host_health.last_heartbeat is not None else "unknown")
            )
            if not endpoint.enabled or (host_runtime is not None and not host_runtime.enabled):
                endpoint_status = "offline"
            items.append({
                "profile": _project_model_endpoint(endpoint, host_runtime),
                "snapshot": {
                    "runtimeId": endpoint.endpoint_id,
                    "healthStatus": endpoint_status,
                    "availableSlots": 0 if endpoint.runtime_id else 1,
                    "utilization": 0.0,
                    "metrics": {},
                },
                "snapshotVersion": endpoint.version,
                "health": {
                    "healthy": endpoint_status == "online",
                    "status": endpoint_status,
                    "reliability": None,
                    "latencyMs": None,
                    "lastHeartbeat": None,
                    "healthSource": "model-endpoint-catalog",
                },
            })
        return {"items": items, "total": len(items)}

    def require_marketplace():
        marketplace = getattr(runtime, "marketplace_service", None)
        if marketplace is None:
            raise HTTPException(status_code=503, detail="resource marketplace unavailable")
        actor = current_trusted_user()
        if actor is None:
            raise HTTPException(status_code=401, detail="trusted user context required")
        owner_scope = str(actor.tenant_id or "local")
        return marketplace, owner_scope

    @router.get("/marketplace/catalog")
    async def list_marketplace_catalog():
        marketplace, _ = require_marketplace()
        return {
            "items": marketplace.public_catalog()
        }

    @router.get("/marketplace/installations")
    async def list_marketplace_installations():
        marketplace, owner_scope = require_marketplace()
        return {
            "items": [
                job.model_dump(by_alias=True, mode="json")
                for job in marketplace.list_installations(owner_scope)
            ]
        }

    @router.post("/marketplace/installations", status_code=status.HTTP_201_CREATED)
    async def install_marketplace_item(request: MarketplaceInstallRequest):
        marketplace, owner_scope = require_marketplace()
        require_resource_operator(owner_scope)
        try:
            job = await asyncio.to_thread(marketplace.install, catalog_id=request.catalog_id, owner_scope=owner_scope)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="marketplace item not found") from exc
        return job.model_dump(by_alias=True, mode="json")

    @router.post("/marketplace/installations/{job_id}/files")
    async def upload_marketplace_tool_file(job_id: str, file: UploadFile = File(...)):
        marketplace, owner_scope = require_marketplace()
        require_resource_operator(owner_scope)
        try:
            content = await file.read(20 * 1024 * 1024 + 1)
            return await asyncio.to_thread(marketplace.upload_tool_file, job_id, owner_scope=owner_scope, filename=file.filename, content=content)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="installation not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="file type, size or tool state invalid") from exc
        finally:
            await file.close()

    @router.post("/marketplace/installations/{job_id}/execute")
    async def execute_marketplace_tool(job_id: str, data: dict[str, Any]):
        marketplace, owner_scope = require_marketplace()
        require_resource_operator(owner_scope)
        try:
            return await asyncio.to_thread(marketplace.execute_tool, job_id, owner_scope=owner_scope, data=data)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="installation not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="tool input or state invalid") from exc

    @router.get("/marketplace/installations/{job_id}/files")
    async def download_marketplace_tool_file(job_id: str, path: str = Query(max_length=512)):
        marketplace, owner_scope = require_marketplace()
        require_resource_operator(owner_scope)
        try:
            content, name = await asyncio.to_thread(marketplace.download_tool_file, job_id, owner_scope=owner_scope, relative_path=path)
            return StreamingResponse(iter([content]), media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{name}"', "X-Content-Type-Options": "nosniff"})
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="installation not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="output file or tool state invalid") from exc

    @router.post("/marketplace/custom-resources", status_code=status.HTTP_201_CREATED)
    async def register_marketplace_custom_resource(request: CustomResourceRequest):
        marketplace, owner_scope = require_marketplace()
        require_resource_operator(owner_scope)
        try:
            job = marketplace.register_custom(request, owner_scope=owner_scope)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return job.model_dump(by_alias=True, mode="json")

    @router.post("/marketplace/installations/{job_id}/stop")
    async def stop_marketplace_installation(job_id: str):
        marketplace, owner_scope = require_marketplace()
        require_resource_operator(owner_scope)
        try:
            job = marketplace.stop(job_id, owner_scope=owner_scope)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="installation not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail="installation cannot be stopped") from exc
        return job.model_dump(by_alias=True, mode="json")

    @router.delete("/marketplace/installations/{job_id}")
    async def uninstall_marketplace_installation(job_id: str):
        marketplace, owner_scope = require_marketplace()
        require_resource_operator(owner_scope)
        try:
            job = marketplace.uninstall(job_id, owner_scope=owner_scope)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="installation not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail="installation cannot be removed") from exc
        return job.model_dump(by_alias=True, mode="json")

    @router.get("/resources/{resource_id}/usage")
    async def get_resource_usage(resource_id: str, limit: int = Query(default=12, ge=1, le=50)):
        """Return the resource's most recent attempt bindings from the identity graph.

        Read-only join over ``execution_bindings``/``attempts``: the catalog only
        answers "which attempt used this resource, when, with which agent/model".
        Run lifecycle detail stays owned by the run surfaces.
        """
        plane = getattr(runtime, "resource_plane", None)
        if plane is None:
            raise HTTPException(status_code=503, detail="resource query source unavailable")
        try:
            plane.runtime(resource_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="resource not found") from exc
        repositories = getattr(runtime, "identity_lifecycle", None)
        repositories = getattr(repositories, "repositories", None) if repositories is not None else None
        binding_repository = getattr(repositories, "execution_bindings", None) if repositories is not None else None
        list_for_resource = getattr(binding_repository, "list_for_resource", None)
        if list_for_resource is None:
            raise HTTPException(status_code=503, detail="resource usage source unavailable")
        records = list_for_resource(resource_id, limit=limit)
        return {
            "resourceId": resource_id,
            "items": [record.model_dump(by_alias=True, mode="json") for record in records],
            "total": len(records),
        }

    @router.get("/resources/{resource_id}/health-history")
    async def get_resource_health_history(resource_id: str, limit: int = Query(default=40, ge=1, le=200)):
        """Return the resource's persisted heartbeat/observation event history."""
        plane = getattr(runtime, "resource_plane", None)
        if plane is None:
            raise HTTPException(status_code=503, detail="resource query source unavailable")
        try:
            plane.runtime(resource_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="resource not found") from exc
        list_events = getattr(plane.health_monitor.store, "list_events", None)
        if list_events is None:
            raise HTTPException(status_code=503, detail="resource health history unavailable")
        events = list_events(resource_id, limit=limit)
        return {
            "resourceId": resource_id,
            "items": [
                {
                    "observedAt": (
                        event.updated_at.isoformat() if event.updated_at is not None else None
                    ),
                    "reliability": event.reliability,
                    "latencyMs": event.latency_ms,
                    "lastHeartbeat": (
                        event.last_heartbeat.isoformat()
                        if event.last_heartbeat is not None
                        else None
                    ),
                    "version": event.version,
                }
                for event in events
            ],
            "total": len(events),
        }

    @router.get("/resources/{resource_id}/credential")
    async def get_resource_credential(resource_id: str):
        """Return credential metadata only (id + age); never the secret material."""
        plane = getattr(runtime, "resource_plane", None)
        if plane is None:
            raise HTTPException(status_code=503, detail="resource credential source unavailable")
        try:
            plane.runtime(resource_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="resource not found") from exc
        try:
            record = plane.runtime_credential(resource_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="resource credential not found") from exc
        return {
            "resourceId": record.resource_id,
            "credentialId": record.credential_id,
            "createdAt": record.created_at.isoformat(),
        }

    @router.post("/resources/{resource_id}/enabled")
    async def set_resource_enabled(resource_id: str, request: ResourceEnabledRequest):
        """Toggle the resource's scheduling switch in the catalog and agent ledger."""
        plane = getattr(runtime, "resource_plane", None)
        if plane is None:
            raise HTTPException(status_code=503, detail="resource mutation source unavailable")
        try:
            profile = plane.runtime(resource_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="resource not found") from exc
        # 启停是本地调度管理动作，不涉及凭据签发：任何已认证用户可操作；
        # 凭据类动作（rotate/register）仍保持 operator 门槛。
        actor = current_trusted_user()
        if actor is None:
            raise HTTPException(status_code=401, detail="trusted user context required")
        if actor.tenant_id and actor.tenant_id != profile.owner_scope:
            raise HTTPException(status_code=403, detail="resource owner scope does not match operator tenant")
        try:
            updated = plane.set_runtime_enabled(resource_id, enabled=request.enabled)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="resource not found") from exc
        return {
            "resourceId": updated.runtime_id,
            "enabled": updated.enabled,
            "agentLedgerSynced": False,
        }

    @router.post("/resources/{resource_id}/probe")
    async def probe_resource(resource_id: str):
        """Actively refresh the wired local runtime's health projection on demand."""
        plane = getattr(runtime, "resource_plane", None)
        if plane is None:
            raise HTTPException(status_code=503, detail="resource probe source unavailable")
        if current_trusted_user() is None:
            raise HTTPException(status_code=401, detail="trusted user context required")
        local_resource = getattr(runtime, "local_runtime_resource", None)
        transport = getattr(runtime, "local_runtime_transport", None)
        projector = getattr(runtime, "local_runtime_health_projector", None)
        wired_profile = getattr(local_resource, "profile", None)
        wired_id = str(getattr(wired_profile, "runtime_id", "") or "")
        if not wired_id or resource_id != wired_id or transport is None or projector is None:
            raise HTTPException(
                status_code=409,
                detail="active probe is only supported for the wired local runtime resource",
            )
        healthy = await projector.refresh(transport)
        health = plane.health_monitor.health(resource_id)
        return {
            "resourceId": resource_id,
            "healthy": healthy,
            "reliability": health.reliability,
            "latencyMs": health.latency_ms,
            "lastHeartbeat": (
                health.last_heartbeat.isoformat() if health.last_heartbeat is not None else None
            ),
        }

    @router.get("/nodes")
    async def get_nodes():
        """Return the Node table's static profiles and last observations."""
        plane = getattr(runtime, "resource_plane", None)
        if plane is None:
            raise HTTPException(status_code=503, detail="node query source unavailable")
        items: list[dict[str, Any]] = []
        for profile in plane.nodes():
            versioned = plane.node_snapshot(profile.node_id)
            health = plane.node_health(profile.node_id)
            items.append({
                "profile": profile.model_dump(by_alias=True, mode="json"),
                "snapshot": versioned.snapshot.model_dump(by_alias=True, mode="json"),
                "snapshotVersion": versioned.version,
                "health": {
                    "status": health.status.value,
                    "lastHeartbeat": (
                        health.last_heartbeat.isoformat()
                        if health.last_heartbeat is not None
                        else None
                    ),
                    "consecutiveFailures": health.consecutive_failures,
                },
            })
        return {"items": items, "total": len(items)}

    @router.post("/nodes/{node_id}/enabled")
    async def set_node_enabled(node_id: str, request: ResourceEnabledRequest):
        """Toggle a customer's Node scheduling switch within its tenant."""
        plane = getattr(runtime, "resource_plane", None)
        if plane is None:
            raise HTTPException(status_code=503, detail="node mutation source unavailable")
        try:
            profile = plane.node(node_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="node not found") from exc
        actor = current_trusted_user()
        if actor is None:
            raise HTTPException(status_code=401, detail="trusted user context required")
        if actor.tenant_id and actor.tenant_id != profile.owner_scope:
            raise HTTPException(status_code=403, detail="node owner scope does not match operator tenant")
        updated = plane.set_node_enabled(node_id, enabled=request.enabled)
        return {"nodeId": updated.node_id, "enabled": updated.enabled}

    @router.get("/agents")
    async def get_agents():
        """Return the logical agents callable through the embedded runtime.

        逻辑 Agent 不是资源；这个投影只描述嵌入式执行后端内可解析的角色，
        选择权威仍在资源平面的 Runtime 绑定。
        """
        agent_registry = getattr(runtime, "agent_registry", None)
        if agent_registry is None:
            raise HTTPException(status_code=503, detail="agent query source unavailable")
        items: list[dict[str, Any]] = []
        for agent in agent_registry.all():
            profile = agent.profile
            agent_id = str(agent_registry.agent_id(agent))
            items.append({
                "profile": {
                    "agentId": agent_id,
                    "agentName": profile.agent_name,
                    "domain": profile.domain,
                    "capabilities": list(profile.capabilities),
                    "riskLevel": profile.risk_level,
                    "description": profile.description,
                    "enabled": profile.enabled,
                    "source": profile.source,
                    "modelProvider": profile.model_provider,
                    "modelName": profile.model_name,
                },
                "snapshotVersion": 1,
            })
        return {"items": items, "total": len(items)}

    @router.post("/resources/register", status_code=status.HTTP_201_CREATED)
    async def register_remote_resource(request: RemoteResourceRegistrationRequest):
        """Register a remote resource and issue its one-time credential secret."""
        plane = getattr(runtime, "resource_plane", None)
        if plane is None:
            raise HTTPException(status_code=503, detail="resource registration source unavailable")
        profile = request.profile
        if request.snapshot.runtime_id != profile.runtime_id:
            raise HTTPException(status_code=422, detail="profile and snapshot runtimeId must match")
        require_resource_operator(str(profile.owner_scope or ""))
        try:
            issued = plane.register_remote_runtime(
                profile, request.snapshot, registration_id=request.registration_id
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            "resourceId": issued.resource_id,
            "credentialId": issued.credential_id,
            "ownerScope": issued.owner_scope,
            "secret": issued.secret,
            "signatureAlgorithm": "HMAC-SHA256-SHA256(secret)",
            "created": issued.created,
        }

    @router.post("/nodes/register", status_code=status.HTTP_201_CREATED)
    async def register_remote_node(request: NodeRegistrationRequest):
        """Register a remote node and issue its one-time credential secret."""
        plane = getattr(runtime, "resource_plane", None)
        if plane is None:
            raise HTTPException(status_code=503, detail="node registration source unavailable")
        profile = request.profile
        if request.snapshot.node_id != profile.node_id:
            raise HTTPException(status_code=422, detail="profile and snapshot nodeId must match")
        require_resource_operator(str(profile.owner_scope or ""))
        try:
            issued = plane.register_remote_node(
                profile, request.snapshot, registration_id=request.registration_id
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            "nodeId": issued.node_id,
            "credentialId": issued.credential_id,
            "ownerScope": issued.owner_scope,
            "secret": issued.secret,
            "signatureAlgorithm": "HMAC-SHA256-SHA256(secret)",
            "created": issued.created,
        }

    @router.post("/nodes/{node_id}/observation")
    async def post_remote_node_observation(
        node_id: str,
        request: RemoteNodeObservationRequest,
        raw_request: Request,
        node_credential_id: str | None = Header(default=None, alias="X-Node-Credential-Id"),
        node_timestamp: str | None = Header(default=None, alias="X-Node-Timestamp"),
        node_nonce: str | None = Header(default=None, alias="X-Node-Nonce"),
        node_signature: str | None = Header(default=None, alias="X-Node-Signature"),
    ):
        """Accept a signed remote node heartbeat and update the Node ledger."""
        plane = getattr(runtime, "resource_plane", None)
        if plane is None:
            raise HTTPException(status_code=503, detail="node observation source unavailable")
        if not all((node_credential_id, node_timestamp, node_nonce, node_signature)):
            raise HTTPException(status_code=401, detail="node authentication headers are required")
        try:
            timestamp = int(node_timestamp)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=401, detail="node request timestamp is invalid") from exc
        try:
            NodeRequestAuthenticator(plane).authenticate(
                node_id=node_id,
                credential_id=node_credential_id,
                method=raw_request.method,
                path=raw_request.url.path,
                timestamp=timestamp,
                nonce=node_nonce,
                signature=node_signature,
                body=await raw_request.body(),
            )
        except ResourceRequestNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ResourceRequestExpired as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except ResourceRequestReplay as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ResourceRequestInvalid as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        try:
            health = plane.observe_node(
                node_id,
                observation_sequence=request.observation_sequence,
                cpu_utilization=request.cpu_utilization,
                gpu_utilization=request.gpu_utilization,
                available_memory_mb=request.available_memory_mb,
                queued_tasks=request.queued_tasks,
                latency_ms=request.latency_ms,
                observed_at=request.observed_at,
            )
            versioned = plane.node_snapshot(node_id)
            coordinator.notify_state_changed()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="node not found") from exc
        except StaleResourceObservation as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "nodeId": node_id,
            "health": {
                "status": health.status.value,
                "lastHeartbeat": (
                    health.last_heartbeat.isoformat()
                    if health.last_heartbeat is not None
                    else None
                ),
                "consecutiveFailures": health.consecutive_failures,
            },
            "snapshot": versioned.snapshot.model_dump(by_alias=True, mode="json"),
            "snapshotVersion": versioned.version,
        }

    @router.post("/resources/{resource_id}/credential/rotate")
    async def rotate_remote_resource_credential(resource_id: str):
        """Rotate a remote resource credential and return the new secret once."""
        plane = getattr(runtime, "resource_plane", None)
        if plane is None:
            raise HTTPException(status_code=503, detail="resource credential source unavailable")
        try:
            profile = plane.runtime(resource_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="resource not found") from exc
        require_resource_operator(str(profile.owner_scope or ""))
        try:
            issued = plane.rotate_runtime_credential(resource_id)
        except KeyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            "resourceId": issued.resource_id,
            "credentialId": issued.credential_id,
            "ownerScope": issued.owner_scope,
            "secret": issued.secret,
            "signatureAlgorithm": "HMAC-SHA256-SHA256(secret)",
        }

    @router.post("/resources/{resource_id}/observation")
    async def post_remote_resource_observation(
        resource_id: str,
        request: RemoteResourceObservationRequest,
        raw_request: Request,
        resource_credential: str | None = Header(default=None, alias="X-Resource-Credential"),
        resource_timestamp: str | None = Header(default=None, alias="X-Resource-Timestamp"),
        resource_nonce: str | None = Header(default=None, alias="X-Resource-Nonce"),
        resource_signature: str | None = Header(default=None, alias="X-Resource-Signature"),
    ):
        """Accept a remote node's heartbeat plus its latest schedulable snapshot."""
        plane = getattr(runtime, "resource_plane", None)
        if plane is None:
            raise HTTPException(status_code=503, detail="resource observation source unavailable")
        if not all((resource_credential, resource_timestamp, resource_nonce, resource_signature)):
            raise HTTPException(status_code=401, detail="resource authentication headers are required")
        try:
            timestamp = int(resource_timestamp)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=401, detail="resource request timestamp is invalid") from exc
        try:
            ResourceRequestAuthenticator(plane).authenticate(
                resource_id=resource_id,
                credential_id=resource_credential,
                method=raw_request.method,
                path=raw_request.url.path,
                timestamp=timestamp,
                nonce=resource_nonce,
                signature=resource_signature,
                body=await raw_request.body(),
            )
        except ResourceRequestNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ResourceRequestExpired as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except ResourceRequestReplay as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ResourceRequestInvalid as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        try:
            health = plane.observe_remote_runtime(
                resource_id,
                available_slots=request.available_slots,
                utilization=request.utilization,
                latency_ms=request.latency_ms,
                observed_at=request.observed_at,
                observation_sequence=request.observation_sequence,
            )
            versioned = plane.runtime_snapshot(resource_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="resource not found") from exc
        except StaleResourceObservation as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "resourceId": resource_id,
            "health": {
                "healthy": health.healthy,
                "reliability": health.reliability,
                "latencyMs": health.latency_ms,
                "lastHeartbeat": (
                    health.last_heartbeat.isoformat()
                    if health.last_heartbeat is not None
                    else None
                ),
            },
            "snapshot": versioned.snapshot.model_dump(by_alias=True, mode="json"),
            "snapshotVersion": versioned.version,
        }

    @router.get("/missions")
    async def list_missions(
        status_value: str | None = Query(default=None, alias="status"),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
    ):
        query = require_identity_queries()
        actor = current_trusted_user()
        try:
            mission_status = MissionStatus(status_value) if status_value else None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="invalid mission status") from exc

        visible_mission_ids = runtime.workflow_store.list_mission_ids(
            mission_record_state=MissionRecordState.ACTIVE,
        )

        items, total = query.list_mission_items(
            user_id=(actor.user_id if actor else None),
            tenant_id=(actor.tenant_id if actor else None),
            status=mission_status,
            page=page,
            page_size=page_size,
            visible_mission_ids=visible_mission_ids,
            include_run_summaries=False,
        )
        runtime_summaries = runtime.workflow_store.list_mission_run_summaries(
            [item.mission_id for item in items],
            mission_record_state=MissionRecordState.ACTIVE,
            owner_user_id=(actor.user_id if actor else None),
            owner_tenant_id=(actor.tenant_id if actor else None),
        )
        projected_items: list[dict[str, Any]] = []
        for item in items:
            projected = item.model_dump(by_alias=True, mode="json")
            runtime_summary = runtime_summaries.get(item.mission_id)
            if runtime_summary is not None and runtime_summary.latest_run is not None:
                latest = runtime_summary.latest_run
                projected["latestRunId"] = latest.run_id
                projected["latestRunStatus"] = latest.status.value
                projected["runCount"] = runtime_summary.run_count
                projected["updatedAt"] = latest.updated_at.isoformat()
            projected_items.append(projected)
        return {
            "items": projected_items,
            "total": total,
            "page": page,
            "pageSize": page_size,
            "source": "agentos-v2",
        }

    @router.get("/missions/{mission_id}")
    async def get_mission(mission_id: str):
        return require_mission_access(mission_id).model_dump(by_alias=True, mode="json")

    @router.get("/missions/{mission_id}/runs")
    async def get_mission_runs(mission_id: str):
        require_mission_access(mission_id)
        history = require_identity_queries().mission_run_history(mission_id)
        return history.model_dump(by_alias=True, mode="json")

    @router.get("/missions/{mission_id}/workspace")
    async def get_mission_workspace(
        mission_id: str,
        run_id: str | None = Query(default=None, alias="runId"),
    ):
        semantic_view = None
        semantic_read = require_current_mission_read(mission_id)
        if semantic_read is not None:
            snapshot, semantic_record = semantic_read
            try:
                semantic_view = MissionSemanticResolver.resolve(snapshot)
            except (ValueError, RuntimeError) as exc:
                raise HTTPException(status_code=503, detail="mission semantic source unavailable") from exc
        mission_detail = require_mission_access(mission_id)
        actor = current_trusted_user()

        if run_id:
            # 显式请求的 Run 若已被软删除，工作区按 404 收敛，避免残留投影
            # 让已删 Run 通过直达链接复活动。
            try:
                requested_runtime_run = getattr(runtime, "get_status_cached", runtime.get_status)(run_id)
            except KeyError:
                requested_runtime_run = None
            if requested_runtime_run is not None and requested_runtime_run.record_state is RunRecordState.DELETED:
                raise HTTPException(status_code=404, detail="run not found")

        runtime_status_map = {
            "pending": RunStatus.PENDING,
            "planning": RunStatus.PENDING,
            "running": RunStatus.RUNNING,
            "retrying": RunStatus.RUNNING,
            "waiting_review": RunStatus.RUNNING,
            "completed": RunStatus.SUCCEEDED,
            "failed": RunStatus.FAILED,
            "cancelled": RunStatus.CANCELLED,
            "superseded": RunStatus.SUPERSEDED,
        }
        terminal_run_statuses = {
            RunStatus.SUCCEEDED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.SUPERSEDED,
        }

        def list_runtime_runs() -> list[Any]:
            """Load every visible Run so Workspace and Project use one Run set."""
            items: list[Any] = []
            page = 1
            page_size = 100
            while True:
                result = runtime.workflow_store.list_run_overviews(
                    mission_id=mission_id,
                    owner_user_id=(actor.user_id if actor else None),
                    owner_tenant_id=(actor.tenant_id if actor else None),
                    page=page,
                    page_size=page_size,
                )
                items.extend(result.items)
                if not result.items or page * result.page_size >= result.total:
                    return items
                page += 1

        def runtime_run_summary(item: Any, *, is_active: bool) -> WorkspaceRunSummary:
            raw_status = getattr(item.status, "value", item.status)
            status = runtime_status_map.get(str(raw_status), RunStatus.PENDING)
            execution_state = getattr(item, "execution_state", {})
            execution_state = execution_state if isinstance(execution_state, dict) else {}
            # Identity already carries lineage for materialized runs. Only
            # deferred runs without an Identity row need their runtime body.
            if not execution_state and identity_repositories.runs.get(item.run_id) is None:
                source = getattr(runtime, "get_status_cached", runtime.get_status)(item.run_id)
                state = getattr(source, "execution_state", {})
                execution_state = state if isinstance(state, dict) else {}
            completed_at = (
                item.updated_at
                if status in terminal_run_statuses
                else None
            )
            return WorkspaceRunSummary(
                runId=item.run_id,
                status=status,
                parentRunId=getattr(item, "parent_run_id", None) or execution_state.get("parentRunId"),
                sourceRunId=getattr(item, "source_run_id", None) or execution_state.get("sourceRunId"),
                createdAt=item.created_at,
                completedAt=completed_at,
                isActive=is_active,
            )

        if not run_id:
            runtime_runs = runtime.workflow_store.list_run_overviews(
                mission_id=mission_id,
                mission_record_state=MissionRecordState.ACTIVE,
                owner_user_id=(actor.user_id if actor else None),
                owner_tenant_id=(actor.tenant_id if actor else None),
                page=1,
                page_size=1,
            )
            if runtime_runs.items:
                run_id = runtime_runs.items[0].run_id
        try:
            projection = require_identity_queries().mission_workspace(
                mission_id,
                run_id=run_id,
            )
        except EntityNotFoundError as exc:
            if not run_id:
                raise HTTPException(status_code=404, detail="workspace source not found") from exc
            try:
                runtime_run = getattr(runtime, "get_status_cached", runtime.get_status)(run_id)
            except KeyError:
                raise HTTPException(status_code=404, detail="workspace source not found") from exc
            _require_access(runtime_run)
            if runtime_run.mission_id != mission_id:
                raise HTTPException(status_code=404, detail="workspace source not found") from exc

            status_map = {
                "completed": RunStatus.SUCCEEDED,
                "failed": RunStatus.FAILED,
                "cancelled": RunStatus.CANCELLED,
                "superseded": RunStatus.SUPERSEDED,
                "running": RunStatus.RUNNING,
            }
            projected_status = status_map.get(runtime_run.status.value, RunStatus.PENDING)
            error = runtime_run.error if isinstance(runtime_run.error, dict) else {}
            terminal_statuses = {
                RunStatus.SUCCEEDED,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
                RunStatus.SUPERSEDED,
            }

            def run_summary(item: Any, *, is_active: bool) -> WorkspaceRunSummary:
                metadata = item.metadata if isinstance(getattr(item, "metadata", None), dict) else {}
                return WorkspaceRunSummary(
                    runId=item.run_id,
                    status=item.status,
                    parentRunId=metadata.get("parentRunId"),
                    sourceRunId=metadata.get("sourceRunId"),
                    createdAt=item.created_at,
                    completedAt=item.finished_at,
                    isActive=is_active,
                )

            historical_summaries = [
                run_summary(item, is_active=False)
                for item in mission_detail.runs
                if item.run_id != runtime_run.run_id
            ]
            runtime_state = getattr(runtime_run, "execution_state", None)
            runtime_state = runtime_state if isinstance(runtime_state, dict) else {}
            runtime_parent_id = runtime_state.get("parentRunId")
            runtime_source_id = runtime_state.get("sourceRunId")
            runtime_summary = WorkspaceRunSummary(
                runId=runtime_run.run_id,
                status=projected_status,
                parentRunId=runtime_parent_id,
                sourceRunId=runtime_source_id,
                createdAt=runtime_run.created_at,
                completedAt=(runtime_run.updated_at if projected_status in terminal_statuses else None),
                isActive=True,
            )
            projection = MissionWorkspaceProjection(
                mission=mission_detail.mission,
                activeRun=runtime_summary,
                runs=sorted(
                    [*historical_summaries, runtime_summary],
                    key=lambda item: (item.created_at, item.run_id),
                ),
                inputAttachments=[
                    item.model_dump(
                        by_alias=True,
                        mode="json",
                        exclude={"owner_user_id", "owner_tenant_id", "storage_key"},
                    )
                    for item in identity_repositories.input_attachments.list_for_mission(
                        mission_id
                    )
                ],
                diagnostics=[WorkspaceDiagnostic(
                    code="PLANNING_PROJECTION_PENDING",
                    message="Run exists in the execution runtime; its identity graph is not available yet.",
                    severity="warning",
                    details={
                        "runtimeStatus": runtime_run.status.value,
                        "lifecyclePhase": (
                            runtime_run.lifecycle_phase.value
                            if runtime_run.lifecycle_phase is not None
                            else None
                        ),
                        "errorCode": error.get("code"),
                    },
                )],
            )

        # A deferred planning failure is intentionally not materialized into
        # the Identity graph. Keep it in the Workspace Run navigator anyway:
        # every user-triggered Run is a real historical Run, even when it has
        # no Blueprint or TaskPlan to project.
        runtime_runs = list_runtime_runs()
        runtime_summaries = {
            item.run_id: runtime_run_summary(
                item,
                is_active=item.run_id == (
                    projection.active_run.run_id
                    if projection.active_run is not None
                    else run_id
                ),
            )
            for item in runtime_runs
        }
        merged_runs: list[WorkspaceRunSummary] = []
        projected_run_ids: set[str] = set()
        for item in projection.runs:
            runtime_summary = runtime_summaries.get(item.run_id)
            if runtime_summary is None:
                merged_runs.append(item)
            else:
                projected_run_ids.add(item.run_id)
                merged_runs.append(item.model_copy(update={
                    "status": runtime_summary.status,
                    "parent_run_id": runtime_summary.parent_run_id or item.parent_run_id,
                    "source_run_id": runtime_summary.source_run_id or item.source_run_id,
                    "completed_at": runtime_summary.completed_at or item.completed_at,
                }))
        merged_runs.extend(
            item
            for run_id_value, item in runtime_summaries.items()
            if run_id_value not in projected_run_ids
        )
        active_run = projection.active_run
        if active_run is not None:
            runtime_summary = runtime_summaries.get(active_run.run_id)
            if runtime_summary is not None:
                active_run = active_run.model_copy(update={
                    "status": runtime_summary.status,
                    "parent_run_id": runtime_summary.parent_run_id or active_run.parent_run_id,
                    "source_run_id": runtime_summary.source_run_id or active_run.source_run_id,
                    "completed_at": runtime_summary.completed_at or active_run.completed_at,
                })
        projection = projection.model_copy(update={
            "active_run": active_run,
            "runs": sorted(
                merged_runs,
                key=lambda item: (item.created_at, item.run_id),
            ),
        })

        # Identity owns stable task semantics; the execution runtime owns
        # transient/persisted node results. Join only their references here so
        # the workspace can expose a stage result without promoting it to a
        # formal Artifact or embedding the potentially large output body.
        if run_id:
            try:
                runtime_run = getattr(runtime, "get_status_cached", runtime.get_status)(run_id)
            except KeyError:
                runtime_run = None
            if runtime_run is not None and runtime_run.mission_id == mission_id:
                # The Execution Runtime is the authoritative source for Run
                # lifecycle state. Identity projection can lag after a
                # restart, so do not expose an old ``running`` snapshot to
                # Workspace while the reconciler catches up.
                raw_runtime_status = getattr(runtime_run, "status", None)
                runtime_status_value = getattr(
                    raw_runtime_status,
                    "value",
                    raw_runtime_status,
                )
                runtime_status_map = {
                    "pending": RunStatus.PENDING,
                    "planning": RunStatus.PENDING,
                    "running": RunStatus.RUNNING,
                    "retrying": RunStatus.RUNNING,
                    "waiting_review": RunStatus.RUNNING,
                    "completed": RunStatus.SUCCEEDED,
                    "failed": RunStatus.FAILED,
                    "cancelled": RunStatus.CANCELLED,
                    "superseded": RunStatus.SUPERSEDED,
                }
                projected_runtime_status = runtime_status_map.get(runtime_status_value)
                if projected_runtime_status is not None:
                    runtime_finished_at = (
                        getattr(runtime_run, "updated_at", None)
                        if projected_runtime_status in {
                            RunStatus.SUCCEEDED,
                            RunStatus.FAILED,
                            RunStatus.CANCELLED,
                            RunStatus.SUPERSEDED,
                        }
                        else None
                    )
                    projection = projection.model_copy(update={
                        "active_run": (
                            projection.active_run.model_copy(update={
                                "status": projected_runtime_status,
                                "completed_at": runtime_finished_at or projection.active_run.completed_at,
                            })
                            if projection.active_run is not None
                            and projection.active_run.run_id == runtime_run.run_id
                            else projection.active_run
                        ),
                        "runs": [
                            item.model_copy(update={
                                "status": projected_runtime_status,
                                "completed_at": runtime_finished_at or item.completed_at,
                            })
                            if item.run_id == runtime_run.run_id
                            else item
                            for item in projection.runs
                        ],
                    })
                runtime_state = getattr(runtime_run, "execution_state", None)
                runtime_state = runtime_state if isinstance(runtime_state, dict) else {}
                output_refs = runtime_state.get("outputRefs") or {}
                output_summaries = runtime_state.get("outputSummaries") or {}
                if isinstance(output_refs, dict):
                    projection = projection.model_copy(update={
                        "entries": [
                            entry.model_copy(update={
                                "metadata": {
                                    **entry.metadata,
                                    "outputRef": output_refs.get(entry.acg_node_id),
                                    "outputSummary": output_summaries.get(entry.acg_node_id),
                                },
                            })
                            if entry.kind is WorkspaceEntryKind.TASK and entry.acg_node_id in output_refs
                            else entry
                            for entry in projection.entries
                        ],
                    })
        if semantic_view is not None:
            from contracts.mission_semantic import run_intent_basis
            from runtime.workspace import with_mission_semantics
            selected_id = projection.active_run.run_id if projection.active_run is not None else None
            basis = None
            basis_status = "NO_RUN"
            if selected_id:
                try:
                    selected = runtime.workflow_store.get_run(selected_id)
                except KeyError:
                    basis_status = "RUNTIME_UNAVAILABLE"
                else:
                    _require_access(selected)
                    if selected.mission_id != mission_id or selected.record_state is RunRecordState.DELETED:
                        raise HTTPException(status_code=404, detail="run not found")
                    try:
                        basis = run_intent_basis(selected)
                    except ValueError as exc:
                        raise HTTPException(status_code=503, detail="run semantic basis unavailable") from exc
                    basis_status = "BOUND" if basis is not None else "UNBOUND"
            try:
                projection = with_mission_semantics(projection, semantic_view, basis=basis,
                    basis_status=basis_status, legacy_input=semantic_record.input, legacy_title=semantic_record.title)
            except (KeyError, ValueError) as exc:
                raise HTTPException(status_code=503, detail="mission semantic projection unavailable") from exc
        payload = projection.model_dump(
            by_alias=True,
            mode="json",
            exclude_none=True,
        )
        # Runtime facts can lead Identity through its durable outbox. Read each
        # Run independently; selected/isActive and timestamps never grant action.
        capabilities = {}
        selected = payload.get('activeRun')
        for summary in [*payload['runs'], *([selected] if selected else [])]:
            selected_id = summary['runId']
            if selected_id not in capabilities:
                try:
                    source = runtime.workflow_store.get_run(selected_id)
                except (KeyError, AttributeError):
                    capabilities[selected_id] = None
                else:
                    _require_access(source)
                    capabilities[selected_id] = (project_run_capabilities(runtime, source)
                        if source.mission_id == mission_id else None)
            summary['actionCapabilities'] = capabilities[selected_id]
        return payload

    async def workspace_file_read(mission_id: str, path: str, tool_name: str, arguments: dict, *, save_operation: str | None = None):
        """Use the existing owner check, startup Grant and read-only file tools."""
        require_mission_access(mission_id)
        relative_path = normalize_relative_path(path)
        if relative_path is None or len(relative_path) > 4096:
            raise HTTPException(status_code=400, detail="workspace-relative path is invalid")

        client = getattr(runtime, "local_runtime_client", None)
        authorization = getattr(runtime, "local_runtime_authorization", None)
        if client is None or authorization is None:
            raise HTTPException(status_code=503, detail="workspace file capability unavailable")

        authority = getattr(runtime, 'workspace_authority', None)
        if authority is not None:
            # Explorer is a human action, scoped to the latest frozen Mission Run.
            actor = current_trusted_user()
            runs = runtime.workflow_store.list_runs(
                mission_id=mission_id,
                owner_user_id=(actor.user_id if actor else None),
                owner_tenant_id=(actor.tenant_id if actor else None),
            )
            if not runs:
                raise HTTPException(403, 'Mission has no frozen workspace Run')
            selected_run = max(runs, key=lambda item: item.created_at)
            _require_access(selected_run)
            try:
                authorization = authority.resolve(selected_run)
            except PermissionError as exc:
                raise HTTPException(403, str(exc)) from exc
            from contracts.capability import CapabilityInvocation
            from contracts.local_runtime import LocalRuntimeExecutionLimits
            capability = {'read_file':'fs.read','list_files':'fs.list','write_file':'fs.write'}[tool_name]
            business = dict(arguments, path=relative_path)
            business.pop('maxEntries', None)
            call_id = f'workspace-human:{mission_id}:{save_operation or uuid4().hex}'
            result = await client.execute(CapabilityInvocation(invocationId=call_id, capabilityId=capability, input=business),
                resource_id=runtime.local_runtime_resource.profile.runtime_id, authorization=authorization,
                limits=LocalRuntimeExecutionLimits(timeoutSeconds=30, maxStdoutBytes=64000, maxStderrBytes=32000),
                idempotency_key=call_id)
            if result.status != 'completed':
                raise HTTPException(409, result.error.code if result.error else 'Workspace operation failed')
            frozen = selected_run.input.get('workspaceBinding')
            workspace_root = frozen['workspaceRoot'] if isinstance(frozen, dict) else await client.workspace_root(authorization)
            return workspace_root, relative_path, result.output

        try:
            workspace_root = await client.workspace_root(authorization)
            from app.tools import get_chat_tool_runtime

            catalog = get_chat_tool_runtime().catalog
            session_id = f"workspace-explorer:{mission_id}"
            call_id = f"workspace-save:{mission_id}:{save_operation}" if save_operation else f"workspace-explorer:{uuid4().hex}"

            async def confirm_user_save(event, data):
                # This authenticated endpoint represents the human's explicit Save
                # action. Resolve only this invocation, once; DENY policy still wins.
                if event == "approval_required" and save_operation:
                    from app.tools.permissions import ApprovalDecision
                    approval = data["approval"]
                    await catalog.permission_service.resolve(
                        approval["approvalId"], decision=ApprovalDecision.ALLOW_ONCE,
                        session_id=session_id, invocation_id=call_id,
                        capability_id="fs.write", relative_path=relative_path)

            payload = await catalog.execute(
                tool_name,
                {"path": relative_path, **arguments},
                call_id=call_id,
                session_id=session_id,
                **({"permission_event_sink": confirm_user_save} if save_operation else {}),
            )
        except HTTPException:
            raise
        except Exception as exc:
            from app.tools.local_runtime import LocalRuntimeToolError
            from app.tools.permissions import PermissionDeniedError

            if isinstance(exc, PermissionDeniedError):
                raise HTTPException(status_code=403, detail="workspace access denied") from exc
            if isinstance(exc, LocalRuntimeToolError):
                if exc.code in {"FS_NOT_TEXT", "FS_TOO_LARGE"}:
                    # 文本编辑链（1 MiB/严格 UTF-8）拒绝：读取端点改以二进制读走
                    # 预览提取；保存/列表调用方直接映射回各自状态码。
                    raise WorkspaceBinaryFallbackNeeded(exc.code) from exc
                if exc.code in {"FS_STALE_VERSION", "FS_NOT_OBSERVED"}:
                    raise HTTPException(status_code=409, detail="File changed on disk; reload before saving") from exc
                if exc.code in {"PATH_INVALID", "DIRECTORY_REQUIRED", "LIST_LIMIT_EXCEEDED"}:
                    raise HTTPException(status_code=400, detail=exc.code) from exc
                if exc.code in {"PATH_NOT_FOUND", "PARENT_NOT_FOUND", "FS_NOT_FOUND"}:
                    raise HTTPException(status_code=404, detail="workspace path not found") from exc
                if exc.code in {
                    "PATH_OUTSIDE_WORKSPACE", "CAPABILITY_DENIED", "GRANT_REVOKED", "GRANT_EXPIRED"
                }:
                    raise HTTPException(status_code=403, detail="workspace access denied") from exc
                raise HTTPException(status_code=503, detail="workspace file capability unavailable") from exc
            logger.warning("Workspace file listing unavailable: %s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="workspace file capability unavailable") from exc

        result = payload.data.get("result") if isinstance(payload.data, dict) else None
        if not isinstance(result, dict):
            raise HTTPException(status_code=502, detail="workspace response is invalid")
        return workspace_root, relative_path, result

    @router.get("/missions/{mission_id}/workspace/files")
    async def list_workspace_files(
        mission_id: str, path: str = Query(default="."),
        max_entries: int = Query(default=1000, alias="maxEntries", ge=1, le=1000),
    ):
        workspace_root, relative_path, result = await workspace_file_read(
            mission_id, path, "list_files", {"maxEntries": max_entries})
        entries = result.get("entries") if isinstance(result, dict) else None
        if not isinstance(entries, list):
            raise HTTPException(status_code=502, detail="workspace listing response is invalid")
        if len(entries) > max_entries:
            raise HTTPException(status_code=400, detail="LIST_LIMIT_EXCEEDED")
        # Hands entries have name/type; derive child paths from the authorized
        # directory instead of requiring an executor-specific path field.
        children = []
        for item in entries:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if (not isinstance(name, str) or name in {"", ".", ".."}
                    or any(c in name for c in "/\\:\x00") or item.get("type") not in {"file", "directory"}):
                continue
            child_path = name if relative_path == "." else relative_path.rstrip("/") + "/" + name
            children.append({"name": name, "type": item["type"], "path": child_path})
        return {
            "workspaceRoot": workspace_root,
            "path": relative_path,
            "entries": children,
        }

    @router.get("/missions/{mission_id}/workspace/file")
    async def read_workspace_file(mission_id: str, path: str = Query(min_length=1)):
        try:
            workspace_root, relative_path, result = await workspace_file_read(
                mission_id, path, "read_file", {"versioned": True})
        except WorkspaceBinaryFallbackNeeded:
            return await read_workspace_file_binary(mission_id, path)
        content = result.get("content", result.get("text"))
        if (not isinstance(content, str) or result.get("binary") or result.get("isBinary")
                or result.get("encoding") == "base64" or "\x00" in content):
            raise HTTPException(status_code=415, detail="Only text files can be previewed")
        if len(content.encode("utf-8")) > 1_048_576:
            raise HTTPException(status_code=413, detail="File exceeds the 1 MiB preview limit")
        return {"workspaceRoot": workspace_root, "path": relative_path, "content": content,
                "version": result.get("version")}

    async def read_workspace_file_binary(mission_id: str, path: str) -> dict:
        """二进制重读：交给 workspace_preview 生成只读载荷（与桌面链同一合同）。"""
        try:
            workspace_root, relative_path, result = await workspace_file_read(
                mission_id, path, "read_file", {"binary": True})
        except WorkspaceBinaryFallbackNeeded as exc:
            # 旧执行器不支持二进制读取，或文件超出 32 MiB 预览上限：保留原状态码。
            if exc.code == "FS_TOO_LARGE":
                raise HTTPException(status_code=413, detail="File exceeds the 32 MiB preview limit") from exc
            raise HTTPException(status_code=415, detail="Only UTF-8 text files can be opened") from exc
        if result.get("binary") is not True or result.get("encoding") != "base64" or not isinstance(result.get("content"), str):
            raise HTTPException(status_code=502, detail="workspace response is invalid")
        import base64
        from app.services import workspace_preview
        try:
            raw = base64.b64decode(result["content"], validate=True)
        except Exception as exc:
            raise HTTPException(status_code=502, detail="workspace response is invalid") from exc
        payload = workspace_preview.extract_preview(relative_path, raw)
        return {"workspaceRoot": workspace_root, "path": relative_path, "version": None, **payload}

    @router.post("/missions/{mission_id}/workspace/file")
    async def save_workspace_file(mission_id: str, body: WorkspaceFileSaveRequest):
        # No client-selected root, Grant or security profile. Never fall back to
        # a plain overwrite if this backend lacks conditional-write support.
        require_mission_access(mission_id)
        if "\x00" in body.content:
            raise HTTPException(status_code=415, detail="Only text files can be saved")
        if len(body.content.encode("utf-8")) > 1_048_576:
            raise HTTPException(status_code=413, detail="File exceeds the 1 MiB editor limit")
        snapshot = await read_workspace_file(mission_id, body.path)
        if not snapshot.get("version"):
            raise HTTPException(status_code=409, detail="This runtime supports read-only editing; conditional writes unavailable")
        if snapshot["version"] != body.expected_version:
            raise HTTPException(status_code=409, detail="File changed on disk; reload before saving")
        root, path, result = await workspace_file_read(
            mission_id, body.path, "write_file",
            {"content": body.content, "expectedVersion": body.expected_version, "overwrite": True},
            save_operation=body.operation_id)
        return {"workspaceRoot": root, "path": path, "version": result.get("version")}

    def change_mission_record_state(mission_id: str, state: MissionRecordState) -> dict[str, Any]:
        require_mission_access(mission_id)
        try:
            task, affected_runs = runtime.workflow_store.set_mission_record_state(mission_id, state)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="mission not found") from exc
        except RuntimeRunRecordNotTerminalError as exc:
            raise HTTPException(status_code=409, detail="mission has active runs") from exc
        except ValueError as exc:
            if (
                state is MissionRecordState.DELETED
                and str(exc) == "deleted mission record state is immutable"
            ):
                # DELETE is idempotent at the API boundary. The identity
                # projection can retain a stale row until its next read, so a
                # repeated delete should converge it instead of surfacing a
                # misleading conflict.
                try:
                    task = runtime.workflow_store.get_mission(mission_id)
                except KeyError as missing:
                    raise HTTPException(status_code=404, detail="mission not found") from missing
                affected_runs = 0
            else:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            "missionId": task.mission_id,
            "recordState": task.record_state.value,
            "affectedRunCount": affected_runs,
            "archivedAt": task.archived_at,
            "deletedAt": task.deleted_at,
        }

    @router.post("/missions/{mission_id}/archive")
    async def archive_mission(mission_id: str):
        return change_mission_record_state(mission_id, MissionRecordState.ARCHIVED)

    @router.post("/missions/{mission_id}/restore")
    async def restore_mission(mission_id: str):
        return change_mission_record_state(mission_id, MissionRecordState.ACTIVE)

    @router.delete("/missions/{mission_id}")
    async def delete_mission(mission_id: str):
        return change_mission_record_state(mission_id, MissionRecordState.DELETED)

    @router.get("/runs/{run_id}/execution-tree")
    async def get_execution_tree(run_id: str):
        query, _ = require_run_access(run_id)
        return query.run_execution_tree(run_id).model_dump(
            by_alias=True,
            mode="json",
        )

    @router.get("/runs/{run_id}/attempts")
    async def get_attempt_history(
        run_id: str,
        task_id: str | None = Query(default=None, alias="taskId"),
    ):
        query, _ = require_run_access(run_id)
        return query.attempt_history(run_id, task_id=task_id).model_dump(
            by_alias=True,
            mode="json",
        )

    @router.get("/attempts/{attempt_id}")
    async def get_attempt(attempt_id: str):
        query = require_identity_queries()
        try:
            detail = query.get_attempt(attempt_id)
        except EntityNotFoundError as exc:
            raise HTTPException(status_code=404, detail="attempt not found") from exc
        run = identity_repositories.runs.get(detail.attempt.run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="attempt not found")
        require_mission_access(run.mission_id)
        return detail.model_dump(by_alias=True, mode="json")

    @router.get("/step-executions/{step_execution_id}")
    async def get_step_execution(step_execution_id: str):
        query = require_identity_queries()
        try:
            detail = query.step_execution_detail(step_execution_id)
        except EntityNotFoundError as exc:
            raise HTTPException(status_code=404, detail="step execution not found") from exc
        require_mission_access(detail.origin.mission.mission_id)
        return detail.model_dump(by_alias=True, mode="json")

    @router.get("/step-executions/{step_execution_id}/provenance")
    async def get_step_execution_provenance(step_execution_id: str):
        query = require_identity_queries()
        try:
            detail = query.step_execution_detail(step_execution_id)
            provenance = query.execution_provenance(step_execution_id)
        except EntityNotFoundError as exc:
            raise HTTPException(status_code=404, detail="step execution not found") from exc
        require_mission_access(detail.origin.mission.mission_id)
        return provenance.model_dump(by_alias=True, mode="json")

    def require_semantic_service():
        service = getattr(runtime, "mission_semantic_service", None)
        if service is None:
            raise HTTPException(status_code=409, detail="mission semantics are disabled")
        principal = current_semantic_principal()
        if principal is None:
            raise HTTPException(status_code=403, detail="trusted semantic principal is required")
        return service, principal

    def require_visible_semantic_mission(service, principal, mission_id):
        # Authorization precedes existence checks; soft deletion hides public
        # commands and receipts while internal semantic history is retained.
        try:
            service.require_read_access(principal, mission_id)
            mission = runtime.workflow_store.get_mission(mission_id)
            if mission.record_state is MissionRecordState.DELETED:
                raise HTTPException(status_code=404, detail="mission not found")
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail="semantic access denied") from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="mission not found") from exc

    def revision_context(mission_id, run_id):
        service, principal = require_semantic_service()
        require_visible_semantic_mission(service, principal, mission_id)
        run = load_run(run_id)
        if run.mission_id != mission_id:
            raise HTTPException(status_code=409, detail="MISSION_SCOPE_CONFLICT")
        if run.record_state.value != "active":
            raise HTTPException(status_code=404, detail="run not found")
        return service, principal, run

    @router.get("/missions/{mission_id}/runs/{run_id}/revision")
    async def get_run_revision(mission_id: str, run_id: str):
        service, principal, run = revision_context(mission_id, run_id)
        try:
            observation = revision_observation(run, service.get_effective_snapshot(principal, mission_id),
                service.list_run_revision_decisions(principal, mission_id, run_id))
            for decision in reversed(service.list_run_revision_decisions(principal, mission_id, run_id)):
                successor = runtime.workflow_store.find_run_by_idempotency_key(revision_successor_key(decision)[0])
                if successor:
                    observation.update(decisionStatus="SUCCESSOR_CREATED", successorRunId=successor.run_id)
                    break
            return observation
        except (RuntimeError, sqlite3.Error) as exc:
            raise HTTPException(status_code=503, detail="revision decision schema requires explicit upgrade") from exc

    @router.post("/missions/{mission_id}/runs/{run_id}/revision")
    async def decide_run_revision(mission_id: str, run_id: str, request: MissionRevisionDecision):
        service, principal, _ = revision_context(mission_id, run_id)
        load_run(run_id, mutable=True)
        try:
            result = service.decide_run_revision(principal, mission_id, run_id, request)
            return result.model_dump(by_alias=True, mode="json")
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail="semantic access denied") from exc
        except MissionRevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (RuntimeError, sqlite3.Error) as exc:
            raise HTTPException(status_code=503, detail="revision decision storage unavailable; retry same operation") from exc

    @router.post("/missions/{mission_id}/runs/{run_id}/revision/{operation_id}/apply", status_code=202)
    async def apply_run_revision(mission_id: str, run_id: str, operation_id: str):
        service, principal, source = revision_context(mission_id, run_id)
        try:
            service.require_write_access(principal, mission_id)
            receipt = next((r for r in service.list_run_revision_decisions(principal, mission_id, run_id)
                            if r.operation_id == operation_id), None)
            if receipt is None:
                raise HTTPException(status_code=404, detail="decision not found")
            if receipt.actor_id != principal.actor_id or receipt.tenant_id != principal.tenant_id:
                raise HTTPException(status_code=403, detail="decision principal mismatch")
            if receipt.decision != "REQUEST_REPLAN":
                raise HTTPException(status_code=409, detail="decision does not request replanning")
            # Stable namespace is independent of URL encoding and process lifetime.
            key, fingerprint = revision_successor_key(receipt)
            existing = runtime.workflow_store.find_run_by_idempotency_key(key)
            if existing is not None:
                if existing.record_state.value != "active":
                    raise HTTPException(status_code=409, detail="successor was deleted")
                await coordinator.submit(existing.run_id)
                return {"status": "SUCCESSOR_CREATED", "runId": existing.run_id}
            if source.status.value != "cancelled":
                raise HTTPException(status_code=409, detail="SOURCE_NOT_CANCELLED; explicitly cancel the source Run first")
            if coordinator.is_active(run_id):
                return {"status": "WAITING_CANCELLATION", "runId": run_id}
            choices = service.list_run_revision_decisions(principal, mission_id, run_id)
            if choices[-1].operation_id != operation_id:
                raise HTTPException(status_code=409, detail="DECISION_SUPERSEDED")
            # Original execution configuration, no inherited TaskPlan/ACG package.
            run_input = {k: v for k, v in source.input.items()
                         if k not in {"acgBlueprint", "taskPlan", "taskBindings"}}
            _, successor = runtime.prepare_run(mission_id, semantic_principal=principal,
                workflow_id=source.workflow_id, review_mode=source.review_mode,
                idempotency_key=key, idempotency_fingerprint=fingerprint,
                defer_acg_planning=True, input_override=run_input, parent_run_id=run_id,
                execution_scope_override=source.execution_scope,
                rerun_reason="mission_revision", mission_revision_decision=receipt.model_dump(by_alias=True, mode="json"))
            await coordinator.submit(successor.run_id)
            return {"status": "SUCCESSOR_CREATED", "runId": successor.run_id}
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail="semantic access denied") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (RuntimeError, sqlite3.Error) as exc:
            raise HTTPException(status_code=503, detail="revision application unavailable; retry same operation") from exc

    @router.post("/missions/{mission_id}/semantics")
    async def edit_mission_semantics(mission_id: str, request: MissionSemanticEditRequest):
        service, principal = require_semantic_service()
        require_visible_semantic_mission(service, principal, mission_id)
        try:
            result = service.commit(principal, MissionSemanticRequest(missionId=mission_id, **request.model_dump()))
            if result.status in {"REVISION_CONFLICT", "OPERATION_CONFLICT"}:
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=409, content=result.model_dump(by_alias=True, mode="json"))
            return result
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail="semantic access denied") from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="mission not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="invalid semantic request") from exc
        except (RuntimeError, SQLiteError) as exc:
            raise HTTPException(status_code=503, detail="semantic commit interrupted; retry the same operationId and body") from exc

    @router.get("/missions/{mission_id}/semantics")
    async def get_mission_semantics(mission_id: str):
        service, principal = require_semantic_service()
        require_visible_semantic_mission(service, principal, mission_id)
        try:
            return MissionSemanticResolver.resolve(service.get_effective_snapshot(principal, mission_id))
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail="semantic access denied") from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="mission not found") from exc
        except (ValueError, RuntimeError, SQLiteError) as exc:
            raise HTTPException(status_code=503, detail="mission semantic source unavailable") from exc

    @router.get("/missions/{mission_id}/semantics/commits")
    async def list_mission_semantic_commits(mission_id: str):
        service, principal = require_semantic_service()
        require_visible_semantic_mission(service, principal, mission_id)
        try:
            return {"items": service.list_commits(principal, mission_id)}
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail="semantic access denied") from exc

    @router.get("/missions/{mission_id}/semantics/receipts/{operation_id}")
    async def get_mission_semantic_receipt(mission_id: str, operation_id: str):
        service, principal = require_semantic_service()
        require_visible_semantic_mission(service, principal, mission_id)
        try:
            receipt = service.get_receipt(principal, mission_id, operation_id)
            if receipt is None:
                raise HTTPException(status_code=404, detail="semantic receipt not found")
            return receipt
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail="semantic access denied") from exc

    @router.post("/mission-launches/reconcile")
    async def reconcile_mission_launch(request: MissionCreateRequest):
        """Read caller-scoped creation anchors, including Mission-without-Run.

        The original wire body is hashed by the same server authority as POST
        missions. No client fingerprint, request contents or other owner's IDs
        are returned. This endpoint never submits or repairs an execution.
        """
        actor = current_trusted_user()
        if actor is None:
            raise HTTPException(status_code=401, detail="trusted user context required")
        if not request.client_request_id or not request.client_request_id.strip():
            raise HTTPException(status_code=422, detail="clientRequestId is required")
        key, fingerprint = _idempotency(request)
        task = runtime.workflow_store.find_mission_by_creation_key(key)
        run = runtime.workflow_store.find_run_by_idempotency_key(key)
        # Missing ownership is not an implicit grant for this new lookup API.
        for record in (task, run):
            if record is not None and (
                str(record.input.get("authenticatedUserId") or "") != actor.user_id
                or str(record.input.get("authenticatedTenantId") or "") != (actor.tenant_id or "")
            ):
                return {"status": "NOT_FOUND"}
        if task is None:
            return {"status": "REQUIRES_REVIEW" if run is not None else "NOT_FOUND"}
        if task.creation_fingerprint != fingerprint or (run is not None and run.idempotency_fingerprint != fingerprint):
            return {"status": "CONFLICT", "missionId": task.mission_id}
        if task.record_state is not MissionRecordState.ACTIVE or (run is not None and (
            run.mission_id != task.mission_id or run.record_state is RunRecordState.DELETED
        )):
            return {"status": "REQUIRES_REVIEW", "missionId": task.mission_id}
        if run is None:
            if request.semantics is not None and getattr(runtime, "mission_semantic_service", None) is not None:
                receipt = runtime.workflow_store.get_semantic_receipt(task.mission_id, "create:" + key)
                if receipt is not None and receipt.result.status not in {"COMMITTED", "NO_OP"}:
                    return {"status": "REQUIRES_REVIEW", "missionId": task.mission_id}
            return {"status": "CREATING", "missionId": task.mission_id}
        return {"status": "CREATED", "missionId": task.mission_id, "runId": run.run_id,
                "run": project_control_run(run)}

    @router.post(
        "/missions",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=MissionResponse,
        response_model_by_alias=True,
    )
    async def create_mission(request: MissionCreateRequest):
        service = getattr(runtime, "mission_semantic_service", None)
        if service is not None:
            require_semantic_service()
        if service is not None and not runtime.allow_legacy_mission_intent and request.semantics is None:
            raise HTTPException(status_code=422, detail="explicit semantics are required")
        if request.semantics is not None and (not request.client_request_id or not request.client_request_id.strip()):
            raise HTTPException(status_code=422, detail="clientRequestId is required for semantic creation")
        key, fingerprint = _idempotency(request)
        if key:
            existing = runtime.workflow_store.find_run_by_idempotency_key(key)
            if existing is not None:
                _require_access(existing)
                if existing.record_state is RunRecordState.DELETED:
                    raise HTTPException(status_code=404, detail="run not found")
                if existing.idempotency_fingerprint != fingerprint:
                    raise HTTPException(status_code=409, detail="clientRequestId conflict",
                                        headers={"X-Mission-Launch-Conflict": "CLIENT_REQUEST_ID_CONFLICT"})
                if service is not None:
                    require_visible_semantic_mission(service, current_semantic_principal(), existing.mission_id)
                try:
                    await coordinator.submit(existing.run_id)
                except Exception as exc:
                    raise HTTPException(status_code=503, detail="run submission interrupted; retry the same clientRequestId and body") from exc
                return project_control_run(existing, MissionResponse)
        try:
            mission_input = prepare_execution_input(
                request.input, request.material_refs, request.attachment_ids
            )
            # Stable creation key plus insert-only persistence is the durable recovery
            # anchor. Identity projection and semantic receipt are replayed below.
            task = runtime.create_mission(
                title=request.title,
                domain=request.domain,
                intent=request.intent,
                input=mission_input,
                security_level=request.security_level,
                priority=request.priority,
                workflow_id=request.workflow_id,
                enabled_plugin_ids=request.enabled_plugin_ids,
                defer_identity_projection=True,
                **({"creation_key": key, "creation_fingerprint": fingerprint} if key else {}),
            )
            if service is not None and request.semantics is not None:
                result = service.commit(current_semantic_principal(), MissionSemanticRequest(
                    missionId=task.mission_id, operationId="create:" + key,
                    expectedMissionRevision=0, **request.semantics.model_dump()))
                if result.status not in {"COMMITTED", "NO_OP"}:
                    raise HTTPException(status_code=409, detail=result.model_dump(by_alias=True, mode="json"),
                                        headers={"X-Mission-Launch-Conflict": "MISSION_SEMANTIC_CONFLICT"})
            _, run = runtime.prepare_run(
                task.mission_id,
                semantic_principal=current_semantic_principal(),
                workflow_id=request.workflow_id,
                review_mode=request.review_mode,
                idempotency_key=key,
                idempotency_fingerprint=fingerprint,
                enabled_plugin_ids=request.enabled_plugin_ids,
                defer_acg_planning=True,
            )
            await coordinator.submit(run.run_id)
            return project_control_run(runtime.get_status(run.run_id), MissionResponse)
        except AttachmentError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail={"code": exc.code, "message": str(exc)},
                headers={"X-Mission-Launch-Conflict": exc.code} if exc.status_code == 409 else None,
            ) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail="semantic access denied") from exc
        except (KeyError, ValueError) as exc:
            if str(exc) == "mission creation request conflict":
                raise HTTPException(status_code=409, detail="clientRequestId conflict",
                                    headers={"X-Mission-Launch-Conflict": "CLIENT_REQUEST_ID_CONFLICT"}) from exc
            logger.exception(
                "mission_start_rejected",
                extra={"errorType": type(exc).__name__},
            )
            if isinstance(exc, TaskDecompositionError):
                detail = "ACG task planning validation failed after one repair (TASK_PLAN_VALIDATION_FAILED)"
            elif isinstance(exc, ACGPlanningError):
                detail = "ACG planning failed (ACG_PLANNING_FAILED)"
            else:
                detail = "invalid workflow request"
            raise HTTPException(status_code=422, detail=detail) from exc
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("mission_creation_interrupted")
            raise HTTPException(status_code=503, detail="mission creation interrupted; retry the same clientRequestId and body") from exc

    @router.get("/runs")
    async def list_runs(
        status_value: str | None = Query(default=None, alias="status"),
        statuses_value: str | None = Query(default=None, alias="statuses"),
        domain: str | None = None,
        workflow_id: str | None = Query(default=None, alias="workflowId"),
        mission_id: str | None = Query(default=None, alias="missionId"),
        lifecycle_phase: str | None = Query(default=None, alias="lifecyclePhase"),
        source: str | None = None,
        sources_value: str | None = Query(default=None, alias="sources"),
        record_state: MissionRecordState = Query(default=MissionRecordState.ACTIVE, alias="recordState"),
        _summary: bool = Query(default=True, alias="summary"),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
    ):
        actor = current_trusted_user()
        common = dict(
            status=status_value,
            statuses=_csv_values(statuses_value),
            domain=domain,
            workflow_id=workflow_id,
            mission_id=mission_id,
            lifecycle_phase=lifecycle_phase,
            source=source,
            sources=_csv_values(sources_value),
            mission_record_state=record_state,
            owner_user_id=(actor.user_id if actor else None),
            owner_tenant_id=(actor.tenant_id if actor else None),
            page=page,
            page_size=page_size,
        )
        if _summary:
            # Payload-free fast path: summary columns + mission title only.
            # Heavy keys keep their project_run shape so list consumers that
            # tolerate missing bodies see empty collections, not new contracts.
            result = runtime.workflow_store.list_run_overviews(**common)
            return {
                "items": [
                    {
                        "runId": item.run_id,
                        "missionId": item.mission_id,
                        "title": item.title,
                        "workflowId": item.workflow_id,
                        "domain": item.domain,
                        "source": item.source,
                        "status": item.status.value,
                        "lifecyclePhase": item.lifecycle_phase,
                        "lifecycleMessage": item.lifecycle_message,
                        "currentStepId": item.current_step_id,
                        "completedStepIds": [],
                        "activeStepIds": [],
                        "skippedStepIds": [],
                        "outputRef": None,
                        "runtimeRevision": item.runtime_revision,
                        "executionState": {},
                        "steps": [],
                        "createdAt": item.created_at,
                        "updatedAt": item.updated_at,
                        "startedAt": item.started_at,
                    }
                    for item in result.items
                ],
                "total": result.total,
                "page": result.page,
                "pageSize": result.page_size,
            }
        result = runtime.workflow_store.list_runs(**common)
        return {
            "items": [project(run) for run in result.items],
            "total": result.total,
            "page": result.page,
            "pageSize": result.page_size,
        }

    @router.get("/runs/{run_id}")
    async def get_run(run_id: str):
        # A capability snapshot and its displayed Run must share one authority
        # revision; do not combine a cached status with fresh permission offers.
        try:
            run = runtime.workflow_store.get_run(run_id)
        except KeyError as exc:
            raise HTTPException(404, 'run not found') from exc
        _require_access(run)
        if run.record_state == RunRecordState.DELETED:
            raise HTTPException(404, 'run not found')
        require_current_mission_read(run.mission_id)
        result = project(run)
        if run.execution_state.get("planningCommitRequired"):
            result["formalControl"] = project_initial_control(runtime, run)
        result['actionCapabilities'] = project_run_capabilities(runtime, run, formal_control=result.get('formalControl'))
        return result

    @router.get("/runs/{run_id}/tool-approvals")
    async def formal_tool_approvals(run_id: str):
        load_run(run_id, readonly=True)  # existing authenticated owner boundary
        from app.tools.permissions import get_chat_permission_service
        service = get_chat_permission_service()
        pending = getattr(runtime, "formal_tool_pending", {})
        return {"items": [item for key,item in pending.items()
                          if item["sessionId"] == run_id and service.pending(key) is not None]}

    @router.post("/runs/{run_id}/tool-approvals/{approval_id}")
    async def resolve_formal_tool_approval(run_id: str, approval_id: str, decision: dict):
        source = load_run(run_id, mutable=True)
        if source.status != WorkflowStatus.RUNNING or not source.execution_state.get('executionPermitId'):
            raise HTTPException(409, 'Run is not awaiting a formal tool decision')
        from app.tools.permissions import get_chat_permission_service, ApprovalDecision, ApprovalResolutionError
        pending = getattr(runtime, "formal_tool_pending", {}).get(approval_id)
        if not pending or pending["sessionId"] != run_id:
            raise HTTPException(404,"approval not found")
        if decision.get("decision") not in {"allow_once","deny"}:
            raise HTTPException(400,"one operation decision required")
        try:
            result = await get_chat_permission_service().resolve(approval_id,
                decision=ApprovalDecision(decision["decision"]),session_id=run_id,
                invocation_id=pending["invocationId"],capability_id=pending["capabilityId"],
                relative_path=pending["relativePath"])
        except ApprovalResolutionError as exc:
            raise HTTPException(exc.status_code,exc.code) from exc
        runtime.formal_tool_pending.pop(approval_id,None)
        return {"resolved":True}

    @router.get("/runs/{run_id}/history-config")
    async def get_history_config(run_id: str):
        run = load_run(run_id)
        try:
            title = runtime.workflow_store.get_mission(run.mission_id).title
        except KeyError:
            title = None
        return project_history_config(run, title=title)

    @router.get("/runs/{run_id}/resource-usage")
    async def get_resource_usage(run_id: str):
        run = load_run(run_id)
        calls = _model_call_projection(run)
        usage = {
            key: sum(int(call["usage"][key]) for call in calls)
            for key in (
                "inputTokens", "outputTokens", "cacheReadTokens", "cacheWriteTokens",
                "reasoningTokens", "totalTokens",
            )
        }
        pressures = [call["contextPressure"] for call in calls if call["contextPressure"] is not None]
        observed_capability = next((call["capability"] for call in reversed(calls) if call["capability"]), None)
        capability = observed_capability
        output_policy_value = (calls[-1]["outputPolicy"] if calls else None)
        if capability is None:
            capability = _declared_capability_hint(runtime)
            if isinstance(capability, dict):
                output_policy_value = output_policy_value or "catalog_default"
        if calls:
            capability_source = "observed"
        elif isinstance(capability, dict) and capability is not observed_capability:
            capability_source = "declared"
        else:
            capability_source = None
        context_window = (
            capability.get("contextWindowTokens")
            if isinstance(capability, dict)
            else None
        )
        input_values = [int(call["usage"]["inputTokens"]) for call in calls]
        current_input_tokens = input_values[-1] if input_values else None
        peak_input_tokens = max(input_values) if input_values else None
        manifests = runtime.content_manifest_store.list_manifests(owner_type="run", owner_id=run_id)
        artifact_manifests = [item for item in manifests if item.kind is ContentKind.ARTIFACT]
        intermediate_manifests = [item for item in manifests if item.kind is ContentKind.INTERMEDIATE]
        total_steps = len(run.steps)
        completed_steps = len(run.completed_step_ids)
        return {
            "runId": run_id,
            "capability": capability,
            "capabilitySource": capability_source,
            "outputPolicy": output_policy_value,
            "usage": {
                **usage,
                "callCount": len(calls),
                "retryCount": sum(1 for call in calls if str(call.get("effectiveReason") or "").startswith("retry")),
                "latencyMs": sum(int(call["latencyMs"]) for call in calls),
                "cacheHitRatio": (
                    round(usage["cacheReadTokens"] / usage["inputTokens"], 4)
                    if usage["inputTokens"]
                    else None
                ),
            },
            "contextPressure": {
                "current": pressures[-1] if pressures else None,
                "peak": max(pressures) if pressures else None,
                "currentInputTokens": current_input_tokens,
                "peakInputTokens": peak_input_tokens,
                "contextWindowTokens": context_window,
                "source": (
                    "usage_derived"
                    if pressures
                    else "capability_declared"
                    if context_window
                    else "unknown"
                ),
            },
            "composition": {
                "materialManifestCount": len(run.input.get("materialRefs") or []),
                "materialFragmentCount": sum(
                    runtime.content_manifest_store.get_manifest(item).fragment_count
                    for item in run.input.get("materialRefs") or []
                ),
                "taskCount": total_steps,
                "completedTaskCount": completed_steps,
                "persistedResultFragmentCount": sum(item.fragment_count for item in intermediate_manifests),
                "reducerManifestCount": len(intermediate_manifests),
                "chapterCount": sum(item.fragment_count for item in artifact_manifests),
                "artifactCount": len(artifact_manifests),
                "assemblyComplete": bool(artifact_manifests and all(item.sealed for item in artifact_manifests)),
                "taskProgress": round(completed_steps / total_steps, 4) if total_steps else None,
            },
            "scheduler": {
                "activeSlots": len(run.active_step_ids),
                "queueDepth": max(0, total_steps - completed_steps - len(run.active_step_ids)),
                "checkpointCount": 1 if run.execution_state.get("checkpointId") else 0,
                "recoveryCount": len(run.execution_state.get("graphPatchRefs") or []),
            },
        }

    @router.get("/runs/{run_id}/resource-usage/calls")
    async def get_resource_usage_calls(
        run_id: str,
        step_id: str | None = Query(default=None, alias="stepId"),
        cursor: str | None = None,
        page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
    ):
        run = load_run(run_id)
        calls = _model_call_projection(run)
        if step_id:
            calls = [call for call in calls if call["stepId"] == step_id]
        try:
            start = int(cursor or 0)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="invalid cursor") from exc
        if start < 0:
            raise HTTPException(status_code=422, detail="invalid cursor")
        items = calls[start:start + page_size]
        next_cursor = str(start + page_size) if start + page_size < len(calls) else None
        return {"runId": run_id, "items": items, "nextCursor": next_cursor, "total": len(calls)}

    @router.get("/runs/{run_id}/graph")
    async def get_graph(run_id: str):
        runtime_run = load_run(run_id)
        if identity_queries is None:
            return project_graph(runtime_run)
        query, _ = require_run_access(run_id)
        tree = query.run_execution_tree(run_id)
        graph = tree.blueprint.graph
        state = _state(runtime_run)
        return {
            "runId": run_id,
            "blueprintId": tree.blueprint.blueprint_id,
            "graphId": tree.blueprint.graph_id,
            "graphVersion": tree.run.graph_version,
            "nodes": list(graph.get("nodes") or []),
            "edges": list(graph.get("edges") or []),
            "taskBindings": [
                {
                    "nodeId": node.task.task_id,
                    "acgNodeId": node.acg_node_id,
                }
                for node in tree.nodes
                if node.acg_node_id is not None
            ],
            "completedStepIds": list(runtime_run.completed_step_ids),
            "activeStepIds": list(runtime_run.active_step_ids),
            "skippedStepIds": list(runtime_run.execution_state.get("skippedStepIds") or []),
            "graphPatchRefs": list(state.get("graphPatchRefs") or []),
            "resourceBindings": dict(state.get("resourceBindings") or {}),
            "source": "agentos-v2",
        }

    @router.get("/runs/{run_id}/outputs/{output_ref}")
    async def get_output(run_id: str, output_ref: str):
        # An output may contain the same artifact body. Recheck the Workflow
        # record through the read-only cache: a lagging Identity projection must
        # not hide deletion or downgrade a frozen Mission's read authority.
        run = load_content_run(run_id)
        identity_run = (
            identity_repositories.runs.get(run_id)
            if identity_repositories is not None
            else None
        )
        if identity_run is not None:
            require_run_access(run_id)
        else:
            allowed = set((_state(run).get("outputRefs") or {}).values())
            if output_ref not in allowed:
                raise HTTPException(status_code=404, detail="output not found")
        try:
            content = runtime.execution_value_store.get_output(run_id=run_id, output_ref=output_ref)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="output not found") from exc
        return {"runId": run_id, "outputRef": output_ref, "content": content}

    @router.get("/runs/{run_id}/context-packs")
    async def list_context_packs(run_id: str):
        # ContextPack bodies live in the run-scoped execution value store. Read
        # only the references belonging to this run, then return bounded
        # metadata so the Inspector can explain the context flow without
        # exposing the complete model input body.
        identity_run = (
            identity_repositories.runs.get(run_id)
            if identity_repositories is not None
            else None
        )
        if identity_run is not None:
            require_mission_owner_access(identity_run.mission_id)
            metadata = dict(identity_run.metadata or {})
            projection = dict(metadata.get("executionProjection") or {})
            raw_refs = projection.get("contextRefs") or {}
        else:
            run = load_run(run_id, readonly=True)
            raw_refs = _state(run).get("contextRefs") or {}

        refs = raw_refs if isinstance(raw_refs, dict) else {}
        items: list[dict[str, Any]] = []
        for step_id, context_ref in refs.items():
            if not isinstance(context_ref, str) or not context_ref:
                continue
            try:
                payload = runtime.execution_value_store.get_context_pack(
                    run_id=run_id,
                    context_ref=context_ref,
                )
            except (KeyError, ValueError):
                payload = None
            items.append(_context_pack_summary(str(step_id), context_ref, payload))

        return {"runId": run_id, "items": items, "total": len(items)}

    @router.get("/runs/{run_id}/artifacts")
    async def list_artifacts(run_id: str):
        content_run = load_content_run(run_id)
        if identity_repositories is not None:
            identity_run = identity_repositories.runs.get(run_id)
            if identity_run is not None:
                details = identity_queries.artifacts_for_run(run_id)
                if (details or identity_repositories.run_artifact_bindings.list_for_run(run_id)
                        or (content_run.review_mode == 'human_in_loop' and content_run.execution_state.get('planningCommitRequired'))):
                    items = [project_identity_artifact(item) for item in details]
                    return {"runId": run_id, "items": items, "total": len(items)}
        items = runtime.content_manifest_store.list_manifests(
            owner_type="run", owner_id=run_id, kind=ContentKind.ARTIFACT
        )
        return {
            "runId": run_id,
            "items": [item.model_dump(by_alias=True, mode="json") for item in items],
            "total": len(items),
        }

    @router.get("/runs/{run_id}/artifacts/{manifest_id}")
    async def get_artifact(run_id: str, manifest_id: str):
        load_content_run(run_id)
        if identity_repositories is not None:
            identity_run = identity_repositories.runs.get(run_id)
            if identity_run is not None:
                for detail in identity_queries.artifacts_for_run(run_id):
                    if manifest_id in {detail.artifact.artifact_id, detail.artifact.content_ref}:
                        return project_identity_artifact(detail)
        manifest = require_manifest_access(manifest_id)
        if manifest.owner_type != "run" or manifest.owner_id != run_id or manifest.kind is not ContentKind.ARTIFACT:
            raise HTTPException(status_code=404, detail="artifact not found")
        return manifest.model_dump(by_alias=True, mode="json")

    @router.get("/runs/{run_id}/artifacts/{manifest_id}/fragments")
    async def get_artifact_fragments(
        run_id: str,
        manifest_id: str,
        cursor: str | None = None,
        page_size: int = Query(default=20, alias="pageSize", ge=1, le=200),
    ):
        manifest = await get_artifact(run_id, manifest_id)
        try:
            page, next_cursor = runtime.content_manifest_store.read_page(
                manifest["manifestId"], cursor=cursor, page_size=page_size
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        # Page readers must reject corrupt bytes as well as complete downloads.
        if not manifest.get("sealed") or any(
            hashlib.sha256(payload).hexdigest() != ref.checksum or len(payload) != ref.byte_length
            for ref, payload in page
        ):
            raise HTTPException(status_code=503, detail="Artifact content integrity unavailable")
        return {
            "manifest": manifest,
            "items": [
                {
                    **ref.model_dump(by_alias=True, mode="json"),
                    "content": payload.decode("utf-8", errors="replace"),
                }
                for ref, payload in page
            ],
            "nextCursor": next_cursor,
        }

    @router.post(
        "/missions/{mission_id}/runs",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=RunResponse,
        response_model_by_alias=True,
    )
    async def create_mission_run(mission_id: str, request: MissionRunCreateRequest):
        """Create a new Run under an existing Mission using the submitted configuration snapshot."""

        require_mission_access(mission_id)
        source_run = load_run(request.source_run_id, write=True)
        if source_run.mission_id != mission_id:
            raise HTTPException(status_code=409, detail="source run belongs to another mission")
        if source_run.status.value not in {"completed", "failed", "cancelled", "superseded"}:
            raise HTTPException(status_code=409, detail="source run must be terminal before rerun")
        key, fingerprint = _idempotency(request)
        if key:
            existing = runtime.workflow_store.find_run_by_idempotency_key(key)
            if existing is not None:
                _require_access(existing)
                if existing.mission_id != mission_id or existing.idempotency_fingerprint != fingerprint:
                    raise HTTPException(status_code=409, detail="clientRequestId conflict")
                if existing.record_state is RunRecordState.DELETED:
                    raise HTTPException(status_code=404, detail="run not found")
                try:
                    await coordinator.submit(existing.run_id)
                except Exception as exc:
                    raise HTTPException(status_code=503, detail="run submission interrupted; retry the same clientRequestId and body") from exc
                return project_control_run(existing)
        try:
            assert_mutable_run(source_run)
            run_input = prepare_execution_input(
                request.input, request.material_refs, request.attachment_ids
            )
            _, run = runtime.prepare_run(
                mission_id,
                semantic_principal=current_semantic_principal(),
                workflow_id=request.workflow_id or source_run.workflow_id,
                review_mode=request.review_mode,
                idempotency_key=key,
                idempotency_fingerprint=fingerprint,
                enabled_plugin_ids=request.enabled_plugin_ids,
                defer_acg_planning=True,
                input_override=run_input,
                parent_run_id=source_run.run_id,
                rerun_reason=request.rerun_reason,
            )
            await coordinator.submit(run.run_id)
            return project_control_run(runtime.get_status(run.run_id))
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail="semantic access denied") from exc
        except (KeyError, ValueError) as exc:
            logger.exception(
                "agentos_v2_run_create_failed",
                extra={"missionId": mission_id, "sourceRunId": request.source_run_id},
            )
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except (RuntimeError, SQLiteError) as exc:
            raise HTTPException(status_code=503, detail="run preparation or submission interrupted; retry the same clientRequestId and body") from exc

    @router.post(
        "/runs/{run_id}/steps/{step_id}/retry",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=RunResponse,
        response_model_by_alias=True,
    )
    async def retry_failed_step(run_id: str, step_id: str, request: SingleStepRetryRequest):
        """Reuse committed outputs and continue from the selected failed step."""

        source_run = load_run(run_id, write=True)
        # Internal Planner recovery retains its existing authority. Public
        # operators create successors and cannot rewrite a terminal source.
        if request.mode == 'current_run':
            raise HTTPException(409, 'public retry requires successor_run')
        key, fingerprint = _single_step_retry_idempotency(run_id, step_id, request)
        existing = (
            runtime.workflow_store.find_run_by_idempotency_key(key)
            if request.mode == "successor_run"
            else None
        )
        if existing is not None:
            _require_access(existing)
            if existing.idempotency_fingerprint != fingerprint:
                raise HTTPException(status_code=409, detail="clientRequestId conflict")
            if existing.record_state is RunRecordState.DELETED:
                raise HTTPException(status_code=404, detail="run not found")
            try:
                await coordinator.submit(existing.run_id)
            except Exception as exc:
                raise HTTPException(status_code=503, detail="run submission interrupted; retry the same clientRequestId and body") from exc
            return project_control_run(existing)
        try:
            assert_mutable_run(source_run)
            retry_run = runtime.prepare_single_step_retry(
                source_run_id=source_run.run_id,
                step_id=step_id,
                reason=request.reason,
                expected_runtime_revision=request.expected_runtime_revision,
                idempotency_key=key,
                idempotency_fingerprint=fingerprint,
                reuse_source_run=request.mode == "current_run",
            )
            await coordinator.submit(retry_run.run_id)
            return project_control_run(runtime.get_status(retry_run.run_id))
        except (KeyError, ValueError) as exc:
            logger.warning(
                "agentos_v2_single_step_retry_rejected",
                extra={"sourceRunId": run_id, "stepId": step_id, "errorType": type(exc).__name__},
            )
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (RuntimeError, SQLiteError) as exc:
            raise HTTPException(status_code=503, detail="step retry preparation or submission interrupted; retry the same clientRequestId and body") from exc

    @router.get("/runs/{run_id}/artifacts/{manifest_id}/download")
    async def download_artifact(run_id: str, manifest_id: str):
        from fastapi.responses import StreamingResponse
        from starlette.background import BackgroundTask

        manifest = await get_artifact(run_id, manifest_id)
        # The store validates the aggregate checksum at the END of assembly.
        # Verify a bounded-memory snapshot before sending HTTP 200/any bytes;
        # otherwise a late generator failure already exposed corrupt content.
        verified = SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b")
        try:
            for chunk in runtime.content_manifest_store.stream_assembly(manifest["manifestId"]):
                verified.write(chunk)
            if verified.tell() != manifest["byteLength"]:
                raise ValueError("artifact length mismatch")
            verified.seek(0)
        except (KeyError, ValueError, TypeError, OSError, SQLiteError) as exc:
            verified.close()
            raise HTTPException(status_code=503, detail="Artifact content integrity unavailable") from exc

        def verified_chunks():
            try:
                while chunk := verified.read(64 * 1024):
                    yield chunk
            finally:
                verified.close()

        return StreamingResponse(
            verified_chunks(),
            media_type=manifest["mediaType"],
            headers={"Content-Disposition": f'attachment; filename="{manifest_id}.md"',
                     "Content-Length": str(manifest["byteLength"])},
            background=BackgroundTask(verified.close),
        )

    @router.get("/runs/{run_id}/legacy-outputs")
    async def get_legacy_outputs(run_id: str):
        run = load_run(run_id)
        if _state(run).get("outputRefs"):
            raise HTTPException(status_code=404, detail="legacy outputs not found")
        items = [
            {
                "stepId": step.step_id,
                "name": step.name,
                "status": step.status.value,
                "content": dict(step.output),
            }
            for step in run.steps
            if isinstance(step.output, dict) and step.output
        ]
        if not items:
            raise HTTPException(status_code=404, detail="legacy outputs not found")
        return {"runId": run_id, "items": items}

    @router.get("/runs/{run_id}/trace")
    def get_trace(run_id: str, view: str | None = Query(default=None, pattern="^workspace$")):
        run = load_run(run_id, readonly=True)
        exported = runtime.trace_store.export_json(run, workspace=True) if view == "workspace" else runtime.trace_store.export_json(run)
        exported["events"] = [_redact(item) for item in exported.get("events", [])]
        return exported

    @router.get("/runs/{run_id}/events")
    async def stream_runtime_events(run_id: str):
        # Authorize before opening the long-lived broker subscription.  The
        # broker is run-scoped, but it is not an access-control boundary.
        run = load_run(run_id)

        async def body():
            terminal_event = {
                "completed": "run.completed",
                "failed": "run.failed",
                "cancelled": "run.cancelled",
            }.get(run.status.value)
            if terminal_event:
                event = RuntimeEvent(
                    eventType=terminal_event, runId=run_id, sequence=0,
                    payload={"status": run.status.value},
                )
                payload = json.dumps(event.model_dump(by_alias=True, mode="json"), ensure_ascii=False)
                yield f"event: {event.event_type}\ndata: {payload}\n\n"
                return
            try:
                async for event in runtime_event_broker.subscribe(run_id):
                    payload = json.dumps(event.model_dump(by_alias=True, mode="json"), ensure_ascii=False)
                    yield f"event: {event.event_type}\ndata: {payload}\n\n"
                    if event.event_type in {"run.completed", "run.failed", "run.cancelled"}:
                        break
            except RuntimeEventOverflow:
                # A slow observer is disconnected explicitly; the workflow is
                # never cancelled because an SSE consumer fell behind.
                yield (
                    "event: runtime.subscriber.overflow\n"
                    "data: {\"errorCode\":\"RUNTIME_SSE_SLOW_SUBSCRIBER\"}\n\n"
                )
        return StreamingResponse(
            body(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.get("/runs/{run_id}/provenance")
    async def get_provenance(run_id: str):
        run = load_run(run_id, readonly=True)
        ledger = runtime.provenance_store.load_ledger(run_id=run.run_id, mission_id=run.mission_id)
        events = ledger.trace_events()
        legacy = run.provenance if isinstance(run.provenance, dict) else {}
        if not events and any(isinstance(legacy.get(key), list) and legacy[key] for key in ("productions", "consumptions", "interactions")):
            common = {"eventId", "runId", "missionId", "attempt", "previousHash", "eventHash", "createdAt"}
            return {
                "runId": run.run_id,
                "schemaVersion": legacy.get("schemaVersion"),
                "integrityStatus": legacy.get("integrityStatus", "unknown"),
                "productions": _legacy_provenance_items(legacy.get("productions"), common | {
                    "producerStepId", "agentName", "checksum", "fieldNames", "tokenSize", "evidenceRefs",
                }),
                "consumptions": _legacy_provenance_items(legacy.get("consumptions"), common | {
                    "consumerStepId", "producerStepIds", "consumerAgentName", "producerEventIds",
                    "consumedFields", "fieldsByProducer", "tokensDelivered", "tokensAvailable",
                    "savingRatio", "contractStatus", "checksum",
                }),
                "interactions": _legacy_provenance_items(legacy.get("interactions"), common | {
                    "interactionId", "edgeIds", "producerStepIds", "consumerStepId",
                    "producerAgentNames", "consumerAgentName", "fieldsByProducer", "tokensDelivered",
                    "tokensAvailable", "savingRatio", "evidenceRefs", "contractStatus", "checksum",
                }),
                "legacy": True,
            }
        return {
            "runId": run.run_id,
            "integrityStatus": "valid" if ledger.verify_integrity() else "invalid",
            "events": events,
        }

    @router.get("/runs/{run_id}/checkpoints")
    async def get_checkpoints(run_id: str):
        run = load_run(run_id)
        checkpoint_id = str(run.execution_state.get("checkpointId") or "")
        items = []
        if checkpoint_id:
            items.append(
                {
                    "checkpointId": checkpoint_id,
                    "version": runtime.checkpoint_store.version(run_id=run_id, checkpoint_id=checkpoint_id),
                    "canResume": run.status.value == "waiting_review",
                }
            )
        return {"runId": run_id, "items": items, "total": len(items)}

    @router.get("/runs/{run_id}/reviews")
    async def get_reviews(run_id: str):
        load_run(run_id)
        reviews = runtime.list_reviews(run_id)
        return {
            "runId": run_id,
            "items": [item.model_dump(by_alias=True, mode="json") for item in reviews],
            "total": len(reviews),
        }

    @router.get("/runs/{run_id}/scheduling")
    async def get_scheduling(run_id: str):
        run = load_run(run_id)
        items = list(run.execution_state.get("schedulingDecisions") or [])
        return {"runId": run_id, "items": _redact(items), "total": len(items)}

    @router.get("/runs/{run_id}/memory-events")
    async def get_memory_events(run_id: str):
        # 该接口被前端秒级轮询；运行快照为数十 MB JSON，走缓存快路径避免
        # 每次轮询都全量反序列化（与 load_run 同样的鉴权与 404 语义）。
        try:
            run = runtime.get_status_cached(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc
        _require_access(run)
        items = []
        for event in run.trace:
            payload = event.payload if isinstance(event.payload, dict) else {}
            if "retrievalMode" in payload:
                items.append({
                    "kind": "memory_access",
                    "stepId": event.step_id,
                    "retrievalMode": payload.get("retrievalMode"),
                    "hitRefs": list(payload.get("hitRefs") or []),
                    "budget": payload.get("tokenBudget"),
                    "fallbackReason": payload.get("fallbackReason"),
                    "createdAt": event.created_at,
                })
            elif event.observation == "Structured memory event projected":
                items.append({"kind": "memory_event", **_redact(payload)})
            elif payload.get("kind") == "phase_capsule":
                items.append({"kind": "phase_capsule", **_redact(payload)})
        return {"runId": run_id, "items": items, "total": len(items)}

    @router.get("/evolution/active")
    async def get_active_evolution_policy():
        return runtime.evolution_service.store.active().model_dump(by_alias=True, mode="json")

    @router.get("/evolution/history")
    async def get_evolution_history():
        items = [
            item.model_dump(by_alias=True, mode="json")
            for item in runtime.evolution_service.store.list_versions()
        ]
        return {"items": items, "total": len(items)}

    @router.post("/runs/{run_id}/evolution-proposals")
    async def create_evolution_proposal(run_id: str):
        load_run(run_id)
        try:
            trajectory, evaluation, proposal = runtime.propose_evolution_from_run(run_id)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=409, detail="evolution proposal conflict") from exc
        return {
            "trajectory": trajectory.model_dump(by_alias=True, mode="json"),
            "evaluation": evaluation.model_dump(by_alias=True, mode="json"),
            "proposal": proposal.model_dump(by_alias=True, mode="json"),
        }

    @router.post("/evolution/proposals/{proposal_id}/approve")
    async def approve_evolution_proposal(
        proposal_id: str, request: EvolutionApprovalRequest
    ):
        try:
            version = runtime.approve_evolution_proposal(
                proposal_id,
                approved_by=request.reviewer,
            )
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=409, detail="evolution approval conflict") from exc
        return version.model_dump(by_alias=True, mode="json")

    @router.post("/evolution/rollback")
    async def rollback_evolution_policy(request: EvolutionRollbackRequest):
        try:
            version = runtime.evolution_service.rollback(
                request.target_version, approved_by=request.reviewer
            )
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=409, detail="evolution rollback conflict") from exc
        return version.model_dump(by_alias=True, mode="json")

    @router.get("/runs/{run_id}/copilot")
    async def get_copilot(run_id: str):
        run = load_run(run_id, readonly=True)
        return interaction.view(run_id, run)

    @router.post("/runs/{run_id}/copilot/permission")
    async def copilot_permission(run_id: str, request: CopilotPermissionRequest):
        source = load_run(run_id, mutable=True)
        if source.status.value not in {'pending', 'planning', 'running', 'retrying', 'waiting_review'}:
            raise HTTPException(409, 'terminal Run permission is immutable')
        return interaction.set_permission(run_id, request)

    @router.post("/runs/{run_id}/copilot/messages")
    async def copilot_message(run_id: str, request: CopilotMessageRequest):
        load_run(run_id)
        try:
            return await interaction.message(run_id, request)
        except ReviewConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid conversation request or model response") from exc
        except Exception as exc:
            logger.exception("Copilot model unavailable", extra={"runId": run_id})
            raise HTTPException(status_code=503, detail="任务模型暂时不可用，请稍后重试") from exc

    @router.post("/runs/{run_id}/copilot/messages/stream")
    async def copilot_message_stream(run_id: str, request: CopilotMessageRequest):
        load_run(run_id)

        async def events():
            async for event in interaction.stream_message(run_id, request):
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"

        return StreamingResponse(events(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @router.post("/runs/{run_id}/copilot/answers", status_code=202)
    async def copilot_answer(run_id: str, request: PlannerAnswerRequest):
        load_run(run_id, mutable=True)
        try:
            run = await interaction.answer(run_id, request)
        except ReviewConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if run.status == WorkflowStatus.RETRYING:
            await coordinator.submit(run_id)
        return interaction.view(run_id)

    @router.post("/runs/{run_id}/copilot/actions/preview")
    async def copilot_action_preview(run_id: str, request: TaskOperationPreviewRequest):
        load_run(run_id, mutable=True)
        try:
            return await interaction.preview_operation(run_id, request)
        except (ValueError, KeyError, ReviewConflictError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/runs/{run_id}/copilot/actions", status_code=202)
    async def copilot_action_apply(run_id: str, request: TaskOperationApplyRequest):
        load_run(run_id, mutable=True)
        try:
            receipt = await interaction.operations.apply(run_id, request)
        except (ValueError, KeyError, ReviewConflictError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        target_id = receipt["receipt"]["runId"]
        target = load_run(target_id)
        if target.status in {WorkflowStatus.PENDING, WorkflowStatus.RETRYING}:
            await coordinator.submit(target_id)
        return receipt

    @router.post(
        "/runs/{run_id}/reviews",
        response_model=ReviewResponse,
        response_model_by_alias=True,
    )
    async def apply_review(run_id: str, request: ReviewApplyRequest):
        source_run = load_run(run_id, mutable=True)
        try:
            run = await runtime.apply_review(
                ReviewDecision(
                    runId=run_id,
                    stepId=request.step_id,
                    decision=request.decision,
                    reviewer=request.reviewer,
                    comment=request.comment,
                    operationId=request.operation_id,
                    expectedRunUpdatedAt=request.expected_run_updated_at,
                    expectedStepStatus=request.expected_step_status,
                )
            )
            if request.decision is ReviewDecisionType.RERUN:
                operation_key = hashlib.sha256(
                    f"review-rerun:{run_id}:{request.operation_id}".encode()
                ).hexdigest()
                operation_fingerprint = hashlib.sha256(
                    f"{run_id}:{request.step_id}:{request.operation_id}".encode()
                ).hexdigest()
                _, run = runtime.prepare_run(
                    source_run.mission_id,
                    semantic_principal=current_semantic_principal(),
                    workflow_id=source_run.workflow_id,
                    review_mode=source_run.review_mode,
                    idempotency_key=operation_key,
                    idempotency_fingerprint=operation_fingerprint,
                    enabled_plugin_ids=source_run.enabled_plugin_ids,
                    defer_acg_planning=True,
                    input_override=dict(source_run.input),
                    parent_run_id=source_run.run_id,
                    rerun_reason="review_rerun",
                )
                await coordinator.submit(run.run_id)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail="semantic access denied") from exc
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=409, detail="review conflict") from exc
        return project_control_run(
            run,
            ReviewResponse,
            operationId=request.operation_id,
            decision=request.decision.value,
        )

    @router.post(
        "/runs/{run_id}/cancel",
        response_model=OperationResponse,
        response_model_by_alias=True,
    )
    async def cancel_run(run_id: str, request: RunCancelRequest | None = None):
        """协作式终止一个活跃运行；幂等，且对不可取消的终态返回固定冲突提示。"""
        source = load_run(run_id, mutable=True)
        if source.status.value not in {'pending', 'planning', 'running', 'retrying', 'waiting_review'}:
            raise HTTPException(409, 'run cannot be cancelled')
        try:
            run = (runtime.cancel(run_id, expected_runtime_revision=request.expected_runtime_revision)
                if request is not None and request.expected_runtime_revision is not None else runtime.cancel(run_id))
            await coordinator.cancel(run_id)
        except (InvalidStateTransition, ValueError) as exc:
            raise HTTPException(status_code=409, detail="run cannot be cancelled") from exc
        return project_control_run(run, OperationResponse, operation="cancel")

    @router.delete("/runs/{run_id}")
    async def delete_run(run_id: str):
        """软删除一个终态 Run：runtime 记录状态置 deleted，Identity 行并入同标记。

        两侧列表查询随即过滤，直达读取按 404 收敛；重复删除幂等返回当前状态。
        这里不走 ``load_run``——它对已删 Run 抛 404，会挡住幂等重放。
        """
        try:
            existing = getattr(runtime, "get_status_cached", runtime.get_status)(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc
        _require_access(existing)
        require_run_write_scope(existing)
        try:
            updated = runtime.workflow_store.set_run_record_state(run_id, RunRecordState.DELETED)
        except RuntimeRunRecordNotTerminalError as exc:
            raise HTTPException(status_code=409, detail="run is not terminal") from exc
        except ValueError as exc:
            if str(exc) == "deleted run record state is immutable":
                # DELETE 在 API 边界幂等：identity 行可能仍持旧标记，重复删除
                # 应收敛到当前状态而不是抛出误导性冲突。
                updated = existing
            else:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        if identity_repositories is not None and identity_repositories.runs.get(run_id) is not None:
            identity_repositories.runs.mark_deleted(run_id)
        return {
            "runId": updated.run_id,
            "missionId": updated.mission_id,
            "recordState": updated.record_state.value,
            "deletedAt": updated.deleted_at.isoformat() if updated.deleted_at else None,
        }

    return router


__all__ = ["EvolutionApprovalRequest", "EvolutionRollbackRequest", "MaterialCreateRequest", "MissionCreateRequest", "MissionRunCreateRequest", "ReviewApplyRequest", "create_router", "project_graph", "project_run"]
