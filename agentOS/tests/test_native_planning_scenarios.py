from __future__ import annotations

import asyncio
import hashlib
import json

from agentos.agents import AgentRegistry
from agentos.core.acg import ACGBlueprint, ControlType, EdgeType, NodeType
from agentos.core.models.types import WorkflowStatus
from agentos.core.native import register_native_runtime
from agentos.core.runtime import WorkflowRuntime
from agentos.core.workflow.registry import WorkflowRegistry


SOFTWARE_TASK = (
    "设计一个企业知识库系统的技术方案，包括需求、系统架构、数据流、安全风险、"
    "实施阶段和验收方式。"
)
INDUSTRIAL_TASK = (
    "规划一条智能手机装配生产线，包括工序拆解、设备资源、产能、成本、质量控制和风险。"
)
RESEARCH_TASK = (
    "形成一份关于多智能体长期记忆架构的研究报告，需要资料梳理、证据分析、"
    "方案比较、结论验证和最终报告。"
)


def execute_native(intent: str, model_runtime):
    agents = AgentRegistry()
    workflows = WorkflowRegistry()
    register_native_runtime(agent_registry=agents, workflow_registry=workflows)
    runtime = WorkflowRuntime(agent_registry=agents, workflow_registry=workflows)
    runtime.set_model_runtime(model_runtime)
    task = runtime.create_task(
        title=intent[:30],
        domain="general",
        intent="general",
        input={
            "userIntent": intent,
            "usePlanner": True,
            "planningMode": "dynamic",
            "thinkingMode": "disabled",
        },
    )
    run = asyncio.run(runtime.start(task.task_id, review_mode="auto"))
    return task, run, ACGBlueprint.model_validate(run.acg_blueprint)


def capability_set(run) -> set[str]:
    return {step.capability for step in run.steps if step.capability}


def structure_hash(blueprint: ACGBlueprint) -> str:
    payload = {
        "capabilities": sorted(step.capability for step in blueprint.step_nodes()),
        "dependencies": sorted(
            (edge.source_id, edge.target_id)
            for edge in blueprint.edges_of_type(EdgeType.DEPENDENCY)
        ),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def test_three_native_tasks_generate_distinct_executable_graphs_without_legal_pack(
    structured_model_runtime,
):
    software_task, software_run, software_graph = execute_native(SOFTWARE_TASK, structured_model_runtime)
    industrial_task, industrial_run, industrial_graph = execute_native(INDUSTRIAL_TASK, structured_model_runtime)
    research_task, research_run, research_graph = execute_native(RESEARCH_TASK, structured_model_runtime)

    software = capability_set(software_run)
    industrial = capability_set(industrial_run)
    research = capability_set(research_run)

    assert {"requirement_analysis", "architecture_design", "risk_analysis"}.issubset(software)
    assert "process_decomposition" not in software
    assert {"process_decomposition", "resource_planning", "cost_analysis"}.issubset(industrial)
    assert {"information_retrieval", "evidence_analysis", "comparative_analysis"}.issubset(research)
    assert "architecture_design" not in research
    assert len({frozenset(software), frozenset(industrial), frozenset(research)}) == 3

    for task, run, blueprint in [
        (software_task, software_run, software_graph),
        (industrial_task, industrial_run, industrial_graph),
        (research_task, research_run, research_graph),
    ]:
        assert task.recommended_workflow == "native_acg_runtime_v1"
        assert run.status == WorkflowStatus.COMPLETED
        assert run.runtime_graph is not None and run.runtime_graph.graph_version == 1
        assert run.output.get("final_answer")
        assert all(step.status.value == "completed" for step in run.steps)
        assert blueprint.step_nodes()

    assert any(
        node.node_type == NodeType.CONTROL
        and getattr(node, "control_type", None) == ControlType.PARALLEL
        for node in industrial_graph.nodes
    )
    assert len(
        {
            structure_hash(software_graph),
            structure_hash(industrial_graph),
            structure_hash(research_graph),
        }
    ) == 3


def test_unrecognized_native_task_uses_exact_three_step_fallback_and_executes(
    structured_model_runtime,
):
    task, run, blueprint = execute_native("把这件事情妥善处理好。", structured_model_runtime)

    assert task.recommended_workflow == "native_acg_runtime_v1"
    assert [step.capability for step in run.steps] == [
        "task_understanding",
        "analysis",
        "artifact_generation",
    ]
    assert len(blueprint.step_nodes()) == 3
    assert run.status == WorkflowStatus.COMPLETED
    assert run.output.get("final_answer")
