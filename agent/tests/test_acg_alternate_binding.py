from __future__ import annotations

import asyncio

import pytest

from agentos.agents import AgentOutput, AgentProfile, AgentRegistry, BaseAgent
from agentos.agents.registry import AgentNotFound
from agentos.core.acg import ACGBlueprint, StepNode
from agentos.core.models.types import WorkflowDefinition, WorkflowStatus, WorkflowStepDefinition
from agentos.core.runtime import WorkflowRuntime
from agentos.core.workflow.progress import ProgressAssembler
from agentos.core.workflow.registry import WorkflowRegistry


class _UnavailableAgent(BaseAgent):
    def __init__(self, name: str, domain: str, calls: list[str]):
        super().__init__(AgentProfile(agentName=name, domain=domain, capabilities=["analyze"]))
        self.calls = calls

    async def run(self, context):
        self.calls.append(self.profile.agent_name)
        raise AgentNotFound("binding disappeared")


class _SuccessfulAgent(BaseAgent):
    def __init__(self, name: str, domain: str, calls: list[str]):
        super().__init__(AgentProfile(agentName=name, domain=domain, capabilities=["analyze"]))
        self.calls = calls

    async def run(self, context):
        self.calls.append(self.profile.agent_name)
        return AgentOutput(output={"agent": self.profile.agent_name, "accepted": True})


def _execute(domain: str, *, with_alternate: bool = True):
    calls: list[str] = []
    agents = AgentRegistry()
    agents.register(_UnavailableAgent("primary", domain, calls))
    if with_alternate:
        agents.register(_SuccessfulAgent("alternate", domain, calls))
    workflows = WorkflowRegistry()
    workflows.register(
        WorkflowDefinition(
            workflowId="binding_workflow",
            name="Binding workflow",
            domain=domain,
            intent="review",
            runtimeEngine="acg",
            steps=[
                WorkflowStepDefinition(
                    stepId="analysis",
                    name="Analysis",
                    agentName="primary",
                    capability="analyze",
                    maxRetries=1,
                )
            ],
        )
    )
    runtime = WorkflowRuntime(agent_registry=agents, workflow_registry=workflows)
    blueprint = ACGBlueprint(
        graphId="binding_graph",
        nodes=[
            StepNode(
                nodeId="analysis",
                name="Analysis",
                agentName="primary",
                capability="analyze",
                retryLimit=1,
            )
        ],
        edges=[],
    )

    blueprint_snapshot = blueprint.model_dump(by_alias=True, mode="json")

    async def run_workflow():
        task = runtime.create_task(
            title="binding",
            domain=domain,
            intent="review",
            input={"acgBlueprint": blueprint.model_dump(by_alias=True, mode="json")},
        )
        return await runtime.start(task.task_id, workflow_id="binding_workflow")

    run = asyncio.run(run_workflow())
    assert blueprint.model_dump(by_alias=True, mode="json") == blueprint_snapshot
    return run, calls, blueprint


@pytest.mark.parametrize("domain", ["legal_binding_test", "code_binding_test"])
def test_failed_agent_switches_binding_and_next_attempt_uses_alternate(domain):
    run, calls, blueprint = _execute(domain)
    graph = run.runtime_graph
    node = graph.get_node("analysis")
    progress = ProgressAssembler().assemble(run)

    assert run.status == WorkflowStatus.COMPLETED
    assert calls == ["primary", "alternate"]
    assert graph.graph_version == 2
    assert len(graph.nodes) == 1 and len(graph.edges) == 0
    assert len(node.attempts) == 2
    assert node.attempts[0].agent_name == "primary"
    assert node.attempts[0].error
    assert node.attempts[1].agent_name == "alternate"
    assert node.attempts[0].binding_id != node.attempts[1].binding_id
    assert node.current_binding["agentName"] == "alternate"
    assert node.binding_switch_count == 1
    assert run.get_step("analysis").agent_name == "alternate"
    assert progress.total_steps == 1
    assert progress.dynamic_step_count == 0
    assert progress.graph_version == 2
    assert progress.binding_switch_count == 1


def test_exhausted_candidates_fail_without_reusing_failed_binding():
    run, calls, _ = _execute("exhausted_binding_test", with_alternate=False)
    node = run.runtime_graph.get_node("analysis")

    assert run.status == WorkflowStatus.FAILED
    assert calls == ["primary"]
    assert run.runtime_graph.graph_version == 1
    assert len(node.attempts) == 1
    assert node.binding_switch_count == 0
    assert run.runtime_graph.runtime_events[0].status.value == "REJECTED"
    assert run.runtime_graph.pending_runtime_event_ids == []
