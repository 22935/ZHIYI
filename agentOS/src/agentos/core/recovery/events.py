"""Stable runtime event models and pure outcome classification."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

from agentos.core.execution.package import StepExecutionOutcome
from agentos.core.models.types import TraceEventType
from agentos.core.recovery.constants import MAX_SAME_BINDING_RETRIES
from agentos.core.runtime_graph import RuntimeEvent, RuntimeEventStatus, RuntimeEventType
if TYPE_CHECKING:
    from agentos.core.runtime_graph import RuntimeGraph, RuntimeNode


def stable_hash(*parts: Any, prefix: str = "") -> str:
    encoded = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"{prefix}{digest}"


class RuntimeEventClassifier:
    """Purely classify outcomes and structured runtimeSignals; never mutate graph state."""

    classification_version = "1"
    max_same_binding_transient_retries = MAX_SAME_BINDING_RETRIES
    _IMMEDIATE_BINDING_ERRORS = {
        "AGENTNOTFOUND",
        "AGENT_NOT_FOUND",
        "AGENT_DISABLED",
        "BINDING_NOT_REGISTERED",
        "MODEL_ENDPOINT_REMOVED",
    }
    _TRANSIENT_BINDING_ERRORS = {
        "TIMEOUTERROR",
        "MODEL_TIMEOUT",
        "TRANSPORT_ERROR",
        "CONNECTIONERROR",
        "RATE_LIMIT",
        "REMOTE_ENDPOINT_UNAVAILABLE",
    }

    def classify(
        self,
        outcome: StepExecutionOutcome,
        runtime_node: RuntimeNode,
        runtime_graph: RuntimeGraph,
    ) -> list[RuntimeEvent]:
        raw_signals = outcome.runtime_signals
        events: list[RuntimeEvent] = []
        for signal in raw_signals:
            event_type = self._event_type(signal.get("type"))
            if event_type is None:
                continue
            events.append(self._build(outcome, runtime_node, runtime_graph, event_type, signal))

        error_category = str(outcome.error_code or outcome.error_type).strip().upper()
        binding_id = runtime_node.attempts[-1].binding_id if runtime_node.attempts else ""
        same_binding_failures = sum(
            1
            for attempt in runtime_node.attempts
            if attempt.binding_id == binding_id and attempt.error
        )
        if outcome.error and (
            error_category in self._IMMEDIATE_BINDING_ERRORS
            or outcome.error_type.strip().upper() in self._IMMEDIATE_BINDING_ERRORS
            or (
                error_category in self._TRANSIENT_BINDING_ERRORS
                or outcome.error_type.strip().upper() in self._TRANSIENT_BINDING_ERRORS
            )
            and same_binding_failures > self.max_same_binding_transient_retries
        ):
            excluded = list(
                dict.fromkeys(
                    attempt.binding_id
                    for attempt in runtime_node.attempts
                    if attempt.error and attempt.binding_id
                )
            )
            events.append(
                self._build(
                    outcome,
                    runtime_node,
                    runtime_graph,
                    RuntimeEventType.BINDING_UNAVAILABLE,
                    {
                        "reasonCode": (
                            "BINDING_RETRY_EXHAUSTED"
                            if same_binding_failures > self.max_same_binding_transient_retries
                            else "BINDING_UNAVAILABLE"
                        ),
                        "targetNodeId": runtime_node.node_id,
                        "failedBindingId": binding_id,
                        "agentName": runtime_node.attempts[-1].agent_name,
                        "modelName": runtime_node.attempts[-1].model_name,
                        "capability": runtime_node.spec.get("capability") or "",
                        "failureCategory": error_category,
                        "attemptNumber": runtime_node.attempts[-1].attempt_number,
                        "sameBindingRetryCount": same_binding_failures,
                        "excludedBindingIds": excluded,
                        "safeError": str(outcome.error)[:240],
                    },
                )
            )
        elif outcome.error_type == "ContextContractError":
            event_type = (
                RuntimeEventType.INPUT_CONTRACT_VIOLATION
                if outcome.error_direction == "input"
                else RuntimeEventType.OUTPUT_CONTRACT_VIOLATION
            )
            events.append(
                self._build(
                    outcome,
                    runtime_node,
                    runtime_graph,
                    event_type,
                    {
                        "reasonCode": outcome.error_code or event_type.value,
                        "targetNodeId": runtime_node.node_id,
                        "details": {"error": outcome.error or "contract violation"},
                    },
                )
            )
        elif outcome.error and not raw_signals:
            events.append(
                self._build(
                    outcome,
                    runtime_node,
                    runtime_graph,
                    RuntimeEventType.STEP_EXECUTION_FAILED,
                    {
                        "reasonCode": outcome.error_code or "STEP_EXECUTION_FAILED",
                        "targetNodeId": runtime_node.node_id,
                        "details": {"error": outcome.error},
                    },
                )
            )

        unique: dict[str, RuntimeEvent] = {event.event_id: event for event in events}
        return list(unique.values())

    def _build(self, outcome, node, graph, event_type, signal) -> RuntimeEvent:
        reason_code = str(signal.get("reasonCode") or signal.get("code") or event_type.value).strip().upper()
        target_node_id = str(signal.get("targetNodeId") or node.node_id)
        key = stable_hash(
            outcome.run_id,
            node.node_id,
            outcome.attempt_id,
            event_type.value,
            reason_code,
            target_node_id,
        )
        payload = {
            "reasonCode": reason_code,
            "targetNodeId": target_node_id,
            "details": json.loads(
                json.dumps(
                    dict(signal.get("details") or {}),
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
            ),
        }
        for field in (
            "failedBindingId",
            "agentName",
            "modelName",
            "capability",
            "failureCategory",
            "attemptNumber",
            "sameBindingRetryCount",
            "excludedBindingIds",
            "safeError",
        ):
            if field in signal:
                payload[field] = signal[field]
        source_trace = next(
            (
                str(item.get("eventId"))
                for item in outcome.trace_events
                if item.get("eventType") == TraceEventType.CONTRACT_VIOLATION and item.get("eventId")
            ),
            None,
        )
        return RuntimeEvent(
            eventId=f"event_{key[:24]}",
            idempotencyKey=key,
            runId=outcome.run_id,
            graphId=graph.graph_id,
            graphVersion=graph.graph_version,
            eventType=event_type,
            runtimeNodeId=node.node_id,
            attemptId=outcome.attempt_id,
            bindingId=(node.attempts[-1].binding_id if node.attempts else ""),
            sourceTraceEventId=source_trace,
            payload=payload,
            classificationVersion=self.classification_version,
            createdAt=outcome.ended_at,
        )

    @staticmethod
    def _event_type(value: Any) -> RuntimeEventType | None:
        try:
            return RuntimeEventType(str(value or "").strip().upper())
        except ValueError:
            return None


__all__ = [
    "RuntimeEvent",
    "RuntimeEventClassifier",
    "RuntimeEventStatus",
    "RuntimeEventType",
    "stable_hash",
]
