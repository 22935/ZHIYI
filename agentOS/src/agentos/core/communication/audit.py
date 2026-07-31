"""Run-scoped, tamper-evident communication provenance for ACG execution."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _checksum(payload: Any) -> str:
    try:
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        text = str(payload)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _AuditEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    event_id: str = Field(alias="eventId")
    run_id: str = Field(default="", alias="runId")
    task_id: str = Field(default="", alias="taskId")
    previous_hash: str = Field(default="", alias="previousHash")
    event_hash: str = Field(default="", alias="eventHash")
    created_at: datetime = Field(default_factory=_now, alias="createdAt")


class DataProductionEvent(_AuditEvent):
    producer_step_id: str = Field(alias="producerStepId")
    agent_name: str = Field(default="", alias="agentName")
    attempt: int = 1
    checksum: str = ""
    field_names: List[str] = Field(default_factory=list, alias="fieldNames")
    token_size: int = Field(default=0, alias="tokenSize")
    evidence_refs: List[str] = Field(default_factory=list, alias="evidenceRefs")


class DataConsumptionEvent(_AuditEvent):
    consumer_step_id: str = Field(alias="consumerStepId")
    consumer_agent_name: str = Field(default="", alias="consumerAgentName")
    attempt: int = 1
    producer_step_ids: List[str] = Field(default_factory=list, alias="producerStepIds")
    producer_event_ids: List[str] = Field(default_factory=list, alias="producerEventIds")
    fields_by_producer: Dict[str, List[str]] = Field(default_factory=dict, alias="fieldsByProducer")
    consumed_fields: List[str] = Field(default_factory=list, alias="consumedFields")
    tokens_delivered: int = Field(default=0, alias="tokensDelivered")
    tokens_available: int = Field(default=0, alias="tokensAvailable")
    saving_ratio: float = Field(default=0.0, alias="savingRatio")
    checksum: str = ""
    contract_status: str = Field(default="valid", alias="contractStatus")


class RuntimeInteraction(_AuditEvent):
    interaction_id: str = Field(alias="interactionId")
    edge_ids: List[str] = Field(default_factory=list, alias="edgeIds")
    producer_step_ids: List[str] = Field(default_factory=list, alias="producerStepIds")
    consumer_step_id: str = Field(alias="consumerStepId")
    producer_agent_names: List[str] = Field(default_factory=list, alias="producerAgentNames")
    consumer_agent_name: str = Field(default="", alias="consumerAgentName")
    fields_by_producer: Dict[str, List[str]] = Field(default_factory=dict, alias="fieldsByProducer")
    tokens_delivered: int = Field(default=0, alias="tokensDelivered")
    tokens_available: int = Field(default=0, alias="tokensAvailable")
    saving_ratio: float = Field(default=0.0, alias="savingRatio")
    evidence_refs: List[str] = Field(default_factory=list, alias="evidenceRefs")
    contract_status: str = Field(default="valid", alias="contractStatus")
    checksum: str = ""


class ProvenanceLedger:
    """Versioned provenance ledger isolated to one WorkflowRun."""

    schema_version = 2

    def __init__(self, *, run_id: str = "", task_id: str = "") -> None:
        self.run_id = run_id
        self.task_id = task_id
        self._seq = 0
        self._tail_hash = ""
        self._has_legacy_events = False
        self.productions: List[DataProductionEvent] = []
        self.consumptions: List[DataConsumptionEvent] = []
        self.interactions: List[RuntimeInteraction] = []

    @classmethod
    def from_graph(
        cls,
        graph: Optional[Dict[str, Any]],
        *,
        run_id: str = "",
        task_id: str = "",
    ) -> "ProvenanceLedger":
        ledger = cls(run_id=run_id, task_id=task_id)
        if not isinstance(graph, dict):
            return ledger
        for raw in graph.get("productions") or []:
            event = DataProductionEvent.model_validate(raw)
            ledger.productions.append(event)
            ledger._restore_event(event)
        for raw in graph.get("consumptions") or []:
            event = DataConsumptionEvent.model_validate(raw)
            ledger.consumptions.append(event)
            ledger._restore_event(event)
        for raw in graph.get("interactions") or []:
            event = RuntimeInteraction.model_validate(raw)
            ledger.interactions.append(event)
            ledger._restore_event(event)
        sealed_events: List[_AuditEvent] = [
            *ledger.productions,
            *ledger.consumptions,
            *ledger.interactions,
        ]
        sealed_events = [event for event in sealed_events if event.event_hash]
        if sealed_events:
            sealed_events.sort(key=lambda item: int(item.event_id.rsplit("_", 1)[-1]))
            ledger._tail_hash = sealed_events[-1].event_hash
        return ledger

    def _restore_event(self, event: _AuditEvent) -> None:
        try:
            self._seq = max(self._seq, int(event.event_id.rsplit("_", 1)[-1]))
        except (TypeError, ValueError):
            pass
        if event.event_hash:
            self._tail_hash = event.event_hash
        else:
            self._has_legacy_events = True

    def _next_id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}_{self._seq:06d}"

    def _seal(self, event: _AuditEvent) -> None:
        event.previous_hash = self._tail_hash
        payload = event.model_dump(by_alias=True, mode="json", exclude={"event_hash"})
        event.event_hash = _checksum(payload)
        self._tail_hash = event.event_hash

    def latest_production(self, step_id: str) -> Optional[DataProductionEvent]:
        for event in reversed(self.productions):
            if event.producer_step_id == step_id:
                return event
        return None

    def record_production(
        self,
        step_id: str,
        output: Dict[str, Any],
        token_size: int,
        *,
        agent_name: str = "",
        attempt: int = 1,
        evidence_refs: Optional[List[str]] = None,
    ) -> DataProductionEvent:
        event = DataProductionEvent(
            eventId=self._next_id("prod"),
            runId=self.run_id,
            taskId=self.task_id,
            producerStepId=step_id,
            agentName=agent_name,
            attempt=attempt,
            checksum=_checksum(output),
            fieldNames=sorted(output.keys()) if isinstance(output, dict) else [],
            tokenSize=token_size,
            evidenceRefs=list(evidence_refs or []),
        )
        self._seal(event)
        self.productions.append(event)
        return event

    def record_consumption(
        self,
        step_id: str,
        producer_step_ids: List[str],
        consumed_fields: List[str],
        *,
        consumer_agent_name: str = "",
        attempt: int = 1,
        fields_by_producer: Optional[Dict[str, List[str]]] = None,
        data: Optional[Dict[str, Any]] = None,
        tokens_delivered: int = 0,
        tokens_available: int = 0,
        saving_ratio: float = 0.0,
        contract_status: str = "valid",
    ) -> DataConsumptionEvent:
        producer_ids = list(dict.fromkeys(producer_step_ids))
        producer_events = [self.latest_production(item) for item in producer_ids]
        event = DataConsumptionEvent(
            eventId=self._next_id("cons"),
            runId=self.run_id,
            taskId=self.task_id,
            consumerStepId=step_id,
            consumerAgentName=consumer_agent_name,
            attempt=attempt,
            producerStepIds=producer_ids,
            producerEventIds=[item.event_id for item in producer_events if item is not None],
            fieldsByProducer=fields_by_producer or {},
            consumedFields=sorted(set(consumed_fields)),
            tokensDelivered=tokens_delivered,
            tokensAvailable=tokens_available,
            savingRatio=saving_ratio,
            checksum=_checksum(data or {}),
            contractStatus=contract_status,
        )
        self._seal(event)
        self.consumptions.append(event)
        return event

    def record_interaction(
        self,
        *,
        edge_ids: List[str],
        producer_step_ids: List[str],
        consumer_step_id: str,
        producer_agent_names: List[str],
        consumer_agent_name: str,
        fields_by_producer: Dict[str, List[str]],
        tokens_delivered: int,
        tokens_available: int,
        saving_ratio: float,
        evidence_refs: List[str],
        contract_status: str,
        data: Dict[str, Any],
    ) -> RuntimeInteraction:
        event_id = self._next_id("int")
        event = RuntimeInteraction(
            eventId=event_id,
            interactionId=event_id,
            runId=self.run_id,
            taskId=self.task_id,
            edgeIds=edge_ids,
            producerStepIds=list(dict.fromkeys(producer_step_ids)),
            consumerStepId=consumer_step_id,
            producerAgentNames=list(dict.fromkeys(name for name in producer_agent_names if name)),
            consumerAgentName=consumer_agent_name,
            fieldsByProducer=fields_by_producer,
            tokensDelivered=tokens_delivered,
            tokensAvailable=tokens_available,
            savingRatio=saving_ratio,
            evidenceRefs=evidence_refs,
            contractStatus=contract_status,
            checksum=_checksum(data),
        )
        self._seal(event)
        self.interactions.append(event)
        return event

    def trace_backward(self, step_id: str) -> List[str]:
        seen: set[str] = set()
        frontier = [step_id]
        while frontier:
            current = frontier.pop()
            for event in self.consumptions:
                if event.consumer_step_id != current:
                    continue
                for producer in event.producer_step_ids:
                    if producer not in seen:
                        seen.add(producer)
                        frontier.append(producer)
        return sorted(seen)

    def trace_forward(self, step_id: str) -> List[str]:
        return sorted(
            {event.consumer_step_id for event in self.consumptions if step_id in event.producer_step_ids}
        )

    def verify_integrity(self) -> bool:
        if self._has_legacy_events:
            return False
        previous = ""
        events: List[_AuditEvent] = [*self.productions, *self.consumptions, *self.interactions]
        events.sort(key=lambda item: int(item.event_id.rsplit("_", 1)[-1]))
        for event in events:
            if event.previous_hash != previous:
                return False
            expected = _checksum(event.model_dump(by_alias=True, mode="json", exclude={"event_hash"}))
            if event.event_hash != expected:
                return False
            previous = event.event_hash
        return True

    def to_graph(self) -> Dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "productions": [event.model_dump(by_alias=True, mode="json") for event in self.productions],
            "consumptions": [event.model_dump(by_alias=True, mode="json") for event in self.consumptions],
            "interactions": [event.model_dump(by_alias=True, mode="json") for event in self.interactions],
            "integrityStatus": "valid" if self.verify_integrity() else "legacy_or_invalid",
        }


__all__ = [
    "DataProductionEvent",
    "DataConsumptionEvent",
    "RuntimeInteraction",
    "ProvenanceLedger",
]
