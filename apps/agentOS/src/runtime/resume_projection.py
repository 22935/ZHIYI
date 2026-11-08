"""断点恢复（successor Run）复用步骤的 Identity 补投影事件构建。

继任 Run 复用源 Run 已完成步骤的输出但不重新调度它们，调度器的
attempt.ensured 事件链不会发生，Identity 侧永远没有对应 Attempt，
Workspace 会把它们显示为 Pending · Attempt 0。本模块是补投影事件链
（attempt.ensured → resource.bound → step.started → step.succeeded）
的唯一构建实现，两处调用：

- Execution Runtime 在恢复落地时调用（随机 ID）：事件随 run 快照同事务
  写入 lifecycle outbox，execution_state_updates 写回继任 Run 以支撑
  链式恢复（workflow_runtime.prepare_single_step_retry）；
- 一次性回填工具以确定性 ID 复用同一构建，保证重跑幂等
  （ops/scripts/backfill_resume_attempts.py，只处理根治代码部署前的
  终态历史 run，故不写回 execution_state）。

事件序约定：同秒入库的事件由 list_outbox 的 (created_at, event_id)
字母序决定应用顺序，attempt < resource.bound < step.started <
step.succeeded 恰好等于因果序——与调度器既有事件同机制，事件类型
命名不可随意更改。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any


def build_reused_step_projection_events(
    *,
    run_id: str,
    mission_id: str,
    reused_step_ids: Sequence[str],
    copied_refs: Mapping[str, str],
    copied_summaries: Mapping[str, str],
    source_run_id: str,
    source_execution_state: Mapping[str, Any],
    source_step_counters: Mapping[str, tuple[int, int]],
    attempt_id_for: Callable[[str], str],
    step_execution_id_for: Callable[[str], str],
) -> tuple[list[dict], dict[str, dict[str, Any]]]:
    """为每个复用步骤构建补投影事件，返回 (events, execution_state_updates)。

    source_step_counters: step_id -> (attempt, retry_count)，取自源 Run 步骤
    记录，仅用于 attemptIds 键与事件审计编号；Identity 投影以 attemptId 为
    幂等锚点自动连续编号，此处编号不参与编号分配。
    execution_state_updates 含 attemptIds/stepExecutionIds/executionBindings
    三个键的新增条目，是否写回由调用方决定。
    """
    def _state_map(key: str) -> dict[str, Any]:
        value = source_execution_state.get(key)
        return value if isinstance(value, dict) else {}

    source_bindings = _state_map("executionBindings")
    source_node_bindings = _state_map("nodeAgentBindings")
    source_model_bindings = _state_map("modelBindings")
    events: list[dict] = []
    state_updates: dict[str, dict[str, Any]] = {
        "attemptIds": {},
        "stepExecutionIds": {},
        "executionBindings": {},
    }
    for step_id in reused_step_ids:
        binding_payload = source_bindings.get(step_id)
        if not isinstance(binding_payload, dict) or not str(binding_payload.get("resourceId") or "").strip():
            raise ValueError(
                f"checkpoint resume reuse requires a persisted source execution binding: {step_id}"
            )
        output_ref = copied_refs.get(step_id)
        if not output_ref:
            raise ValueError(
                f"reused step has no committed outputRef in the successor run: {step_id}"
            )
        attempt, retry_count = source_step_counters.get(step_id, (0, 0))
        attempt_number = max(int(attempt or 0), int(retry_count or 0)) + 1
        attempt_key = f"{step_id}:{attempt_number}:root"
        attempt_id = attempt_id_for(step_id)
        step_execution_id = step_execution_id_for(step_id)
        metadata = dict(binding_payload.get("metadata") or {})
        original_binding_id = binding_payload.get("bindingId")
        if original_binding_id:
            metadata["reusedFromBindingId"] = str(original_binding_id)
        metadata["reusedFromRunId"] = source_run_id
        binding_payload = {
            **binding_payload,
            "bindingId": f"binding:{run_id}:{step_id}:{attempt_id}",
            "runId": run_id,
            "attemptId": attempt_id,
            "metadata": metadata,
        }
        state_updates["attemptIds"][attempt_key] = attempt_id
        state_updates["stepExecutionIds"][attempt_key] = step_execution_id
        state_updates["executionBindings"][step_id] = binding_payload
        node_binding = source_node_bindings.get(step_id)
        model_binding = source_model_bindings.get(step_id)
        resource_id = str(binding_payload.get("resourceId"))
        agent_id = (
            str(node_binding.get("agentId") or resource_id)
            if isinstance(node_binding, dict) else resource_id
        )
        model_id = (
            str(model_binding.get("model") or "runtime-default")
            if isinstance(model_binding, dict) else "runtime-default"
        )
        events.extend([
            {
                "eventId": f"attempt.ensured:{attempt_id}",
                "eventType": "attempt.ensured",
                "aggregateId": run_id,
                "payload": {
                    "runId": run_id, "missionId": mission_id, "stepId": step_id,
                    "attemptId": attempt_id, "attemptNumber": attempt_number,
                },
            },
            {
                "eventId": f"resource.bound:{attempt_id}",
                "eventType": "resource.bound",
                "aggregateId": attempt_id,
                "payload": {
                    "attemptId": attempt_id, "binding": binding_payload,
                    "agentId": agent_id, "modelId": model_id,
                },
            },
            {
                "eventId": f"step.started:{step_execution_id}",
                "eventType": "step.started",
                "aggregateId": step_execution_id,
                "payload": {
                    "runId": run_id, "attemptId": attempt_id, "stepId": step_id,
                    "stepExecutionId": step_execution_id,
                },
            },
            {
                "eventId": f"step.succeeded:{step_execution_id}",
                "eventType": "step.succeeded",
                "aggregateId": step_execution_id,
                "payload": {
                    "runId": run_id, "attemptId": attempt_id,
                    "stepExecutionId": step_execution_id,
                    "result": {
                        "outputRef": output_ref,
                        "outputSummary": str(copied_summaries.get(step_id) or ""),
                    },
                },
            },
        ])
    return events, state_updates


__all__ = ["build_reused_step_projection_events"]
