from __future__ import annotations

import pytest

from components.executor.node_runner import ACGNodeRunner
from components.executor.graph import ACGExecutionState
from service.agents.base import AgentOutput, AgentProfile, BaseAgent


class _LocalAgent(BaseAgent):
    async def run(self, context):
        raise AssertionError("the local Agent must not run when a resource Adapter is bound")


class _RecordingResourceAdapter:
    def __init__(self) -> None:
        self.context = None

    async def run(self, context):
        self.context = context
        return AgentOutput(output={"source": "remote"}, summary="remote result")


@pytest.mark.asyncio
async def test_bound_resource_adapter_takes_precedence_over_local_agent() -> None:
    agent = _LocalAgent(AgentProfile(agentName="local", domain="general"))
    adapter = _RecordingResourceAdapter()
    runner = ACGNodeRunner.minimal(
        agent=agent,
        resource_execution_adapters={"one": adapter},
    )

    result = await runner("one", ACGExecutionState(runId=runner.run.run_id, graphId="graph"))

    assert result["outputSummary"] == "remote result"
    assert adapter.context is not None
