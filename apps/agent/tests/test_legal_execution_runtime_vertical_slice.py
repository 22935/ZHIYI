"""Golden integration tests for the Legal Pack on the execution runtime."""

from __future__ import annotations

import json

import pytest

from contracts.planning import TaskImplementationBinding, TaskPlan, PlannedTask, TaskPlanRelation
from contracts.workflow import ReviewDecision, ReviewDecisionType, StepStatus, WorkflowStatus

from app.execution.wiring import build_default_runtime, close_runtime
from packs.legal.planning import build_contract_review_blueprint
from components.planner.acg_semantic_validator import semantic_reachability_projection


_SECRET_MARKER = "TOP-SECRET-CONTRACT-BODY-REF-ONLY-20260815"


def _environment(tmp_path) -> dict[str, str]:
    return {
        "AGENTOS_WORKFLOW_DB_PATH": str(tmp_path / "workflows.sqlite3"),
        "AGENTOS_LANGGRAPH_CHECKPOINT_DB": str(tmp_path / "checkpoints.sqlite3"),
        "AGENTOS_EXECUTION_VALUE_DB": str(tmp_path / "values.sqlite3"),
        "AGENTOS_EXECUTION_MEMORY_DB": str(tmp_path / "memory.sqlite3"),
        "AGENTOS_PROVENANCE_DB": str(tmp_path / "provenance.sqlite3"),
        "AGENTOS_AUDIT_DB": str(tmp_path / "decisions.sqlite3"),
    }


def _output(runtime, run, step_id: str) -> dict:
    output_ref = run.execution_state["outputRefs"][step_id]
    return runtime.execution_value_store.get_output(
        run_id=run.run_id,
        output_ref=output_ref,
    )


