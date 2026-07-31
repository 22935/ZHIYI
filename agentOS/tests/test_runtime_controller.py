import asyncio

import pytest

from agentos.agents import AgentOutput, AgentProfile, AgentRegistry, BaseAgent
from agentos.core.acg import ACGBlueprint, ACGEdge, StepNode
from agentos.core.governance.checkpoint import CheckpointStore
from agentos.core.governance.trace import TraceStore
from agentos.core.models.types import AgentTask, StepStatus, WorkflowRun, WorkflowStep
from agentos.core.recovery import (
    PatchConflictError,
    RuntimeController,
    RuntimeGraphPatch,
)
from agentos.core.run_locks import RunLockManager
from agentos.stores.memory_workflow_store import MemoryWorkflowStore
from agentos.stores.sqlite_workflow_store import SQLiteWorkflowStore


class _Agent(BaseAgent):
    def __init__(self):
        super().__init__(
            AgentProfile(
                agentName="worker",
                domain="test",
                capabilities=["work", "remedy"],
                allowedSkills=["search"],
            )
        )

    async def run(self, context):
        return AgentOutput(output={})


class _CountingStore(MemoryWorkflowStore):
    def __init__(self):
        super().__init__()
        self.save_calls = 0
        self.fail_saves = False

    def save_run(self, run):
        self.save_calls += 1
        if self.fail_saves:
            raise RuntimeError("injected save failure")
        super().save_run(run)


def _registry() -> AgentRegistry:
    registry = AgentRegistry()
    registry.register(_Agent())
    return registry


def _blueprint() -> ACGBlueprint:
    return ACGBlueprint(
        graphId="graph_1",
        taskId="task_1",
        version=9,
        nodes=[
            StepNode(
                nodeId="prepare", name="Prepare", agentName="worker", capability="work"
            ),
            StepNode(
                nodeId="target", name="Target", agentName="worker", capability="work"
            ),
        ],
        edges=[ACGEdge(edgeId="prepare_target", sourceId="prepare", targetId="target")],
    )


def _run() -> WorkflowRun:
    blueprint = _blueprint()
    return WorkflowRun(
        runId="run_1",
        taskId="task_1",
        workflowId="workflow_1",
        domain="test",
        runtimeEngine="acg",
        acgBlueprint=blueprint.model_dump(by_alias=True, mode="json"),
        steps=[
            WorkflowStep(
                stepId="prepare", name="Prepare", agentName="worker", capability="work"
            ),
            WorkflowStep(
                stepId="target", name="Target", agentName="worker", capability="work"
            ),
        ],
    )


def _patch(
    *,
    patch_id="patch_1",
    idempotency_key="idem_1",
    event_id="event_1",
    proposal_id="proposal_1",
    node_id="remedy",
    reason="repair",
) -> RuntimeGraphPatch:
    return RuntimeGraphPatch(
        patchId=patch_id,
        idempotencyKey=idempotency_key,
        runId="run_1",
        graphId="graph_1",
        baseGraphVersion=1,
        operationType="ADD_SUBGRAPH",
        sourceEventId=event_id,
        proposalId=proposal_id,
        reason=reason,
        expectedNodeStates={"target": "pending"},
        budgetImpact={"addedNodes": 1, "replanDepthIncrement": 1},
        targetNodeId="target",
        replacedIncomingEdgeIds=["prepare_target"],
        addNodes=[StepNode(nodeId=node_id, agentName="worker", capability="remedy")],
        addEdges=[
            ACGEdge(edgeId=f"prepare_{node_id}", sourceId="prepare", targetId=node_id),
            ACGEdge(edgeId=f"{node_id}_target", sourceId=node_id, targetId="target"),
        ],
    )


def _controller(store) -> RuntimeController:
    return RuntimeController(
        workflow_store=store,
        agent_registry=_registry(),
        checkpoint_store=CheckpointStore(),
        trace_store=TraceStore(),
        lock_manager=RunLockManager(),
    )


async def _initialized(store):
    run = _run()
    store.save_task(AgentTask(taskId=run.task_id, title="Runtime controller"))
    store.save_run(run)
    controller = _controller(store)
    graph = await controller.initialize_from_blueprint(run.run_id, _blueprint())
    return controller, graph


@pytest.mark.parametrize("store_kind", ["memory", "sqlite"])
async def test_legacy_run_initialization_is_idempotent_for_both_stores(
    tmp_path, store_kind
):
    store = (
        MemoryWorkflowStore()
        if store_kind == "memory"
        else SQLiteWorkflowStore(tmp_path / "workflow.db")
    )
    run = _run()
    store.save_task(AgentTask(taskId=run.task_id, title="Legacy runtime"))
    store.save_run(run)
    controller = _controller(store)

    first = await controller.load(run.run_id)
    second = await controller.load(run.run_id)

    assert first.model_dump(by_alias=True, mode="json") == second.model_dump(
        by_alias=True, mode="json"
    )
    assert first.source_blueprint_version == 9
    assert first.graph_version == 1


