"""runtime 执行语义测试的共享夹具边界。

轻量 workflow 提升通道(promote_workflow_to_acg + identity-free fallback)已从
生产代码删除:``ExecutionRuntime._build_acg_blueprint`` 对"预定义 steps 的
identity-free workflow"现在 fail-closed。生产装配(require_planner_identity=True)
不受影响;但本目录大量执行语义测试(checkpoint 校验、重试幂等、资源绑定、trace
投影)以"预定义 steps 的 identity-free runtime"为确定性夹具。

本 fixture 在测试层精确兜住那条 fail-closed ValueError,按原提升行为冻结等价
蓝图(顺序链边、input.from 通信合同与依赖、逻辑绑定、记忆/证据声明)。测试
显式提供 acgBlueprint/taskPlan 或走 planner 的用例不受影响。
"""
from __future__ import annotations

import pytest

from components.planner.lowering_input import _template_blueprint_from_workflow
from support.acg.schema import ACGEdge, EdgeType

_PROMOTION_REMOVED = "workflow step promotion was removed"


def _chain_and_input_edges(blueprint, steps) -> None:
    """复刻原提升通道的两类依赖边:顺序链与 input.from。"""
    step_ids = {definition.step_id for definition in steps}
    for index, definition in enumerate(steps):
        target_id = definition.next_step_id
        if target_id in ("", "done", "completed", None):
            target_id = steps[index + 1].step_id if index + 1 < len(steps) else None
        if (
            target_id
            and target_id in step_ids
            and target_id != definition.step_id
            and not any(
                edge.source_id == definition.step_id
                and edge.target_id == target_id
                and edge.edge_type is EdgeType.DEPENDENCY
                for edge in blueprint.edges
            )
        ):
            blueprint.edges.append(ACGEdge(
                sourceId=definition.step_id, targetId=target_id,
                edgeType=EdgeType.DEPENDENCY,
            ))
    for definition in steps:
        from_map = definition.input.get("from") if isinstance(definition.input, dict) else None
        if not isinstance(from_map, dict):
            continue
        for source_id in from_map:
            if source_id not in step_ids or source_id == definition.step_id:
                continue
            if not any(
                edge.edge_type is EdgeType.DEPENDENCY
                and edge.source_id == source_id
                and edge.target_id == definition.step_id
                for edge in blueprint.edges
            ):
                blueprint.edges.append(ACGEdge(
                    sourceId=source_id, targetId=definition.step_id,
                    edgeType=EdgeType.DEPENDENCY,
                    metadata={"derivedFrom": "input.from"},
                ))


def _freeze_from_steps(task, run, workflow):
    """按原提升行为从预定义 steps 冻结蓝图,返回与原通道一致的 (blueprint, None, ())。

    原 promote 合同不产 TaskPlan、不经 ACGLowerer(无 bound-semantics 校验):
    graph_compiled 事件与 execution_state 的 taskPlan 投影都不发生,这里保持同一形状。
    """
    steps = list(workflow.steps)
    if not steps:
        raise ValueError("step-based test workflows must declare at least one step")
    blueprint = _template_blueprint_from_workflow(workflow, mission_id=task.mission_id)
    _chain_and_input_edges(blueprint, steps)
    return blueprint, None, ()


@pytest.fixture(autouse=True)
def _restore_step_promotion_for_semantic_fixtures(monkeypatch):
    """兜住 identity-free steps workflow 的 fail-closed,恢复等价测试夹具行为。"""
    from runtime.workflow_runtime import ExecutionRuntime

    original = ExecutionRuntime._build_acg_blueprint

    def patched(self, task, run, workflow):
        try:
            return original(self, task, run, workflow)
        except ValueError as exc:
            if _PROMOTION_REMOVED not in str(exc):
                raise
            return _freeze_from_steps(task, run, workflow)

    monkeypatch.setattr(ExecutionRuntime, "_build_acg_blueprint", patched)
