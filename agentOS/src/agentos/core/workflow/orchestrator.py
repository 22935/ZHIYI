"""AgentOS Core 的 orchestrator 模块，提供运行时控制、状态、Trace、审核或治理能力。"""


from time import perf_counter
from typing import Tuple

from agentos.agents.base import AgentOutput, AgentRunContext
from agentos.agents import AgentRegistry
from agentos.memory.workflow_memory import WorkflowMemory
from agentos.adapters.tool_adapter import configured_tool_runtime
from agentos.core.models.types import (
    AgentTask,
    StepStatus,
    WorkflowDefinition,
    WorkflowRun,
    WorkflowStatus,
    WorkflowStep,
)


# ACG remains offline until its lifecycle, timeout, and recovery guarantees are stable.
# Chat owns a separate tool-runtime entry point and is intentionally unaffected.
ACG_NETWORK_TOOLS = frozenset({"web_search", "web_extract"})


class Orchestrator:
    """只理解工作流结构、不绑定行业细节的核心调度器。"""

    def __init__(self, agent_registry: AgentRegistry, capability_catalog=None):
        self.agent_registry = agent_registry
        self.capability_catalog = capability_catalog
        self.model_runtime = None

    def set_model_runtime(self, model_runtime) -> None:
        self.model_runtime = model_runtime

    def _capability_descriptor(self, capability: str | None):
        if self.capability_catalog is None or not capability:
            return None
        try:
            return self.capability_catalog.get(capability)
        except KeyError:
            return None

    async def dispatch_agent(
        self,
        task: AgentTask,
        run: WorkflowRun,
        workflow: WorkflowDefinition,
        step: WorkflowStep,
        memory: WorkflowMemory,
        context_pack=None,
    ) -> Tuple[AgentOutput, int]:
        agent = self.agent_registry.resolve(
            domain=run.domain,
            agent_name=step.agent_name,
            capability=step.capability,
            allowed_agent_ids=(
                run.execution_scope.agent_ids
                if run.execution_scope is not None
                else None
            ),
        )
        tool_runtime = configured_tool_runtime()
        if tool_runtime is not None:
            allowed_tools = [
                name
                for name in agent.profile.allowed_tools
                if name not in ACG_NETWORK_TOOLS
            ]
            tool_runtime = tool_runtime.scoped(allowed_tools)
        context = AgentRunContext(
            task=task,
            run=run,
            workflow=workflow,
            step=step,
            memory=memory,
            contextPack=context_pack,
            toolRuntime=tool_runtime,
            modelRuntime=self.model_runtime,
            capabilityDescriptor=self._capability_descriptor(step.capability),
        )
        started = perf_counter()
        result = await agent.run(context)
        duration_ms = int((perf_counter() - started) * 1000)
        return result, duration_ms

    def compose_final_output(self, run: WorkflowRun) -> dict:
        artifacts = {step.step_id: step.output for step in run.steps if step.output}
        final_answer = ""
        for step in reversed(run.steps):
            if step.output.get("final_answer"):
                final_answer = str(step.output["final_answer"])
                break
            if step.output.get("draft"):
                final_answer = str(step.output["draft"])
                break

        if not final_answer and run.status == WorkflowStatus.COMPLETED:
            completed = [step.name for step in run.steps if step.status == StepStatus.COMPLETED]
            final_answer = f"Workflow completed: {', '.join(completed)}" if completed else "Workflow completed."

        output = {"artifacts": artifacts}
        if final_answer:
            output["final_answer"] = final_answer
        return output
