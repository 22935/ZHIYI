"""线性工作流 → ACG 自动升格。

现有 WorkflowDefinition 是基于 nextStepId 的线性步骤链。本模块把它无损
升格为 ACGBlueprint：每个 step 变成一个 StepNode，相邻 step 之间连一条
DEPENDENCY 边。一条线性链就是一张最简单的 DAG，因此升格后的图可被
ACG 执行器以“就绪集调度”方式执行，行为与原线性执行完全一致。

这保证了存量工作流零改动接入新架构，是“静态优选、动态补位”里
“静态”一侧的落地基础。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agentos.core.acg.blueprint import ACGBlueprint
from agentos.core.acg.edges import ACGEdge
from agentos.core.acg.enums import ComplexityLevel, EdgeType
from agentos.core.acg.nodes import AgentNode, EvidenceNode, MemoryNode, StepNode, _node_id

if TYPE_CHECKING:
    from agentos.core.models.types import WorkflowDefinition


def _complexity_from_step_count(count: int) -> ComplexityLevel:
    if count <= 3:
        return ComplexityLevel.SIMPLE
    if count <= 7:
        return ComplexityLevel.MEDIUM
    if count <= 15:
        return ComplexityLevel.COMPLEX
    return ComplexityLevel.EXTREME


# 注入认知节点的关键词规则（覆盖中英文 capability / stepId）：
# - 产生结论性内容、值得沉淀的步骤 → 注入 Memory 节点
# - 需要外部依据支撑、可审计的步骤 → 注入 Evidence 节点
_MEMORY_KEYWORDS = ("risk", "风险", "suggest", "revision", "建议", "report", "报告", "analysis", "分析", "summary", "结论")
_EVIDENCE_KEYWORDS = ("evidence", "证据", "依据", "statute", "法条", "citation")


def _matches(text: str, keywords: tuple[str, ...]) -> bool:
    low = (text or "").lower()
    return any(k in low for k in keywords)


def promote_workflow_to_acg(
    workflow: "WorkflowDefinition",
    *,
    task_id: str | None = None,
    enrich: bool = True,
) -> ACGBlueprint:
    """把线性 WorkflowDefinition 升格为 ACGBlueprint。

    - 保留 step 顺序：用每个 step 的 stepId 作为 StepNode.node_id。
    - 依赖边：按 next_step_id 串联；若无显式 next，则按声明顺序串联。
    - reviewRequired 透传到 StepNode.review_required。
    - enrich=True（默认）时注入认知协作节点，使图从线性链变为多层认知网络：
        * 每个 Step 挂一个执行 Agent 节点（按 agentName 去重复用）+ EXECUTION 边
        * 产出结论的 Step 挂 Memory 节点 + WRITE 边
        * 需外部依据的 Step 挂 Evidence 节点 + SUPPORT 边
      这些节点与边不参与就绪集调度（执行器只看 STEP + DEPENDENCY），
      因此不改变执行行为，仅丰富拓扑的认知协作语义与可视化表达。
    """
    steps = list(workflow.steps)
    blueprint = ACGBlueprint(
        taskId=task_id,
        objective=workflow.description or workflow.name,
        complexityLevel=_complexity_from_step_count(len(steps)),
        metadata={
            "sourceWorkflowId": workflow.workflow_id,
            "sourceWorkflowVersion": workflow.version,
            "promotedFromLinear": True,
            "enriched": enrich,
            "runtimeEngine": workflow.effective_runtime_engine,
        },
    )

    for definition in steps:
        node = StepNode(
            nodeId=definition.step_id,
            name=definition.name,
            stepType="agent",
            goal=definition.name,
            agentName=definition.agent_name,
            capability=definition.capability,
            inputSpec=dict(definition.input),
            outputSpec=dict(definition.output_spec),
            reviewRequired=definition.review_required,
            retryLimit=definition.max_retries,
            timeout=definition.timeout,
            priority=definition.priority,
        )
        blueprint.nodes.append(node)

    # 构建依赖边：优先用显式 next_step_id，回退到声明顺序。
    step_ids = {definition.step_id for definition in steps}
    for index, definition in enumerate(steps):
        target_id = definition.next_step_id
        if target_id in ("", "done", "completed", None):
            target_id = None
        if target_id is None and index + 1 < len(steps):
            target_id = steps[index + 1].step_id
        if target_id and target_id in step_ids:
            blueprint.edges.append(
                ACGEdge(
                    sourceId=definition.step_id,
                    targetId=target_id,
                    edgeType=EdgeType.DEPENDENCY,
                )
            )

    # input.from 是结构化通信契约。为每个声明的数据来源创建通信边，并补齐
    # 执行依赖，保证消费者不会在生产者完成前被调度。
    for definition in steps:
        from_map = definition.input.get("from") if isinstance(definition.input, dict) else None
        if not isinstance(from_map, dict):
            continue
        for source_id, fields in from_map.items():
            if source_id not in step_ids or source_id == definition.step_id:
                continue
            data_fields = [str(field) for field in fields] if isinstance(fields, list) else []
            blueprint.edges.append(
                ACGEdge(
                    sourceId=source_id,
                    targetId=definition.step_id,
                    edgeType=EdgeType.COMMUNICATION,
                    dataFields=data_fields,
                    metadata={"contract": "input.from"},
                )
            )
            if not any(
                edge.edge_type == EdgeType.DEPENDENCY
                and edge.source_id == source_id
                and edge.target_id == definition.step_id
                for edge in blueprint.edges
            ):
                blueprint.edges.append(
                    ACGEdge(
                        sourceId=source_id,
                        targetId=definition.step_id,
                        edgeType=EdgeType.DEPENDENCY,
                        metadata={"derivedFrom": "input.from"},
                    )
                )

    if enrich:
        _inject_cognitive_nodes(blueprint, steps)

    blueprint.touch()
    return blueprint


def _inject_cognitive_nodes(blueprint: ACGBlueprint, steps) -> None:
    """为每个 Step 注入 Agent / Memory / Evidence 认知节点与关联边。"""
    agent_nodes: dict[str, str] = {}  # agentName -> agent_node_id（去重复用）
    memory_nodes: dict[str, str] = {}
    evidence_nodes: dict[str, str] = {}

    for definition in steps:
        step_id = definition.step_id
        agent_name = definition.agent_name or step_id
        cap = definition.capability or ""
        sig = f"{cap} {step_id}"

        # 1) 执行 Agent 节点（同名 Agent 复用一个节点，体现“一个 Agent 执行多个 Step”）
        if agent_name not in agent_nodes:
            an_id = f"agent::{agent_name}"
            blueprint.nodes.append(
                AgentNode(
                    nodeId=an_id,
                    name=agent_name,
                    role=cap or agent_name,
                    capabilityTags=[cap] if cap else [],
                )
            )
            agent_nodes[agent_name] = an_id
        blueprint.edges.append(
            ACGEdge(sourceId=agent_nodes[agent_name], targetId=step_id, edgeType=EdgeType.EXECUTION)
        )

        # 2) Evidence 节点（需外部依据支撑的步骤）
        if _matches(sig, _EVIDENCE_KEYWORDS):
            ev_id = _node_id("ev")
            blueprint.nodes.append(
                EvidenceNode(
                    nodeId=ev_id,
                    name=f"证据·{definition.name}",
                    evidenceType="retrieved",
                    metadata={"producerStepId": step_id},
                )
            )
            evidence_nodes[step_id] = ev_id

        # 3) Memory 节点（产出结论、值得沉淀的步骤）
        if _matches(sig, _MEMORY_KEYWORDS):
            mem_id = _node_id("mem")
            blueprint.nodes.append(
                MemoryNode(nodeId=mem_id, name=f"记忆·{definition.name}", memoryType="episodic")
            )
            blueprint.edges.append(
                ACGEdge(sourceId=step_id, targetId=mem_id, edgeType=EdgeType.WRITE)
            )
            memory_nodes[step_id] = mem_id

    # READ/SUPPORT 只连接真实声明消费该生产步骤的下游节点。
    for definition in steps:
        from_map = definition.input.get("from") if isinstance(definition.input, dict) else None
        if not isinstance(from_map, dict):
            continue
        for source_id in from_map:
            if source_id in memory_nodes:
                blueprint.edges.append(
                    ACGEdge(
                        sourceId=memory_nodes[source_id],
                        targetId=definition.step_id,
                        edgeType=EdgeType.READ,
                    )
                )
            if source_id in evidence_nodes:
                blueprint.edges.append(
                    ACGEdge(
                        sourceId=evidence_nodes[source_id],
                        targetId=definition.step_id,
                        edgeType=EdgeType.SUPPORT,
                    )
                )


__all__ = ["promote_workflow_to_acg"]
