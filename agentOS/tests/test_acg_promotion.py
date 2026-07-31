"""线性工作流 → ACG 自动升格的契约测试。

锁定向下兼容不变量：存量线性 WorkflowDefinition 升格后，执行顺序、
审核标记、复杂度评级都与原定义一致，且图结构合法。
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from agentos.core.acg import (
    NodeType,
    ComplexityLevel,
    promote_workflow_to_acg,
    ready_steps,
    validate_blueprint,
)
from agentos.core.models.types import WorkflowDefinition


def _linear_workflow(step_count: int = 3) -> WorkflowDefinition:
    steps = []
    for i in range(step_count):
        nxt = f"s{i + 1}" if i + 1 < step_count else "done"
        steps.append(
            {
                "stepId": f"s{i}",
                "name": f"step-{i}",
                "agentName": f"agent-{i}",
                "nextStepId": nxt,
                "reviewRequired": i == step_count - 1,
            }
        )
    return WorkflowDefinition.model_validate(
        {
            "workflowId": "wf_linear",
            "name": "linear",
                "domain": "general",
                "runtimeEngine": "acg",
                "description": "linear demo",
            "steps": steps,
        }
    )


def test_promote_preserves_linear_order():
    wf = _linear_workflow(5)
    bp = promote_workflow_to_acg(wf, task_id="t1", enrich=False)
    validate_blueprint(bp)

    assert bp.task_id == "t1"
    assert bp.node_count == 5
    assert bp.edge_count == 4  # 线性链 n 个节点 n-1 条边

    # 逐步推进，验证执行顺序与声明顺序一致
    completed: set[str] = set()
    order: list[str] = []
    while True:
        ready = ready_steps(bp, completed)
        if not ready:
            break
        assert len(ready) == 1  # 线性图每次只有一个就绪
        order.append(ready[0])
        completed.add(ready[0])
    assert order == ["s0", "s1", "s2", "s3", "s4"]


def test_promote_carries_review_flag():
    wf = _linear_workflow(3)
    bp = promote_workflow_to_acg(wf)
    last = bp.get_node("s2")
    assert last.review_required is True
    assert bp.get_node("s0").review_required is False


def test_promote_complexity_grading():
    assert promote_workflow_to_acg(_linear_workflow(3)).complexity_level == ComplexityLevel.SIMPLE
    assert promote_workflow_to_acg(_linear_workflow(6)).complexity_level == ComplexityLevel.MEDIUM
    assert promote_workflow_to_acg(_linear_workflow(10)).complexity_level == ComplexityLevel.COMPLEX


def test_promote_without_explicit_next_uses_declaration_order():
    wf = WorkflowDefinition.model_validate(
        {
            "workflowId": "wf_noexplicit",
            "name": "noexplicit",
                "domain": "general",
                "runtimeEngine": "acg",
                "steps": [
                {"stepId": "a", "name": "a", "agentName": "x"},
                {"stepId": "b", "name": "b", "agentName": "x"},
                {"stepId": "c", "name": "c", "agentName": "x"},
            ],
        }
    )
    bp = promote_workflow_to_acg(wf, enrich=False)
    validate_blueprint(bp)
    assert bp.edge_count == 2
    assert sorted(bp.dependency_sources("b")) == ["a"]
    assert sorted(bp.dependency_sources("c")) == ["b"]


def test_promoted_nodes_are_step_type():
    bp = promote_workflow_to_acg(_linear_workflow(3), enrich=False)
    assert len(bp.step_nodes()) == 3
    assert all(n.node_type == NodeType.STEP for n in bp.nodes)
    assert bp.metadata["promotedFromLinear"] is True
    assert bp.metadata["sourceWorkflowId"] == "wf_linear"


def test_promote_enriched_injects_cognitive_nodes():
    """enrich=True（默认）应注入 Agent/Memory/Evidence 认知节点，
    但不改变就绪集调度行为（执行顺序仍线性）。"""
    wf = WorkflowDefinition.model_validate(
        {
            "workflowId": "wf_enrich",
            "name": "enrich",
                "domain": "legal",
                "runtimeEngine": "acg",
                "steps": [
                {"stepId": "parse", "name": "解析", "agentName": "parser", "capability": "parse"},
                {"stepId": "risk", "name": "风险识别", "agentName": "risker", "capability": "risk_detect"},
                {"stepId": "report", "name": "报告生成", "agentName": "reporter", "capability": "report_generate"},
            ],
        }
    )
    bp = promote_workflow_to_acg(wf, enrich=True)
    validate_blueprint(bp)

    # 注入了多类节点
    types = {n.node_type for n in bp.nodes}
    assert NodeType.STEP in types
    assert NodeType.AGENT in types
    assert NodeType.MEMORY in types    # risk/report 含记忆关键词
    assert NodeType.EVIDENCE not in types  # 无真实证据生产步骤，不注入装饰性 Evidence

    # 每个 Step 都有执行 Agent 节点
    assert len(bp.step_nodes()) == 3
    assert len([n for n in bp.nodes if n.node_type == NodeType.AGENT]) == 3

    # 关键：就绪集调度仍线性，认知节点不参与执行
    completed: set[str] = set()
    order: list[str] = []
    while True:
        ready = ready_steps(bp, completed)
        if not ready:
            break
        assert len(ready) == 1
        order.append(ready[0])
        completed.add(ready[0])
    assert order == ["parse", "risk", "report"]
    assert bp.metadata["enriched"] is True
