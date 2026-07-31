"""Compact, versioned workflow checkpoints and their audit references."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List

from agentos.core.models.types import Checkpoint, WorkflowRun


COMPACT_CHECKPOINT_VERSION = 2


def checkpoint_snapshot_hash(snapshot: Dict[str, Any]) -> str:
    """Return a stable digest without storing the snapshot again in Trace."""

    encoded = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def checkpoint_trace_payload(checkpoint: Checkpoint) -> Dict[str, Any]:
    """Build the small audit projection used by checkpoint Trace events."""

    snapshot = checkpoint.state_snapshot
    return {
        "checkpointId": checkpoint.checkpoint_id,
        "stepId": checkpoint.step_id,
        "stepIds": list(checkpoint.step_ids or [checkpoint.step_id]),
        "snapshotVersion": checkpoint.snapshot_version,
        "snapshotHash": checkpoint.snapshot_hash
        or checkpoint_snapshot_hash(snapshot),
        "graphId": snapshot.get("graphId"),
        "graphVersion": snapshot.get("graphVersion"),
    }


class CheckpointStore:
    """Create compact resume snapshots embedded in a ``WorkflowRun``."""

    def create(
        self,
        run: WorkflowRun,
        step_id: str,
        *,
        step_ids: List[str] | None = None,
    ) -> Checkpoint:
        runtime_graph = run.runtime_graph
        graph_version = runtime_graph.graph_version if runtime_graph is not None else None
        graph_id = (
            runtime_graph.graph_id
            if runtime_graph is not None
            else (run.acg_blueprint or {}).get("graphId")
        )
        barrier_step_ids = list(dict.fromkeys(step_ids or [step_id]))
        if step_id not in barrier_step_ids:
            barrier_step_ids.insert(0, step_id)

        # RuntimeGraph owns node state, attempts, outputs, events, patches, and
        # branch decisions. Legacy WorkflowStep and run-level execution fields
        # are projections and must not be snapshotted a second time.
        state_snapshot: Dict[str, Any] = {
            "runId": run.run_id,
            "taskId": run.task_id,
            "workflowId": run.workflow_id,
            "status": run.status.value,
            "runtimeGraph": (
                runtime_graph.model_dump(by_alias=True, mode="json")
                if runtime_graph is not None
                else None
            ),
            "provenance": run.provenance,
            "executionState": dict(run.execution_state),
            "executionScope": (
                run.execution_scope.model_dump(by_alias=True, mode="json")
                if run.execution_scope is not None
                else None
            ),
            "workflowVersion": run.execution_state.get("workflowVersion"),
            "graphId": graph_id,
            "graphVersion": graph_version,
            "appliedPatchIds": (
                list(runtime_graph.applied_patch_ids) if runtime_graph is not None else []
            ),
            "conditionalDecisionCount": (
                len(runtime_graph.branch_decisions) if runtime_graph is not None else 0
            ),
        }
        checkpoint = Checkpoint(
            runId=run.run_id,
            stepId=step_id,
            stepIds=barrier_step_ids,
            snapshotVersion=COMPACT_CHECKPOINT_VERSION,
            snapshotHash=checkpoint_snapshot_hash(state_snapshot),
            stateSnapshot=state_snapshot,
            outputSnapshot={},
            canResume=True,
        )
        run.checkpoints.append(checkpoint)
        return checkpoint

    def find(self, run: WorkflowRun, checkpoint_id: str) -> Checkpoint:
        for checkpoint in run.checkpoints:
            if checkpoint.checkpoint_id == checkpoint_id:
                return checkpoint
        raise KeyError(f"checkpoint not found: {checkpoint_id}")

    def list(self, run: WorkflowRun) -> List[Checkpoint]:
        return sorted(
            run.checkpoints,
            key=lambda checkpoint: (checkpoint.created_at, checkpoint.checkpoint_id),
        )


__all__ = [
    "COMPACT_CHECKPOINT_VERSION",
    "CheckpointStore",
    "checkpoint_snapshot_hash",
    "checkpoint_trace_payload",
]
