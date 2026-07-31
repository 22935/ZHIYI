"""Execution adapter protocols and the built-in ACG runtime adapter."""

from __future__ import annotations

from typing import Any, Protocol

from agentos.core.models.types import AgentTask, ReviewDecision, WorkflowDefinition, WorkflowRun


class ExecutionAdapter(Protocol):
    async def start(self, *, task: AgentTask, run: WorkflowRun, workflow: WorkflowDefinition) -> WorkflowRun:
        ...

    async def apply_review(self, decision: ReviewDecision) -> WorkflowRun:
        ...


class ExecutionAdapterFactory(Protocol):
    def __call__(
        self,
        *,
        runtime: Any,
        workflow: WorkflowDefinition,
        implementation_id: str,
    ) -> ExecutionAdapter:
        ...


class ACGWorkflowAdapter:
    """以 ACG 就绪集调度执行工作流（Core Native 自研引擎）。

    通过线性升格或规划器产物得到 ACGBlueprint，再交给 ACGExecutor 做
    并行调度。人审 approve 后从就绪集续跑，保持与治理设施一致。
    """

    def __init__(self, runtime: Any):
        self.runtime = runtime

    def new_executor(self):
        from agentos.core.execution.acg_executor import ACGExecutor

        return ACGExecutor(self.runtime)

    async def start(self, *, task: AgentTask, run: WorkflowRun, workflow: WorkflowDefinition) -> WorkflowRun:
        return await self.runtime._start_acg(
            task=task,
            run=run,
            workflow=workflow,
            executor=self.new_executor(),
        )

    async def apply_review(self, decision: ReviewDecision) -> WorkflowRun:
        return await self.runtime._apply_acg_review(decision, executor=self.new_executor())

