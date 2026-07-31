"""Immutable data transfer objects for snapshot execution and barrier commits."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agentos.core.models.enums import StepStatus


class StepExecutionPackage(BaseModel):
    """Frozen inputs captured while scheduling a single RuntimeNode attempt."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    run_id: str = Field(alias="runId")
    task_id: str = Field(alias="taskId")
    graph_id: str = Field(alias="graphId")
    graph_version: int = Field(alias="graphVersion")
    runtime_node_id: str = Field(alias="runtimeNodeId")
    attempt_id: str = Field(alias="attemptId")
    attempt_number: int = Field(alias="attemptNumber")
    binding: dict[str, Any]
    node_spec: dict[str, Any] = Field(alias="nodeSpec")
    run_input: dict[str, Any] = Field(alias="runInput")
    upstream_outputs: dict[str, dict[str, Any]] = Field(alias="upstreamOutputs")
    context_metadata: dict[str, Any] = Field(default_factory=dict, alias="contextMetadata")
    timeout: int = 0
    run_snapshot: dict[str, Any] = Field(alias="runSnapshot")


class StepExecutionOutcome(BaseModel):
    """Detached result merged into the latest run only at the batch barrier."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    run_id: str = Field(alias="runId")
    graph_id: str = Field(alias="graphId")
    scheduled_graph_version: int = Field(alias="scheduledGraphVersion")
    runtime_node_id: str = Field(alias="runtimeNodeId")
    attempt_id: str = Field(alias="attemptId")
    status: StepStatus
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    resolved_input: dict[str, Any] = Field(default_factory=dict, alias="resolvedInput")
    started_at: datetime = Field(alias="startedAt")
    ended_at: datetime = Field(alias="endedAt")
    trace_events: list[dict[str, Any]] = Field(default_factory=list, alias="traceEvents")
    provenance_events: dict[str, Any] = Field(default_factory=dict, alias="provenanceEvents")
    review_required: bool = Field(default=False, alias="reviewRequired")
    recoverable: bool = False
    runtime_signals: list[dict[str, Any]] = Field(default_factory=list, alias="runtimeSignals")
    error_type: str = Field(default="", alias="errorType")
    error_code: str = Field(default="", alias="errorCode")
    error_direction: str = Field(default="", alias="errorDirection")


__all__ = ["StepExecutionOutcome", "StepExecutionPackage"]
