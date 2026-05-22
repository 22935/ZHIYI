"""AgentOS Core 的 types 模块，提供运行时控制、状态、Trace、审核或治理能力。"""


from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class CoreModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    RUNNING = "running"
    WAITING_REVIEW = "waiting_review"
    RETRYING = "retrying"
    FAILED = "failed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_REVIEW = "waiting_review"
    RETRYING = "retrying"
    FAILED = "failed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TraceEventType(str, Enum):
    TASK_CREATED = "task_created"
    RUN_STARTED = "run_started"
    STEP_STARTED = "step_started"
    AGENT_CALLED = "agent_called"
    TOOL_CALLED = "tool_called"
    CHECKPOINT_CREATED = "checkpoint_created"
    REVIEW_REQUIRED = "review_required"
    REVIEW_DECIDED = "review_decided"
    STEP_FAILED = "step_failed"
    RUN_FAILED = "run_failed"
    RUN_RECOVERED = "run_recovered"
    RUN_COMPLETED = "run_completed"
    RUN_CANCELLED = "run_cancelled"


class ReviewDecisionType(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEED_MORE_INFO = "need_more_info"
    RERUN = "rerun"
    CANCELLED = "cancelled"


class AgentTask(CoreModel):
    task_id: str = Field(default_factory=lambda: new_id("task"), alias="taskId")
    title: str
    domain: str = "general"
    intent: str = "general"
    input: Dict[str, Any] = Field(default_factory=dict)
    security_level: str = Field(default="internal", alias="securityLevel")
    priority: str = "normal"
    status: WorkflowStatus = WorkflowStatus.PENDING
    recommended_workflow: Optional[str] = Field(default=None, alias="recommendedWorkflow")
    created_at: datetime = Field(default_factory=utc_now, alias="createdAt")
    updated_at: datetime = Field(default_factory=utc_now, alias="updatedAt")


class WorkflowStepDefinition(CoreModel):
    step_id: str = Field(alias="stepId")
    name: str
    agent_name: str = Field(alias="agentName")
    capability: Optional[str] = None
    input: Dict[str, Any] = Field(default_factory=dict)
    review_required: bool = Field(default=False, alias="reviewRequired")
    next_step_id: Optional[str] = Field(default=None, alias="nextStepId")
    max_retries: int = Field(default=0, alias="maxRetries")


class WorkflowDefinition(CoreModel):
    workflow_id: str = Field(alias="workflowId")
    name: str
    domain: str
    intent: str = "general"
    version: str = "1.0.0"
    description: str = ""
    steps: List[WorkflowStepDefinition] = Field(default_factory=list)

    def first_step_id(self) -> Optional[str]:
        return self.steps[0].step_id if self.steps else None

    def get_step_definition(self, step_id: str) -> WorkflowStepDefinition:
        for step in self.steps:
            if step.step_id == step_id:
                return step
        raise KeyError(f"workflow step not found: {step_id}")

    def next_step_id(self, step_id: str) -> Optional[str]:
        definition = self.get_step_definition(step_id)
        if definition.next_step_id in ("", "done", "completed", None):
            if definition.next_step_id in ("done", "completed"):
                return None
        if definition.next_step_id:
            return definition.next_step_id

        for index, step in enumerate(self.steps):
            if step.step_id == step_id:
                next_index = index + 1
                return self.steps[next_index].step_id if next_index < len(self.steps) else None
        return None


class WorkflowStep(CoreModel):
    step_id: str = Field(alias="stepId")
    name: str
    agent_name: str = Field(alias="agentName")
    capability: Optional[str] = None
    status: StepStatus = StepStatus.PENDING
    input: Dict[str, Any] = Field(default_factory=dict)
    output: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    retry_count: int = Field(default=0, alias="retryCount")
    max_retries: int = Field(default=0, alias="maxRetries")
    requires_review: bool = Field(default=False, alias="reviewRequired")
    started_at: Optional[datetime] = Field(default=None, alias="startedAt")
    completed_at: Optional[datetime] = Field(default=None, alias="completedAt")

    @classmethod
    def from_definition(cls, definition: WorkflowStepDefinition) -> "WorkflowStep":
        return cls(
            stepId=definition.step_id,
            name=definition.name,
            agentName=definition.agent_name,
            capability=definition.capability,
            input=dict(definition.input),
            reviewRequired=definition.review_required,
            maxRetries=definition.max_retries,
        )


class TraceEvent(CoreModel):
    event_id: str = Field(default_factory=lambda: new_id("trace"), alias="eventId")
    run_id: str = Field(alias="runId")
    step_id: Optional[str] = Field(default=None, alias="stepId")
    agent_name: Optional[str] = Field(default=None, alias="agentName")
    event_type: TraceEventType = Field(alias="eventType")
    observation: str = ""
    payload: Dict[str, Any] = Field(default_factory=dict)
    duration_ms: int = Field(default=0, alias="durationMs")
    created_at: datetime = Field(default_factory=utc_now, alias="createdAt")


class Checkpoint(CoreModel):
    checkpoint_id: str = Field(default_factory=lambda: new_id("ckpt"), alias="checkpointId")
    run_id: str = Field(alias="runId")
    step_id: str = Field(alias="stepId")
    state_snapshot: Dict[str, Any] = Field(default_factory=dict, alias="stateSnapshot")
    output_snapshot: Dict[str, Any] = Field(default_factory=dict, alias="outputSnapshot")
    can_resume: bool = Field(default=True, alias="canResume")
    created_at: datetime = Field(default_factory=utc_now, alias="createdAt")


class WorkflowRun(CoreModel):
    run_id: str = Field(default_factory=lambda: new_id("run"), alias="runId")
    task_id: str = Field(alias="taskId")
    workflow_id: str = Field(alias="workflowId")
    domain: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    current_step_id: Optional[str] = Field(default=None, alias="currentStepId")
    review_mode: str = Field(default="auto", alias="reviewMode")
    input: Dict[str, Any] = Field(default_factory=dict)
    output: Dict[str, Any] = Field(default_factory=dict)
    steps: List[WorkflowStep] = Field(default_factory=list)
    checkpoints: List[Checkpoint] = Field(default_factory=list)
    trace: List[TraceEvent] = Field(default_factory=list)
    error: Optional[str] = None
    recovery_count: int = Field(default=0, alias="recoveryCount")
    created_at: datetime = Field(default_factory=utc_now, alias="createdAt")
    updated_at: datetime = Field(default_factory=utc_now, alias="updatedAt")

    def get_step(self, step_id: str) -> WorkflowStep:
        for step in self.steps:
            if step.step_id == step_id:
                return step
        raise KeyError(f"workflow run step not found: {step_id}")


class ReviewDecision(CoreModel):
    run_id: str = Field(alias="runId")
    step_id: str = Field(alias="stepId")
    decision: ReviewDecisionType
    reviewer: str = "system"
    comment: str = ""
    created_at: datetime = Field(default_factory=utc_now, alias="createdAt")


class ReviewRecord(CoreModel):
    review_id: str = Field(default_factory=lambda: new_id("review"), alias="reviewId")
    run_id: str = Field(alias="runId")
    step_id: str = Field(alias="stepId")
    decision: ReviewDecisionType
    reviewer: str = "system"
    comment: str = ""
    trace_event_id: Optional[str] = Field(default=None, alias="traceEventId")
    created_at: datetime = Field(default_factory=utc_now, alias="createdAt")


class WorkflowMetric(CoreModel):
    total_runs: int = Field(default=0, alias="totalRuns")
    completed_runs: int = Field(default=0, alias="completedRuns")
    failed_runs: int = Field(default=0, alias="failedRuns")
    cancelled_runs: int = Field(default=0, alias="cancelledRuns")
    waiting_review_runs: int = Field(default=0, alias="waitingReviewRuns")
    retrying_runs: int = Field(default=0, alias="retryingRuns")
    completion_rate: float = Field(default=0.0, alias="completionRate")
    failure_rate: float = Field(default=0.0, alias="failureRate")
    recovery_success_rate: float = Field(default=0.0, alias="recoverySuccessRate")
    average_recovery_count: float = Field(default=0.0, alias="averageRecoveryCount")
    average_trace_events: float = Field(default=0.0, alias="averageTraceEvents")
    review_count: int = Field(default=0, alias="reviewCount")
    status_breakdown: Dict[str, int] = Field(default_factory=dict, alias="statusBreakdown")


class EvaluationRun(CoreModel):
    evaluation_id: str = Field(default_factory=lambda: new_id("eval"), alias="evaluationId")
    domain: Optional[str] = None
    workflow_id: Optional[str] = Field(default=None, alias="workflowId")
    source: Optional[str] = None
    metrics: WorkflowMetric
    created_at: datetime = Field(default_factory=utc_now, alias="createdAt")


class SkillRequest(CoreModel):
    session_id: str = Field(alias="sessionId")
    text: str
    action_input: Dict[str, Any] = Field(default_factory=dict, alias="actionInput")
    memory: Dict[str, Any] = Field(default_factory=dict)


class SkillResult(CoreModel):
    skill_name: str = Field(alias="skillName")
    success: bool = True
    output: Dict[str, Any] = Field(default_factory=dict)
    message: str = ""
