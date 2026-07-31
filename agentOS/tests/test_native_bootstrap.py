from __future__ import annotations

import asyncio

import pytest

from agentos.agents import AgentRegistry
from agentos.core.acg import NodeType, validate_blueprint
from agentos.core.models.types import (
    TraceEventType,
    WorkflowDefinition,
    WorkflowDefinitionType,
    WorkflowStatus,
    WorkflowStepDefinition,
)
from agentos.core.native import (
    NATIVE_ACG_WORKFLOW_ID,
    native_bootstrap_definition,
    register_native_runtime,
)
from agentos.core.planning import ACGBuilder, TaskSemanticProfile
from agentos.core.planning.cognitive_router import CapabilityBinding, CollaborationNetwork
from agentos.core.runtime import WorkflowRuntime, build_default_runtime
from agentos.core.workflow.registry import WorkflowRegistry
from agentos.core.workflow.task_manager import TaskManager
from agentos.stores.memory_workflow_store import MemoryWorkflowStore


def _static_workflow(workflow_id: str, *, domain: str = "legal") -> WorkflowDefinition:
    return WorkflowDefinition(
        workflowId=workflow_id,
        name=workflow_id,
        domain=domain,
        intent="review",
        runtimeEngine="acg",
        steps=[
            WorkflowStepDefinition(
                stepId="review",
                name="Review",
                agentName="review",
            )
        ],
    )


@pytest.mark.parametrize("domain", ["general", "legal", "programmer"])
def test_registry_rejects_empty_non_bootstrap_workflows(domain: str):
    registry = WorkflowRegistry()
    workflow = WorkflowDefinition(
        workflowId=f"{domain}_empty",
        name="Empty template",
        domain=domain,
        intent="general",
        runtimeEngine="acg",
        steps=[],
    )

    with pytest.raises(ValueError, match="must define at least one step"):
        registry.register(workflow)


def test_registry_accepts_and_recommends_native_bootstrap():
    registry = WorkflowRegistry()
    registry.register(native_bootstrap_definition())

    workflow = registry.get(NATIVE_ACG_WORKFLOW_ID)
    recommended = registry.recommend(domain="general", intent="general")

    assert workflow.definition_type == WorkflowDefinitionType.NATIVE_BOOTSTRAP
    assert workflow.is_native_bootstrap is True
    assert workflow.steps == []
    assert recommended is workflow


def test_task_manager_defaults_general_task_to_native_and_respects_explicit_workflow():
    store = MemoryWorkflowStore()
    registry = WorkflowRegistry()
    register_native_runtime(agent_registry=AgentRegistry(), workflow_registry=registry)
    registry.register(_static_workflow("explicit_workflow", domain="general"))
    manager = TaskManager(workflow_store=store, workflow_registry=registry)

    native_task = manager.create_task(title="Native task", domain="general", intent="general")
    explicit_task = manager.create_task(
        title="Explicit task",
        domain="general",
        intent="general",
        workflow_id="explicit_workflow",
    )

    assert native_task.recommended_workflow == NATIVE_ACG_WORKFLOW_ID
    assert explicit_task.recommended_workflow == "explicit_workflow"
    assert manager.bind_workflow(native_task).workflow_id == NATIVE_ACG_WORKFLOW_ID


def test_acg_builder_supports_a_single_native_step():
    network = CollaborationNetwork(
        bindings=[
            CapabilityBinding(
                capability="task_understanding",
                agent_name="native_general_agent",
                score=1.0,
            )
        ]
    )
    profile = TaskSemanticProfile(
        primaryGoal="Understand a task",
        requiredCapabilities=["task_understanding"],
        domainHint="general",
        taskTypeHint="general",
    )

    blueprint = ACGBuilder().build(task_id="task_single", profile=profile, network=network)

    validate_blueprint(blueprint)
    assert len(blueprint.step_nodes()) == 1


