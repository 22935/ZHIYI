"""AgentOS 部件化迁移的共享数据合同。

本包只提供跨部件可序列化的数据结构、枚举和稳定校验工具。它不依赖
mission_manager、planner、executor 等业务部件，因此可由任意部件安全导入。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
from typing import Any

from pydantic import BaseModel


def _normalize_json_value(value: Any) -> Any:
    """将允许的合同值递归规范化为严格 JSON 值。"""
    if isinstance(value, BaseModel):
        return _normalize_json_value(
            value.model_dump(by_alias=True, exclude_none=True, exclude_defaults=True)
        )
    if isinstance(value, Enum):
        return _normalize_json_value(value.value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("dictionary keys must be strings for stable JSON")
        return {key: _normalize_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [_normalize_json_value(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(
                item, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
            ),
        )
    raise TypeError(f"value of type {type(value).__name__} is not JSON-normalizable")


def stable_json_dumps(value: Any) -> str:
    """以 camelCase 别名、递归排序键和紧凑格式生成稳定 JSON 文本。"""
    normalized = _normalize_json_value(value)
    try:
        return json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise TypeError("value is not JSON-normalizable") from exc


def stable_checksum(value: Any) -> str:
    """返回稳定 JSON UTF-8 表示的 SHA-256 校验和。"""
    return sha256(stable_json_dumps(value).encode("utf-8")).hexdigest()


from .acg_lifecycle import AcgIdentityLifecyclePort
from .communication import ContextPackRef, MessageEnvelope
from .content import (
    ContentFragmentRef, ContentKind, ContentManifest, FragmentEnvelope,
    VerificationStatus, WorksetSpec, WorksetUnitKind,
)
from .compiled_acg import (
    BindingManifest, BindingRule, CommunicationManifestSpec, CommunicationMode,
    CommunicationRuleSpec, CompiledACGPackage, CompiledEdge, CompiledNodeKind,
    CompiledNodeSpec, ConditionalControlSpec, ConsensusControlSpec, ControlManifest,
    ControlRule, EvidenceManifest, EvidenceRule, LoopControlSpec, MemoryManifest,
    MemoryRule, ParallelControlSpec, SkillManifest, SkillRule,
)
from .capability import (
    AgentArchitecture,
    AgentFramework,
    CapabilityInvocation,
    CapabilityInvocationResult,
    CapabilityKind,
    CapabilityManifest,
    ModelCapabilityEnvelope,
    ModelCapabilitySource,
    ModelFeatureSet,
    ModelInvocationRequest,
    ModelInvocationResponse,
    ModelProvider,
    ModelOutputPolicy,
    ModelStreamEvent,
    ToolProtocol,
)
from .evolution import (
    EvolutionAction,
    GraphEvolutionProposal,
    SkillCandidate,
    SkillEvolutionProposal,
    SkillLifecycleState,
    Trajectory,
    TrajectoryEvaluation,
    TrajectoryStep,
)
from .execution import ExecutionOutcomeRef, ExecutionPackageRef, NodeExecutionPhase, NodeExecutionRecord
from .runtime_events import RuntimeEvent
from .identity import (
    AttemptId,
    BindingId,
    BlueprintId,
    RunId,
    StepExecutionId,
    TaskId,
    MissionId,
    generate_identity,
    new_attempt_id,
    new_binding_id,
    new_blueprint_id,
    new_run_id,
    new_step_execution_id,
    new_task_id,
    new_mission_id,
    validate_identity,
)
from .governance import AuditFinding, AuditRequest, PolicyDecision
from .memory import MemoryPolicy, MemoryQuery, MemoryRecord, MemoryType, MemoryWriteBatch
from .planning import (
    PlanExpansionRequest,
    TaskBindingPatch,
    TaskImplementationBinding,
    SemanticTaskRelationType,
    TaskPlan,
    PlannedTask,
    TaskPlanPatch,
    TaskPlanRelation,
)
from .recovery import (
    FailureEvent, FailureSource, FailureType, GraphPatch, GraphPatchRef, GraphPatchResult,
    RecoveryAction, RecoveryNodeTemplate, RecoveryPlan, RecoveryRecipe,
)
from .resource import (
    BindingRequirement,
    ComputeCapacity,
    DeploymentTier,
    ExecutionBinding,
    ResourceEndpoint,
    ResourceHealthStatus,
    ResourceLease,
    ResourceProfile,
    ResourceSnapshot,
    ResourceType,
    SchedulingDecision,
    SchedulingRequest,
)
from .task import TaskConstraint, TaskLifecycleEvent
from .workflow import GraphEdgeRef, GraphNodeRef, GraphRef


__all__ = [
    "AcgIdentityLifecyclePort", "AgentArchitecture", "AgentFramework", "AuditFinding", "AuditRequest",
    "CapabilityInvocation", "CapabilityInvocationResult", "CapabilityKind", "CompiledACGPackage",
    "ContentFragmentRef", "ContentKind", "ContentManifest", "FragmentEnvelope",
    "CompiledEdge", "CompiledNodeKind", "CompiledNodeSpec", "BindingManifest", "BindingRule",
    "SkillManifest", "SkillRule", "MemoryManifest", "MemoryRule", "EvidenceManifest", "EvidenceRule",
    "CommunicationManifestSpec", "CommunicationMode", "CommunicationRuleSpec", "ControlManifest",
    "ControlRule", "ConditionalControlSpec", "LoopControlSpec", "ParallelControlSpec", "ConsensusControlSpec",
    "AttemptId", "BindingId", "BlueprintId", "CapabilityManifest", "ContextPackRef", "EvolutionAction", "ExecutionOutcomeRef",
    "ExecutionPackageRef", "NodeExecutionPhase", "NodeExecutionRecord", "RuntimeEvent", "FailureEvent", "FailureSource", "FailureType", "RecoveryAction", "GraphEdgeRef", "GraphEvolutionProposal",
    "GraphNodeRef", "GraphPatch", "GraphPatchRef", "GraphPatchResult", "GraphRef", "MemoryPolicy", "MemoryQuery",
    "MemoryRecord", "MemoryType", "MemoryWriteBatch", "MessageEnvelope",
    "ModelCapabilityEnvelope", "ModelCapabilitySource", "ModelFeatureSet",
    "ModelInvocationRequest", "ModelInvocationResponse", "ModelProvider", "ModelOutputPolicy", "ModelStreamEvent", "PolicyDecision",
    "RecoveryNodeTemplate", "RecoveryPlan", "RecoveryRecipe", "BindingRequirement", "ExecutionBinding",
    "ComputeCapacity", "DeploymentTier", "ResourceEndpoint", "ResourceHealthStatus", "ResourceLease", "ResourceProfile", "ResourceSnapshot", "ResourceType",
    "RunId", "SchedulingDecision", "SchedulingRequest", "SkillCandidate", "SkillEvolutionProposal",
    "StepExecutionId", "TaskId", "TaskBindingPatch", "TaskImplementationBinding",
    "PlanExpansionRequest", "SemanticTaskRelationType", "TaskPlan", "PlannedTask", "TaskPlanPatch", "TaskPlanRelation",
    "MissionId", "generate_identity", "new_attempt_id", "new_binding_id",
    "new_blueprint_id", "new_run_id", "new_step_execution_id", "new_task_id",
    "new_mission_id", "validate_identity",
    "SkillLifecycleState", "TaskConstraint", "TaskLifecycleEvent", "ToolProtocol",
    "VerificationStatus", "WorksetSpec", "WorksetUnitKind",
    "Trajectory", "TrajectoryEvaluation", "TrajectoryStep", "stable_checksum",
    "stable_json_dumps",
]
