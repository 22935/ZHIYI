"""Core-owned General review recovery through two application runtime restarts."""

from __future__ import annotations

from copy import deepcopy
import os

from adapters.model.native import GENERAL_EVIDENCE_WORKFLOW_ID
from app.execution.coordinator import RunExecutionCoordinator
from app.execution.wiring import build_default_runtime, close_runtime
from contracts.workflow import ReviewDecision, ReviewDecisionType, WorkflowStatus


def _environment(tmp_path) -> dict[str, str]:
    return {
        **os.environ,
        "AGENTOS_WORKFLOW_DB_PATH": str(tmp_path / "workflows.sqlite3"),
        "AGENTOS_LANGGRAPH_CHECKPOINT_DB": str(tmp_path / "checkpoints.sqlite3"),
        "AGENTOS_EXECUTION_VALUE_DB": str(tmp_path / "values.sqlite3"),
        "AGENTOS_EXECUTION_MEMORY_DB": str(tmp_path / "memory.sqlite3"),
        "AGENTOS_PROVENANCE_DB": str(tmp_path / "provenance.sqlite3"),
        "AGENTOS_AUDIT_DB": str(tmp_path / "decisions.sqlite3"),
        "AGENTOS_RESOURCE_DB": str(tmp_path / "resources.sqlite3"),
        "AGENTOS_EVOLUTION_DB": str(tmp_path / "evolution.sqlite3"),
    }


def _provenance_ids(runtime, run) -> list[str]:
    ledger = runtime.provenance_store.load_ledger(run_id=run.run_id, mission_id=run.mission_id)
    return [
        event.event_id
        for event in [*ledger.productions, *ledger.consumptions, *ledger.interactions]
    ]