def test_native_runtime_executes_without_legal_pack(structured_model_runtime):
    agents = AgentRegistry()
    workflows = WorkflowRegistry()
    register_native_runtime(agent_registry=agents, workflow_registry=workflows)
    runtime = WorkflowRuntime(agent_registry=agents, workflow_registry=workflows)
    runtime.set_model_runtime(structured_model_runtime)

    task = runtime.create_task(
        title="设计一个基础软件项目实施方案",
        domain="general",
        intent="general",
        input={
            "userIntent": "设计一个基础软件项目实施方案，包括目标、阶段、风险和交付物",
            "usePlanner": True,
            "planningMode": "dynamic",
            "thinkingMode": "disabled",
        },
    )
    prepared_task, prepared_run = runtime.prepare_run(task.task_id, review_mode="auto")

    assert prepared_task.task_id == task.task_id
    assert runtime.get_status(prepared_run.run_id).run_id == prepared_run.run_id
    assert prepared_run.workflow_id == NATIVE_ACG_WORKFLOW_ID
    assert prepared_run.runtime_engine == "acg"

    run = asyncio.run(runtime.execute_prepared_run(prepared_run.run_id))
    blueprint = run.acg_blueprint
    graph = run.runtime_graph

    assert workflows.recommend("legal", "contract_review") is None
    with pytest.raises(KeyError):
        runtime.capability_catalog.get("风险识别")
    with pytest.raises(KeyError):
        agents.resolve("legal", agent_name="risk_detect")
    assert run.status == WorkflowStatus.COMPLETED
    assert blueprint is not None and blueprint["nodes"]
    assert graph is not None and graph.graph_version == 1
    runtime_steps = [node for node in graph.nodes if node.node_type == NodeType.STEP]
    assert len(runtime_steps) >= 3
    assert all(node.status.value == "completed" for node in runtime_steps)
    assert run.output.get("final_answer")
    capabilities = {step.capability for step in run.steps}
    assert {"task_understanding", "risk_analysis", "artifact_generation"}.issubset(
        capabilities
    )
    assert any(
        event.event_type == TraceEventType.TASK_STATUS_CHANGED
        and "Planner produced ACG" in event.observation
        for event in run.trace
    )
    assert any(event.event_type == TraceEventType.STEP_SUCCEEDED for event in run.trace)
    model_nodes = [
        node
        for node in runtime_steps
        if node.spec.get("capability") != "information_retrieval"
    ]
    assert len(structured_model_runtime.calls) == len(model_nodes)
    assert all(node.attempts[-1].model_name == "test-model" for node in model_nodes)
    assert all(
        node.attempts[-1].trace_context.get("modelInvocations")
        for node in model_nodes
    )
    assert any(event.event_type == TraceEventType.MODEL_CALLED for event in run.trace)


def test_native_runtime_freezes_generated_planning_seed_and_audit_metadata(
    structured_model_runtime,
):
    agents = AgentRegistry()
    workflows = WorkflowRegistry()
    register_native_runtime(agent_registry=agents, workflow_registry=workflows)
    runtime = WorkflowRuntime(agent_registry=agents, workflow_registry=workflows)
    runtime.set_model_runtime(structured_model_runtime)
    task = runtime.create_task(
        title="Seeded native plan",
        domain="general",
        intent="general",
        input={
            "userIntent": "分析需求、架构、风险和方案并生成交付物",
            "usePlanner": True,
            "planningMode": "dynamic",
            "planningDiversity": "balanced",
        },
    )
    _, prepared = runtime.prepare_run(task.task_id)

    assert prepared.planning_diversity == "balanced"
    assert isinstance(prepared.planning_seed, int)
    assert prepared.input["planningSeed"] == prepared.planning_seed
    frozen_seed = prepared.planning_seed

    run = asyncio.run(runtime.execute_prepared_run(prepared.run_id))
    loaded = runtime.workflow_store.get_run(run.run_id)
    planner_events = [
        event
        for event in loaded.trace
        if event.event_type == TraceEventType.TASK_STATUS_CHANGED
        and "Planner produced ACG" in event.observation
    ]

    assert loaded.status == WorkflowStatus.COMPLETED
    assert loaded.planning_seed == frozen_seed
    assert loaded.planner_algorithm_version == "controlled-stochastic-v1"
    assert loaded.selected_planning_variant_id
    assert loaded.acg_blueprint["metadata"]["planningSeed"] == frozen_seed
    assert planner_events[-1].payload["planningSeed"] == frozen_seed
    assert planner_events[-1].payload["selectedCapabilities"]


def test_native_runtime_fails_explicitly_without_a_model():
    agents = AgentRegistry()
    workflows = WorkflowRegistry()
    register_native_runtime(agent_registry=agents, workflow_registry=workflows)
    runtime = WorkflowRuntime(agent_registry=agents, workflow_registry=workflows)
    task = runtime.create_task(
        title="Prepare a project plan",
        domain="general",
        intent="general",
        input={"userIntent": "Prepare a project plan", "usePlanner": True},
    )

    run = asyncio.run(runtime.start(task.task_id, review_mode="auto"))

    assert run.status == WorkflowStatus.FAILED
    assert any(
        event.event_type == TraceEventType.STEP_FAILED
        and event.payload.get("errorCode") == "MODEL_UNAVAILABLE"
        for event in run.trace
    )


def test_default_runtime_registers_native_before_application_packs(monkeypatch, tmp_path):
    from agentos.core import runtime as runtime_module

    observed: list[str] = []

    def inspect_pack_registration(*, agent_registry, workflow_registry, capability_catalog):
        workflow_registry.get(NATIVE_ACG_WORKFLOW_ID)
        agent_registry.resolve(
            domain="general",
            agent_name="native_general_agent",
            capability="task_understanding",
        )
        assert capability_catalog.get("task_understanding").domain_hints == ["general"]
        with pytest.raises(KeyError):
            capability_catalog.get("风险识别")
        observed.append("native_ready")
        return ()

    monkeypatch.setattr(runtime_module, "register_installed_packs", inspect_pack_registration)
    monkeypatch.setenv("AGENTOS_WORKFLOW_DB_PATH", str(tmp_path / "workflow.db"))

    runtime = build_default_runtime()

    assert observed == ["native_ready"]
    assert runtime.workflow_registry.get(NATIVE_ACG_WORKFLOW_ID).is_native_bootstrap
