"""运行时必须把外部模型和工具置于统一保护边界内。"""

from __future__ import annotations

import asyncio

from adapters.guarded_tool import ToolInvocationError
from adapters.model_adapter import StructuredGenerationError, StructuredGenerationResult
from contracts.workflow import WorkflowDefinition, WorkflowStatus, WorkflowStepDefinition
from runtime.workflow_runtime import ExecutionRuntime
from service.agents import AgentRegistry
from service.agents.base import AgentOutput, AgentProfile, BaseAgent
from components.mission_manager.store import WorkflowRegistry
from support.stores.memory_workflow_store import MemoryWorkflowStore


class _FlakyModel:
    """首次模型调用短暂失败，后续成功并记录提交标识。"""

    def __init__(self) -> None:
        self.commit_ids: list[str | None] = []

    def is_available(self) -> bool:
        return True

    async def generate_json(self, *, commit_id: str | None = None, **_kwargs) -> StructuredGenerationResult:
        self.commit_ids.append(commit_id)
        if len(self.commit_ids) == 1:
            raise StructuredGenerationError("MODEL_TEMPORARY_UNAVAILABLE", "temporary")
        return StructuredGenerationResult(data={"answer": "model"}, provider="test", model="test")


class _FlakyTool:
    """首次工具调用短暂失败，后续成功并记录提交标识。"""

    def __init__(self) -> None:
        self.commit_ids: list[str | None] = []

    def scoped(self, _allowed_tools):
        return self

    async def run(self, _text: str, **_kwargs):
        return {"ok": True}

    async def execute(self, _name: str, _arguments: dict, **kwargs):
        self.commit_ids.append(kwargs.get("commit_id"))
        if len(self.commit_ids) == 1:
            raise ToolInvocationError("TOOL_TEMPORARY_UNAVAILABLE", "temporary")
        return {"answer": "tool"}


class _ModelAgent(BaseAgent):
    """通过节点上下文中的模型运行时执行结构化调用。"""

    async def run(self, context) -> AgentOutput:
        result = await context.model_runtime.generate_json(
            prompt="private",
            schema={"type": "object"},
            commit_id=context.commit_id,
        )
        return AgentOutput(output=result.data)


class _ToolAgent(BaseAgent):
    """通过节点上下文中的工具运行时执行有副作用调用。"""

    async def run(self, context) -> AgentOutput:
        result = await context.tool_runtime.execute(
            "search",
            {"query": "private"},
            commit_id=context.commit_id,
        )
        return AgentOutput(output=result)


def _freeze_single_step_graph(runtime: ExecutionRuntime) -> None:
    """轻量 workflow 提升通道已删除:夹具显式冻结等价的单节点蓝图。

    任务侧仍提供完整合同(mission 与单节点 TaskPlan),图内容与原提升路径一致。
    """
    from components.planner.acg_lowerer import ACGLowerer, ACGLoweringInput, ACGLoweringStep
    from contracts.planning import PlannedTask, TaskImplementationBinding, TaskPlan
    from support.acg.planning import ACGResourcePlan, AgentBindingSpec
    from support.acg.schema import ComplexityLevel

    def build(task, run, workflow):
        definition = workflow.steps[0]
        node_id = definition.step_id
        key = f"step:{node_id}"
        plan = TaskPlan(
            missionId=task.mission_id, planVersion=1,
            nodes=(PlannedTask(key=key, title=definition.name, objective=definition.name),),
        )
        lowering = ACGLoweringInput(
            mission_id=task.mission_id,
            objective=workflow.name,
            complexity_level=ComplexityLevel.SIMPLE,
            task_plan=plan,
            steps=(ACGLoweringStep(
                task_key=key, node_id=node_id, name=definition.name,
                goal=definition.name, metadata={"taskPlanKey": key},
            ),),
            implementation_bindings=(TaskImplementationBinding(planNodeKey=key, acgNodeId=node_id),),
            resource_plan=ACGResourcePlan(bindings=(AgentBindingSpec(
                stepId=node_id,
                plannedAgentId=definition.agent_name or node_id,
            ),)),
        )
        return ACGLowerer().lower(lowering), None, ()

    runtime._build_acg_blueprint = build


def _runtime(*, agent: BaseAgent, tool_runtime=None) -> ExecutionRuntime:
    """创建一个只包含单个受控 Agent 的最小 ACG 运行时。"""
    agents = AgentRegistry()
    agents.register(agent)
    workflows = WorkflowRegistry()
    workflows.register(WorkflowDefinition(
        workflowId="guard-run",
        name="guard run",
        domain="general",
        runtimeEngine="acg",
        steps=[WorkflowStepDefinition(
            stepId="one",
            name="one",
            agentName=agent.profile.agent_name,
            outputSpec={"type": "object", "properties": {"answer": {"type": "string"}}},
        )],
    ))
    runtime = ExecutionRuntime(
        agent_registry=agents,
        workflow_registry=workflows,
        workflow_store=MemoryWorkflowStore(),
        tool_runtime=tool_runtime,
    )
    _freeze_single_step_graph(runtime)
    return runtime


def test_runtime_retries_model_with_the_same_commit_id() -> None:
    """Runtime 注入的模型必须自动受保护并在重试时保留同一提交标识。"""
    model = _FlakyModel()
    runtime = _runtime(agent=_ModelAgent(AgentProfile(agentName="model", domain="general")))
    runtime.set_model_runtime(model)
    task = runtime.create_mission("model", workflow_id="guard-run")
    _, run = runtime.prepare_run(task.mission_id)

    result = asyncio.run(runtime.execute_prepared_run(run.run_id))

    assert result.status is WorkflowStatus.COMPLETED
    assert model.commit_ids == [f"commit:{run.run_id}:one:0", f"commit:{run.run_id}:one:0"]


def test_runtime_retries_tool_with_the_same_commit_id() -> None:
    """Runtime 创建的工具视图必须先授权再保护，并在重试时保留提交标识。"""
    tool = _FlakyTool()
    runtime = _runtime(
        agent=_ToolAgent(AgentProfile(agentName="tool", domain="general", allowedTools=["search"])),
        tool_runtime=tool,
    )
    task = runtime.create_mission("tool", workflow_id="guard-run")
    _, run = runtime.prepare_run(task.mission_id)

    result = asyncio.run(runtime.execute_prepared_run(run.run_id))

    assert result.status is WorkflowStatus.COMPLETED
    assert tool.commit_ids == [f"commit:{run.run_id}:one:0", f"commit:{run.run_id}:one:0"]