@pytest.mark.parametrize("store_kind", ["memory", "sqlite"])
async def test_patch_and_replay_semantics_match_for_both_stores(tmp_path, store_kind):
    store = (
        MemoryWorkflowStore()
        if store_kind == "memory"
        else SQLiteWorkflowStore(tmp_path / "patch-roundtrip.db")
    )
    controller, _ = await _initialized(store)
    patch = _patch()

    applied = await controller.apply_patch("run_1", patch)
    replayed = await controller.apply_patch("run_1", patch)
    persisted = store.get_run("run_1")

    assert applied.applied is True
    assert replayed.idempotent_replay is True
    assert persisted.runtime_graph.graph_version == 2
    assert persisted.runtime_graph.applied_patch_ids == ["patch_1"]
    assert persisted.checkpoints[-1].state_snapshot["runtimeGraph"]["graphVersion"] == 2


async def test_apply_patch_advances_version_and_saves_patch_checkpoint_atomically():
    store = _CountingStore()
    controller, _ = await _initialized(store)
    store.save_calls = 0

    result = await controller.apply_patch("run_1", _patch())
    persisted = store.get_run("run_1")

    assert result.applied is True
    assert result.graph_version == 2
    assert store.save_calls == 1
    assert persisted.runtime_graph.graph_version == 2
    assert persisted.runtime_graph.applied_patch_ids == ["patch_1"]
    assert persisted.checkpoints[-1].state_snapshot["graphVersion"] == 2
    assert persisted.checkpoints[-1].state_snapshot["appliedPatchIds"] == ["patch_1"]
    assert persisted.checkpoints[-1].state_snapshot["runtimeGraph"]["graphVersion"] == 2


async def test_stale_patch_is_rejected():
    store = MemoryWorkflowStore()
    controller, _ = await _initialized(store)
    await controller.apply_patch("run_1", _patch())

    with pytest.raises(PatchConflictError) as caught:
        await controller.apply_patch(
            "run_1",
            _patch(
                patch_id="patch_2",
                idempotency_key="idem_2",
                event_id="event_2",
                proposal_id="proposal_2",
                node_id="remedy_2",
            ),
        )
    assert caught.value.code == "GRAPH_VERSION_CONFLICT"


async def test_controller_ignores_workflow_step_projection_when_validating_patch():
    store = MemoryWorkflowStore()
    controller, _ = await _initialized(store)
    persisted = store.get_run("run_1")
    persisted.get_step("target").status = StepStatus.COMPLETED
    assert persisted.runtime_graph.get_node("target").status.value == "pending"
    store.save_run(persisted)

    result = await controller.apply_patch("run_1", _patch())
    assert result.applied is True
    assert result.runtime_graph.get_node("target").status == StepStatus.PENDING


async def test_same_patch_id_and_content_is_an_idempotent_replay():
    store = MemoryWorkflowStore()
    controller, _ = await _initialized(store)
    patch = _patch()
    first = await controller.apply_patch("run_1", patch)
    second = await controller.apply_patch("run_1", patch)

    assert first.applied is True
    assert second.applied is False
    assert second.idempotent_replay is True
    assert second.graph_version == 2
    assert len(store.get_run("run_1").runtime_graph.nodes) == 3


async def test_same_patch_id_with_different_content_conflicts():
    store = MemoryWorkflowStore()
    controller, _ = await _initialized(store)
    await controller.apply_patch("run_1", _patch())

    conflicting = _patch(reason="different content")
    with pytest.raises(PatchConflictError) as caught:
        await controller.apply_patch("run_1", conflicting)
    assert caught.value.code == "PATCH_ID_CONTENT_CONFLICT"


async def test_same_idempotency_key_and_semantics_does_not_expand_twice():
    store = MemoryWorkflowStore()
    controller, _ = await _initialized(store)
    first_patch = _patch()
    await controller.apply_patch("run_1", first_patch)
    replay = first_patch.model_copy(
        deep=True,
        update={
            "patch_id": "patch_alias",
            "source_event_id": "event_alias",
            "proposal_id": "proposal_alias",
        },
    )

    result = await controller.apply_patch("run_1", replay)

    assert result.applied is False
    assert result.idempotent_replay is True
    assert result.patch_id == "patch_1"
    assert len(store.get_run("run_1").runtime_graph.nodes) == 3


async def test_save_failure_does_not_pollute_persisted_or_caller_owned_run():
    store = _CountingStore()
    controller, _ = await _initialized(store)
    caller_run = store.get_run("run_1")
    caller_before = caller_run.model_dump(by_alias=True, mode="json")
    store.fail_saves = True

    with pytest.raises(RuntimeError, match="injected save failure"):
        await controller.apply_patch("run_1", _patch())

    store.fail_saves = False
    persisted = store.get_run("run_1")
    assert persisted.runtime_graph.graph_version == 1
    assert persisted.runtime_graph.applied_patch_ids == []
    assert caller_run.model_dump(by_alias=True, mode="json") == caller_before


async def test_two_concurrent_patches_at_same_base_version_only_apply_one():
    store = MemoryWorkflowStore()
    controller, _ = await _initialized(store)
    results = await asyncio.gather(
        controller.apply_patch("run_1", _patch()),
        controller.apply_patch(
            "run_1",
            _patch(
                patch_id="patch_2",
                idempotency_key="idem_2",
                event_id="event_2",
                proposal_id="proposal_2",
                node_id="remedy_2",
            ),
        ),
        return_exceptions=True,
    )

    assert sum(not isinstance(item, Exception) for item in results) == 1
    conflict = next(item for item in results if isinstance(item, Exception))
    assert isinstance(conflict, PatchConflictError)
    assert conflict.code == "GRAPH_VERSION_CONFLICT"
    assert store.get_run("run_1").runtime_graph.graph_version == 2
