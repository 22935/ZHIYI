"""Shared lifecycle enums for AgentOS core models and projections."""

from enum import Enum


class WorkflowProgressPhase(str, Enum):
    """Persisted and projected phases of a workflow run lifecycle."""

    UNDERSTANDING = "understanding"
    PLANNING = "planning"
    GRAPH_BUILDING = "graph_building"
    EXECUTING = "executing"
    RECOVERY = "recovery"
    REVIEW = "review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    """Shared persisted lifecycle for WorkflowStep projections and RuntimeNodes."""

    PENDING = "pending"
    RUNNING = "running"
    WAITING_REVIEW = "waiting_review"
    RETRYING = "retrying"
    FAILED = "failed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    SKIPPED_BY_CONDITION = "skipped_by_condition"


__all__ = ["StepStatus", "WorkflowProgressPhase"]
