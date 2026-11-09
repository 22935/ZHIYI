"""Typed scheduler decisions without DAG state."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from contracts.resource import ExecutionBinding, ResourceLease


class FilterReason(str, Enum):
    DISABLED = "DISABLED"
    UNHEALTHY = "UNHEALTHY"
    NODE_UNHEALTHY = "NODE_UNHEALTHY"
    CAPABILITY_MISMATCH = "CAPABILITY_MISMATCH"
    RUNTIME_KIND_MISMATCH = "RUNTIME_KIND_MISMATCH"
    PLACEMENT_MISMATCH = "PLACEMENT_MISMATCH"
    TRUST_INSUFFICIENT = "TRUST_INSUFFICIENT"
    NOT_ALLOWED = "NOT_ALLOWED"
    EXCLUDED = "EXCLUDED"
    DOMAIN_MISMATCH = "DOMAIN_MISMATCH"
    DATA_ZONE_MISMATCH = "DATA_ZONE_MISMATCH"
    OWNER_SCOPE_MISMATCH = "OWNER_SCOPE_MISMATCH"
    LABEL_MISMATCH = "LABEL_MISMATCH"
    NO_CAPACITY = "NO_CAPACITY"
    COST_EXCEEDED = "COST_EXCEEDED"
    LATENCY_EXCEEDED = "LATENCY_EXCEEDED"
    REMOTE_EXECUTION_DISABLED = "REMOTE_EXECUTION_DISABLED"
    MODEL_ENDPOINT_UNAVAILABLE = "MODEL_ENDPOINT_UNAVAILABLE"
    NODE_CPU_INSUFFICIENT = "NODE_CPU_INSUFFICIENT"
    NODE_MEMORY_INSUFFICIENT = "NODE_MEMORY_INSUFFICIENT"
    NODE_GPU_TYPE_MISMATCH = "NODE_GPU_TYPE_MISMATCH"
    NODE_GPU_MEMORY_INSUFFICIENT = "NODE_GPU_MEMORY_INSUFFICIENT"
    NODE_LABEL_MISMATCH = "NODE_LABEL_MISMATCH"
    NODE_DATA_REGION_MISMATCH = "NODE_DATA_REGION_MISMATCH"
    NODE_OWNER_SCOPE_MISMATCH = "NODE_OWNER_SCOPE_MISMATCH"
    NODE_REMOTE_EXECUTION_DENIED = "NODE_REMOTE_EXECUTION_DENIED"


#: 调度结果中代表永久性配置缺口的原因；执行循环应立即失败而不是排队等待。
FATAL_SCHEDULING_REASONS = frozenset({
    "NO_ELIGIBLE_RESOURCE",
    "NO_MODEL_ENDPOINT",
})


class CandidateDecision(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    resource_id: str = Field(alias="resourceId")
    accepted: bool
    reasons: list[FilterReason] = Field(default_factory=list)
    reason_details: list[dict[str, str]] = Field(default_factory=list, alias="reasonDetails")
    score: float | None = None


class ReadyNodeSchedulingResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    status: str
    binding: ExecutionBinding | None = None
    lease: ResourceLease | None = None
    candidates: list[CandidateDecision] = Field(default_factory=list)
    reason: str | None = None


class RequirementReadiness(BaseModel):
    """Current eligibility evidence; no reservation or execution authorization."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)
    ready: bool
    reason: str | None = None
    candidates: list[CandidateDecision] = Field(default_factory=list)
    runtime_versions: dict[str, int] = Field(default_factory=dict, alias="runtimeVersions")
    node_versions: dict[str, int] = Field(default_factory=dict, alias="nodeVersions")
    model_endpoint_versions: dict[str, int] = Field(default_factory=dict, alias="modelEndpointVersions")
    available_runtime_ids: tuple[str, ...] = Field(default=(), alias="availableRuntimeIds")


class SchedulerUnavailable(RuntimeError):
    """Coordination state cannot safely allocate a lease."""


class SchedulerNoEligibleResource(RuntimeError):
    """The frozen binding policy has no executable resource in this Runtime."""

    def __init__(self, message: str, *, reason="NO_ELIGIBLE_RESOURCE", step_id=None, candidates=()):
        super().__init__(message)
        self.reason_code = reason
        self.step_id = step_id
        self.candidate_reasons = [
            {"resourceId": item.resource_id, "reasons": [r.value for r in item.reasons]}
            for item in candidates[:16]
        ]


class SchedulerAllocationTimeout(TimeoutError):
    """A READY node could not obtain capacity within its bounded queue window."""

    def __init__(self, message: str, *, step_id=None, candidates=()):
        super().__init__(message)
        self.reason_code = "SCHEDULER_CAPACITY_TIMEOUT"
        self.step_id = step_id
        self.candidate_reasons = [
            {"resourceId": item.resource_id, "reasons": [r.value for r in item.reasons]}
            for item in candidates[:16]
        ]


__all__ = [
    "FATAL_SCHEDULING_REASONS",
    "CandidateDecision",
    "FilterReason",
    "ReadyNodeSchedulingResult",
    "RequirementReadiness",
    "SchedulerAllocationTimeout",
    "SchedulerNoEligibleResource",
    "SchedulerUnavailable",
]
