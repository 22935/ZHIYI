"""AgentOS Core 的 trace 模块，提供运行时控制、状态、Trace、审核或治理能力。"""


from typing import Any, Dict, List, Optional

from agentos.core.models.types import AgentTask, TraceEvent, TraceEventType, WorkflowRun


class TraceStore:
    """绑定 WorkflowRun 对象的内存 Trace 写入器。"""

    def __init__(self):
        self._task_events: dict[str, list[TraceEvent]] = {}

    def append(
        self,
        run: WorkflowRun,
        event_type: TraceEventType,
        observation: str = "",
        step_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        duration_ms: int = 0,
    ) -> TraceEvent:
        event = TraceEvent(
            runId=run.run_id,
            stepId=step_id,
            agentName=agent_name,
            eventType=event_type,
            observation=observation,
            payload=payload or {},
            durationMs=max(0, int(duration_ms)),
        )
        run.trace.append(event)
        return event

    def append_task(
        self,
        task: AgentTask,
        event_type: TraceEventType,
        observation: str = "",
        payload: Optional[Dict[str, Any]] = None,
    ) -> TraceEvent:
        event = TraceEvent(
            runId=None,
            eventType=event_type,
            observation=observation,
            payload=payload or {},
        )
        self._task_events.setdefault(task.task_id, []).append(event)
        return event

    def task_events(self, task_id: str) -> List[TraceEvent]:
        return list(self._task_events.get(task_id, []))

    def delete_task_events(self, task_id: str) -> None:
        """Release task-level in-memory trace data after an orphan task is deleted."""

        self._task_events.pop(task_id, None)

    def export_json(self, run: WorkflowRun) -> Dict[str, Any]:
        """返回可供 API、审计和报告使用的可移植 Trace 数据。"""

        return {
            "runId": run.run_id,
            "taskId": run.task_id,
            "workflowId": run.workflow_id,
            "domain": run.domain,
            "status": run.status.value,
            "eventCount": len(run.trace),
            "events": [event.model_dump(by_alias=True, mode="json") for event in self.events(run)],
        }

    def export_markdown(self, run: WorkflowRun) -> str:
        """渲染紧凑的人类可读 Trace 报告。"""

        lines: List[str] = [
            f"# Workflow Trace: {run.run_id}",
            "",
            f"- Task: {run.task_id}",
            f"- Workflow: {run.workflow_id}",
            f"- Domain: {run.domain}",
            f"- Status: {run.status.value}",
            f"- Events: {len(run.trace)}",
            "",
            "## Events",
            "",
        ]
        for index, event in enumerate(self.events(run), start=1):
            created_at = event.created_at.isoformat()
            title_parts = [f"{index}. `{event.event_type.value}`", created_at]
            if event.step_id:
                title_parts.append(f"step={event.step_id}")
            if event.agent_name:
                title_parts.append(f"agent={event.agent_name}")
            lines.append(" - ".join(title_parts))
            if event.observation:
                lines.append(f"   - {event.observation}")
            if event.duration_ms:
                lines.append(f"   - durationMs: {event.duration_ms}")
        return "\n".join(lines).rstrip() + "\n"

    def events(self, run: WorkflowRun) -> List[TraceEvent]:
        return sorted(run.trace, key=lambda event: (event.created_at, event.event_id))
