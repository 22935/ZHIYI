"""Typed scheduler decisions without DAG state."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from contracts.resource import ExecutionBinding, ResourceLease


class FilterReason(str, Enum):
    DISABLED = "DISABLED"
    UNHEALTHY = "UNHEALTHY"
    CAPABILITY_MISMATCH = "CAPABILITY_MISMATCH"
    DOMAIN_MISMATCH = "DOMAIN_MISMATCH"
    RESOURCE_TYPE_MISMATCH = "RESOURCE_TYPE_MISMATCH"
    NOT_ALLOWED = "NOT_ALLOWED"
    EXCLUDED = "EXCLUDED"
    DATA_ZONE_MISMATCH = "DATA_ZONE_MISMATCH"
    OWNER_SCOPE_MISMATCH = "OWNER_SCOPE_MISMATCH"
    NO_CAPACITY = "NO_CAPACITY"
    COST_EXCEEDED = "COST_EXCEEDED"
    DEPLOYMENT_TIER_MISMATCH = "DEPLOYMENT_TIER_MISMATCH"
    REMOTE_EXECUTION_DISABLED = "REMOTE_EXECUTION_DISABLED"
    LATENCY_EXCEEDED = "LATENCY_EXCEEDED"
    PRIVACY_LEVEL_INSUFFICIENT = "PRIVACY_LEVEL_INSUFFICIENT"
    MODEL_MISMATCH = "MODEL_MISMATCH"
    GPU_MEMORY_INSUFFICIENT = "GPU_MEMORY_INSUFFICIENT"
    ENDPOINT_MISSING = "ENDPOINT_MISSING"


class CandidateDecision(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    resource_id: str = Field(alias="resourceId")
    accepted: bool
    reasons: list[FilterReason] = Field(default_factory=list)
    score: float | None = None


class ReadyNodeSchedulingResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    status: str
    binding: ExecutionBinding | None = None
    lease: ResourceLease | None = None
    candidates: list[CandidateDecision] = Field(default_factory=list)
    reason: str | None = None


class SchedulerUnavailable(RuntimeError):
    """Coordination state cannot safely allocate a lease."""


class SchedulerNoEligibleResource(RuntimeError):
    """The frozen binding policy has no executable resource in this Runtime."""


class SchedulerAllocationTimeout(TimeoutError):
    """A READY node could not obtain capacity within its bounded queue window."""


__all__ = [
    "CandidateDecision",
    "FilterReason",
    "ReadyNodeSchedulingResult",
    "SchedulerAllocationTimeout",
    "SchedulerNoEligibleResource",
    "SchedulerUnavailable",
]
