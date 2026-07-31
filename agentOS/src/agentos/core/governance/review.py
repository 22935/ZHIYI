"""AgentOS Core 的 review 模块，提供运行时控制、状态、Trace、审核或治理能力。"""


from typing import List

from agentos.core.models.types import ReviewDecision, ReviewDecisionType, ReviewRecord, TraceEventType, WorkflowRun
from agentos.core.governance.trace import TraceStore


class ReviewManager:
    """把人工审核决策记录为可审计的 Trace 事件。"""

    def __init__(self, trace_store: TraceStore):
        self.trace_store = trace_store

    def record(self, run: WorkflowRun, decision: ReviewDecision) -> ReviewRecord:
        event = self.trace_store.append(
            run=run,
            event_type=TraceEventType.REVIEW_DECIDED,
            step_id=decision.step_id,
            observation=f"Review decision: {decision.decision.value}",
            payload=decision.model_dump(by_alias=True, mode="json"),
        )
        return ReviewRecord(
            runId=run.run_id,
            stepId=decision.step_id,
            decision=decision.decision,
            reviewer=decision.reviewer,
            comment=decision.comment,
            operationId=decision.operation_id,
            traceEventId=event.event_id,
            createdAt=event.created_at,
        )

    def list(self, run: WorkflowRun) -> List[ReviewRecord]:
        records: List[ReviewRecord] = []
        for event in sorted(run.trace, key=lambda item: (item.created_at, item.event_id)):
            if event.event_type != TraceEventType.REVIEW_DECIDED:
                continue
            payload = event.payload or {}
            records.append(
                ReviewRecord(
                    reviewId=payload.get("reviewId") or f"review_{event.event_id}",
                    runId=payload.get("runId") or run.run_id,
                    stepId=payload.get("stepId") or event.step_id or "",
                    decision=ReviewDecisionType(payload.get("decision", ReviewDecisionType.APPROVED.value)),
                    reviewer=payload.get("reviewer") or "system",
                    comment=payload.get("comment") or "",
                    operationId=payload.get("operationId"),
                    traceEventId=event.event_id,
                    createdAt=payload.get("createdAt") or event.created_at,
                )
            )
        return records