async def test_golden_workflow_integration_survives_two_ai_service_restarts(tmp_path) -> None:
    environment = _environment(tmp_path)
    first = build_default_runtime(environment=environment)
    try:
        mission = first.create_mission(
            title="Evaluate an AgentOS release decision with cited evidence",
            domain="general",
            intent="evidence_decision",
            workflow_id=GENERAL_EVIDENCE_WORKFLOW_ID,
            input={
                "userIntent": (
                    "Extract release facts, retrieve evidence, compare alternatives, "
                    "validate the decision, and produce a citation report."
                ),
                "constraints": ["all conclusions require evidence references"],
                "thinkingMode": "disabled",
            },
        )
        paused = await first.start(
            mission.mission_id,
            workflow_id=GENERAL_EVIDENCE_WORKFLOW_ID,
            review_mode="human_in_loop",
        )

        assert paused.status is WorkflowStatus.WAITING_REVIEW
        assert paused.current_step_id
        review_step = paused.get_step(paused.current_step_id)
        assert review_step.capability == "verification"
        checkpoint_id = paused.execution_state["checkpointId"]
        completed_before = list(paused.completed_step_ids)
        scheduling_before = deepcopy(paused.execution_state["schedulingDecisions"])
        provenance_before = _provenance_ids(first, paused)
        trace_ids_before = [event.event_id for event in paused.trace]
        run_id = paused.run_id
        blueprint_nodes = paused.acg_blueprint["nodes"]
        assert len(blueprint_nodes) == len(paused.steps)
        assert sum(node.get("nodeType") == "step" for node in blueprint_nodes) == len(paused.steps)
        memory_events_before = [
            event for event in paused.trace
            if event.observation == "Structured memory event projected"
        ]
        assert len(memory_events_before) == 6
        assert any(event.payload.get("evidenceRefs") for event in memory_events_before)
        assert len(paused.execution_state["phaseCapsuleRefs"]) == 1
    finally:
        close_runtime(first)

    second = build_default_runtime(environment=environment)
    try:
        closed_on_first_restart = await RunExecutionCoordinator(second).startup()
        after_first = second.get_status(run_id)
        assert run_id not in closed_on_first_restart
        assert after_first.status is WorkflowStatus.WAITING_REVIEW
        assert after_first.execution_state["checkpointId"] == checkpoint_id
        assert after_first.completed_step_ids == completed_before
        assert after_first.execution_state["schedulingDecisions"] == scheduling_before
        assert _provenance_ids(second, after_first) == provenance_before
    finally:
        close_runtime(second)

    third = build_default_runtime(environment=environment)
    try:
        closed_on_second_restart = await RunExecutionCoordinator(third).startup()
        after_second = third.get_status(run_id)
        assert run_id not in closed_on_second_restart
        assert after_second.status is WorkflowStatus.WAITING_REVIEW
        assert after_second.execution_state["checkpointId"] == checkpoint_id
        assert after_second.completed_step_ids == completed_before
        assert after_second.execution_state["schedulingDecisions"] == scheduling_before
        assert _provenance_ids(third, after_second) == provenance_before

        resumed_calls: list[str] = []
        for agent in third.agent_registry.all():
            if agent.profile.agent_name != "native_general_agent":
                continue
            original = agent.run

            async def counted(context, *, _original=original):
                resumed_calls.append(context.step.capability or context.step.step_id)
                return await _original(context)

            agent.run = counted

        completed = await third.apply_review(ReviewDecision(
            runId=run_id,
            stepId=review_step.step_id,
            decision=ReviewDecisionType.APPROVED,
            operationId="general-golden-approve",
            reviewer="golden-reviewer",
            comment="approved after two service restarts",
        ))

        assert completed.status is WorkflowStatus.COMPLETED
        assert resumed_calls == ["artifact_generation"]
        assert [event.event_id for event in completed.trace][:len(trace_ids_before)] == trace_ids_before
        provenance_after = _provenance_ids(third, completed)
        assert set(provenance_before) <= set(provenance_after)
        assert len(provenance_after) > len(provenance_before)
        assert len(provenance_after) == len(set(provenance_after))
        scheduling_after = completed.execution_state["schedulingDecisions"]
        assert scheduling_after[:len(scheduling_before)] == scheduling_before
        assert len(scheduling_after) == len(scheduling_before) + 1
        assert scheduling_after[-1]["stepId"] != review_step.step_id
        assert all(item["lease"]["status"] == "released" for item in scheduling_after)
        assert completed.run_id == run_id

        trajectory, evaluation, proposal = third.propose_evolution_from_run(run_id)
        assert trajectory.task["runId"] == run_id
        assert len(trajectory.outcome["traceRefs"]) == len(completed.trace)
        assert len(trajectory.outcome["phaseCapsuleRefs"]) == 2
        assert all(step.input["candidateCount"] > 0 for step in trajectory.steps)
        assert all(step.input["memoryEventRef"] for step in trajectory.steps)
        assert all(step.output["provenanceRefs"] for step in trajectory.steps)
        assert evaluation.success_score == 1
        assert proposal.status.value == "pending_review"
        policy = third.approve_evolution_proposal(
            proposal.proposal_id,
            approved_by="golden-policy-reviewer",
        )
        assert policy.version == 1

        next_mission = third.create_mission(
            title="Verify the evolved General policy snapshot",
            domain="general",
            intent="evidence_decision",
            workflow_id=GENERAL_EVIDENCE_WORKFLOW_ID,
            input={"userIntent": "Prepare a new evidence decision run."},
        )
        _, next_run = third.prepare_run(
            next_mission.mission_id,
            workflow_id=GENERAL_EVIDENCE_WORKFLOW_ID,
        )
        assert third.get_status(run_id).execution_state["evolutionPolicyVersion"] == 0
        assert next_run.execution_state["evolutionPolicyVersion"] == 1
        assert next_run.execution_state["appliedEvolutionPolicy"] == {
            "memoryTokenBudget": 768
        }
        assert all(
            step.input["memoryPolicy"]["tokenBudget"] == 768
            for step in next_run.steps
            if "memoryPolicy" in step.input
        )
    finally:
        close_runtime(third)
