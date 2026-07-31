from agentos.core.acg import ACGBlueprint, StepNode
from agentos.core.execution.package import StepExecutionOutcome
from agentos.core.models.types import StepStatus, utc_now
from agentos.core.recovery import RuntimeEventClassifier, RuntimeEventStatus, RuntimeEventType
from agentos.core.runtime_graph import RuntimeGraph


def _graph() -> RuntimeGraph:
    return RuntimeGraph.from_blueprint(
        run_id="run_1",
        blueprint=ACGBlueprint(
            graphId="graph_1",
            nodes=[StepNode(nodeId="target", agentName="worker", capability="work")],
        ),
    )


def _outcome(**updates) -> StepExecutionOutcome:
    values = {
        "runId": "run_1",
        "graphId": "graph_1",
        "scheduledGraphVersion": 1,
        "runtimeNodeId": "target",
        "attemptId": "attempt_1",
        "status": StepStatus.COMPLETED,
        "startedAt": utc_now(),
        "endedAt": utc_now(),
    }
    values.update(updates)
    return StepExecutionOutcome.model_validate(values)


def test_structured_signal_produces_stable_deduplicated_runtime_event():
    classifier = RuntimeEventClassifier()
    graph = _graph()
    signal = {
        "type": "EVIDENCE_MISSING",
        "code": "SOURCE_GAP",
        "targetNodeId": "target",
        "details": {"requiredEvidenceTypes": ["primary_source"]},
    }
    outcome = _outcome(runtimeSignals=[signal, signal])

    first = classifier.classify(outcome, graph.get_node("target"), graph)
    second = classifier.classify(outcome, graph.get_node("target"), graph)

    assert len(first) == 1
    assert first[0].event_type == RuntimeEventType.EVIDENCE_MISSING
    assert first[0].event_id == second[0].event_id
    assert first[0].idempotency_key == second[0].idempotency_key
    assert first[0].reason_code == "SOURCE_GAP"
    assert first[0].status == RuntimeEventStatus.PENDING


def test_success_without_signal_produces_no_event():
    graph = _graph()
    events = RuntimeEventClassifier().classify(
        _outcome(output={"accepted": True}), graph.get_node("target"), graph
    )
    assert events == []


def test_contract_error_maps_direction_and_event_survives_graph_roundtrip():
    graph = _graph()
    outcome = _outcome(
        status=StepStatus.FAILED,
        error="missing field",
        errorType="ContextContractError",
        errorCode="MISSING_FIELD",
        errorDirection="input",
    )
    event = RuntimeEventClassifier().classify(outcome, graph.get_node("target"), graph)[0]
    graph.runtime_events.append(event)
    graph.pending_runtime_event_ids.append(event.event_id)
    reloaded = RuntimeGraph.model_validate(graph.model_dump(by_alias=True, mode="json"))

    assert event.event_type == RuntimeEventType.INPUT_CONTRACT_VIOLATION
    assert reloaded.runtime_events[0].event_id == event.event_id
    assert reloaded.pending_runtime_event_ids == [event.event_id]
