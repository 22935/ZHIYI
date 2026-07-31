import json

from agentos.core.acg import ACGBlueprint, StepNode
from agentos.core.governance.checkpoint import (
    COMPACT_CHECKPOINT_VERSION,
    CheckpointStore,
    checkpoint_snapshot_hash,
    checkpoint_trace_payload,
)
from agentos.core.models.types import Checkpoint, WorkflowRun, WorkflowStep
from agentos.core.runtime_graph import RuntimeGraph


def _run() -> WorkflowRun:
    blueprint = ACGBlueprint(
        graphId="graph_checkpoint",
        taskId="task_checkpoint",
        nodes=[StepNode(nodeId="a", name="A", agentName="worker")],
    )
    graph = RuntimeGraph.from_blueprint(run_id="run_checkpoint", blueprint=blueprint)
    graph.get_node("a").output = {"large": "x" * 8_000}
    return WorkflowRun(
        runId="run_checkpoint",
        taskId="task_checkpoint",
        workflowId="workflow_checkpoint",
        domain="test",
        runtimeEngine="acg",
        input={"duplicatedMaterial": "y" * 8_000},
        output={"duplicatedArtifact": "z" * 8_000},
        acgBlueprint=blueprint.model_dump(by_alias=True, mode="json"),
        runtimeGraph=graph,
        steps=[
            WorkflowStep(
                stepId="a",
                name="A",
                agentName="worker",
                output={"large": "x" * 8_000},
            )
        ],
    )


def test_compact_checkpoint_keeps_runtime_authority_without_legacy_projections():
    run = _run()
    checkpoint = CheckpointStore().create(run, "a", step_ids=["a", "b"])

    assert checkpoint.snapshot_version == COMPACT_CHECKPOINT_VERSION
    assert checkpoint.step_id == "a"
    assert checkpoint.step_ids == ["a", "b"]
    assert checkpoint.output_snapshot == {}
    assert checkpoint.snapshot_hash == checkpoint_snapshot_hash(checkpoint.state_snapshot)
    assert checkpoint.state_snapshot["runtimeGraph"]["nodes"][0]["output"] == {
        "large": "x" * 8_000
    }
    assert not {
        "input",
        "output",
        "steps",
        "acgBlueprint",
        "completedStepIds",
        "pendingStepIds",
        "activeStepIds",
        "runtimeEvents",
        "branchDecisions",
    }.intersection(checkpoint.state_snapshot)


def test_checkpoint_trace_is_a_small_reference_and_legacy_model_still_loads():
    checkpoint = CheckpointStore().create(_run(), "a")
    reference = checkpoint_trace_payload(checkpoint)

    assert reference["checkpointId"] == checkpoint.checkpoint_id
    assert reference["snapshotHash"] == checkpoint.snapshot_hash
    assert "stateSnapshot" not in reference
    assert len(json.dumps(reference)) * 10 < len(
        checkpoint.model_dump_json(by_alias=True)
    )

    legacy = Checkpoint.model_validate(
        {
            "checkpointId": "ckpt_legacy",
            "runId": "run_legacy",
            "stepId": "legacy_step",
            "stateSnapshot": {"graphVersion": 1},
            "outputSnapshot": {"old": True},
        }
    )
    assert legacy.snapshot_version == 1
    assert legacy.snapshot_hash is None
    assert legacy.step_ids == []