async def test_legal_contract_review_restarts_and_resumes_without_replaying_commits(tmp_path):
    environment = _environment(tmp_path)
    first = build_default_runtime(environment=environment)
    try:
        workflow = first.workflow_registry.get("legal_contract_review_v1")
        blueprint = build_contract_review_blueprint(workflow)
        mission = first.create_mission(
            title="Legal contract review golden run",
            domain="legal",
            intent="contract_review",
            workflow_id=workflow.workflow_id,
            input={
                "contractText": (
                    f"{_SECRET_MARKER}. The final payment is not conditional on final acceptance; "
                    "the supplier may reuse customer data for model training."
                ),
                "webSearchEnabled": True,
                "thinkingMode": "disabled",
                "acgBlueprint": blueprint.model_dump(by_alias=True, mode="json"),
            },
        )
        task_plan = TaskPlan(
            missionId=mission.mission_id,
            planVersion=1,
            nodes=tuple(
                PlannedTask(
                    key=f"step:{step.node_id}",
                    title=step.name or step.node_id,
                    objective=step.goal or step.description or step.node_id,
                    capabilityRequirements=((step.capability,) if step.capability else ()),
                    metadata={"plannerStrategy": "legal_pack_explicit_blueprint"},
                )
                for step in blueprint.step_nodes()
            ),
        )
        task_bindings = tuple(
            TaskImplementationBinding(
                planNodeKey=f"step:{step.node_id}",
                acgNodeId=step.node_id,
            )
            for step in blueprint.step_nodes()
        )
        # The fixture declares the same happens-before contract as its explicit graph.
        task_plan = task_plan.model_copy(update={"relations": tuple(
            TaskPlanRelation(sourceKey=source, targetKey=target, relationType="depends_on")
            for source, target in sorted(semantic_reachability_projection(blueprint, task_bindings))
        )})
        mission.input.update({
            "acgBlueprint": blueprint.model_dump(by_alias=True, mode="json"),
            "taskPlan": task_plan.model_dump(by_alias=True, mode="json"),
            "taskBindings": [
                item.model_dump(by_alias=True, mode="json")
                for item in task_bindings
            ],
        })
        first.workflow_store.save_mission(mission)

        paused = await first.start(
            mission.mission_id,
            workflow_id=workflow.workflow_id,
            review_mode="human_in_loop",
        )

        assert paused.status is WorkflowStatus.WAITING_REVIEW
        assert paused.current_step_id == "human_review"
        assert paused.get_step("human_review").status is StepStatus.WAITING_REVIEW
        assert "auto_review" in paused.execution_state["skippedStepIds"]
        assert _output(first, paused, "parse_contract")["contract_type"]
        assert _output(first, paused, "risk_detect")["risks"]
        assert _output(first, paused, "statute_retrieve")["sources"]
        statute_memory = first.memory_store.get(f"memory:{paused.run_id}:statute_retrieve")
        evidence_memory = first.memory_store.get(f"memory:{paused.run_id}:legal_evidence_match")
        assert statute_memory is not None and statute_memory.memory_type.value == "evidence"
        assert evidence_memory is not None and evidence_memory.memory_type.value == "evidence"
        assert paused.execution_state["memoryRefs"]["statute_retrieve"] == statute_memory.memory_id
        assert paused.execution_state["memoryRefs"]["legal_evidence_match"] == evidence_memory.memory_id
        assert any(
            event.event_type.value == "tool_called" and event.step_id == "statute_retrieve"
            for event in paused.trace
        )
        parallel_batches = [
            event.payload.get("stepIds")
            for event in paused.trace
            if event.event_type.value == "step_scheduled"
        ]
        assert any(set(batch or ()) == {"classify_clauses", "statute_retrieve"} for batch in parallel_batches)

        human_commit_id = f"commit:{paused.run_id}:human_review:0"
        committed_before = first.execution_value_store.get_node_commit(
            run_id=paused.run_id,
            commit_id=human_commit_id,
        )
        assert committed_before is not None
        assert committed_before["stage"] == "committed"
        assert first.memory_store.get(f"memory:{paused.run_id}:human_review") is None

        checkpoint_id = paused.execution_state["checkpointId"]
        checkpoint_before = first.checkpoint_store.load(
            run_id=paused.run_id,
            checkpoint_id=checkpoint_id,
        )
        checkpoint_version = first.checkpoint_store.latest_version(run_id=paused.run_id)
        state_json = json.dumps(paused.execution_state, ensure_ascii=False, sort_keys=True)
        checkpoint_json = json.dumps(checkpoint_before, ensure_ascii=False, sort_keys=True)
        assert _SECRET_MARKER not in state_json
        assert _SECRET_MARKER not in checkpoint_json
        assert "outputRefs" in checkpoint_before
        assert "contextRefs" in checkpoint_before

        repeated = await first.execute_prepared_run(paused.run_id)
        assert repeated.execution_state["checkpointId"] == checkpoint_id
        assert first.checkpoint_store.latest_version(run_id=paused.run_id) == checkpoint_version
        trace_ids_before = [event.event_id for event in repeated.trace]
        succeeded_before = {
            step_id: sum(
                event.event_type.value == "step_succeeded" and event.step_id == step_id
                for event in repeated.trace
            )
            for step_id in paused.completed_step_ids
        }
        provenance_before = first.provenance_store.load_ledger(
            run_id=paused.run_id,
            mission_id=paused.mission_id,
        )
        provenance_ids_before = {
            event.event_id
            for event in [
                *provenance_before.productions,
                *provenance_before.consumptions,
                *provenance_before.interactions,
            ]
        }
    finally:
        close_runtime(first)

    second = build_default_runtime(environment=environment)
    try:
        resumed_calls: list[str] = []
        for agent in second.agent_registry.all():
            original = agent.run
            agent_name = agent.profile.agent_name

            async def counted(context, *, _original=original, _agent_name=agent_name):
                resumed_calls.append(f"{context.step.step_id}:{_agent_name}")
                return await _original(context)

            agent.run = counted

        completed = await second.apply_review(
            ReviewDecision(
                runId=paused.run_id,
                stepId="human_review",
                decision=ReviewDecisionType.APPROVED,
                operationId="legal-golden-approve",
                reviewer="golden-reviewer",
                comment="approved after legal review",
            )
        )

        assert completed.status is WorkflowStatus.COMPLETED, json.dumps({"review": completed.execution_state.get("reviewPayload"), "completed": completed.completed_step_ids, "skipped": completed.execution_state.get("skippedStepIds"), "steps": [(s.step_id, s.status.value) for s in completed.steps]})
        assert resumed_calls == ["report_generate:report_generate"]
        assert second.execution_value_store.get_node_commit(
            run_id=completed.run_id,
            commit_id=human_commit_id,
        ) == committed_before
        assert second.memory_store.get(f"memory:{completed.run_id}:human_review") is not None
        assert completed.output == {
            "outputRef": completed.execution_state["outputRefs"]["report_generate"]
        }
        report = _output(second, completed, "report_generate")
        assert report["report_markdown"]
        assert "approved after legal review" in report["report_markdown"]

        trace_ids_after = [event.event_id for event in completed.trace]
        assert len(trace_ids_after) == len(set(trace_ids_after))
        assert trace_ids_after[: len(trace_ids_before)] == trace_ids_before
        for step_id, count_before in succeeded_before.items():
            assert sum(
                event.event_type.value == "step_succeeded" and event.step_id == step_id
                for event in completed.trace
            ) == count_before

        provenance_after = second.provenance_store.load_ledger(
            run_id=completed.run_id,
            mission_id=completed.mission_id,
        )
        provenance_ids_after = [
            event.event_id
            for event in [
                *provenance_after.productions,
                *provenance_after.consumptions,
                *provenance_after.interactions,
            ]
        ]
        assert len(provenance_ids_after) == len(set(provenance_ids_after))
        assert provenance_ids_before.issubset(provenance_ids_after)
    finally:
        close_runtime(second)


@pytest.mark.parametrize("force_dynamic", [False, True])
async def test_legal_planner_uses_real_execution_capability_catalog(tmp_path, force_dynamic):
    runtime = build_default_runtime(environment=_environment(tmp_path))
    try:
        mission = runtime.create_mission(
            title="Review a software services contract and produce a legal report",
            domain="legal",
            intent="contract_review",
            workflow_id="legal_contract_review_v1",
            input={
                "userIntent": "parse and classify the contract, identify risks and evidence, then produce a report",
                "usePlanner": True,
                "forceDynamicPlanning": force_dynamic,
                "planningDiversity": "stable",
                "planningSeed": 20260815,
            },
        )

        _, prepared = runtime.prepare_run(
            mission.mission_id,
            workflow_id="legal_contract_review_v1",
            review_mode="human_in_loop",
        )

        assert prepared.acg_blueprint is not None
        assert prepared.execution_state["planningSeed"] == 20260815
        assert prepared.execution_state["selectedCapabilities"]
        assert all(step.capability for step in prepared.steps)
        assert any(
            "Planner produced ACG" in event.observation
            for event in prepared.trace
        )
    finally:
        close_runtime(runtime)
