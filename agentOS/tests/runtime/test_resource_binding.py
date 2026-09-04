"""统一资源目录与 ACG 冻结 Agent 绑定的运行时测试。"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

from components.mission_manager.store import WorkflowRegistry
from components.executor.graph import ACGSuperstepError
from components.resource.service import ResourceService
from contracts.resource import DeploymentTier, ResourceEndpoint, ResourceHealthStatus, ResourceProfile, ResourceSnapshot, ResourceType
from components.scheduler.models import (
    SchedulerAllocationTimeout,
    SchedulerNoEligibleResource,
)
from adapters.resource_execution import ResourceExecutionError
from adapters.resource_execution import ResourceExecutionAdapter
from contracts.evolution import PolicyMutation, Trajectory
from contracts.workflow import WorkflowDefinition, WorkflowStepDefinition
from runtime.workflow_runtime import ExecutionRuntime
from service.agents import AgentRegistry
from service.agents.base import AgentOutput, AgentProfile, BaseAgent
from support.stores.memory_workflow_store import MemoryWorkflowStore


class _BoundAgent(BaseAgent):
    """记录调用身份，用于证明执行期没有重新做全局 Agent 选择。"""

    def __init__(
        self, profile: AgentProfile, calls: list[str], *, delay: float = 0.0
    ) -> None:
        super().__init__(profile)
        self.calls = calls
        self.delay = delay

    async def run(self, context):
        if self.delay:
            await asyncio.sleep(self.delay)
        self.calls.append(str(self.profile.agent_id))
        return AgentOutput(output={"agent": self.profile.agent_id})


def _runtime(calls: list[str]) -> tuple[ExecutionRuntime, AgentRegistry]:
    """建立一个按 capability 解析 Agent 的最小 ACG Runtime。"""
    agents = AgentRegistry()
    agents.register(_BoundAgent(AgentProfile(
        agentId="agent-primary", agentName="primary", domain="general",
        capabilities=["analysis"], bindingPriority=1,
    ), calls))
    workflows = WorkflowRegistry()
    workflows.register(WorkflowDefinition(
        workflowId="resource-run", name="resource", domain="general", runtimeEngine="acg",
        steps=[WorkflowStepDefinition(stepId="analyse", name="analyse", agentName="", capability="analysis")],
    ))
    return ExecutionRuntime(
        agent_registry=agents,
        workflow_registry=workflows,
        workflow_store=MemoryWorkflowStore(),
    ), agents


def test_prepare_run_freezes_resource_bindings() -> None:
    """每个 ACG Step 必须在准备期固定对应的 agentId。"""
    runtime, _ = _runtime([])
    task = runtime.create_mission("resource", workflow_id="resource-run")

    _, run = runtime.prepare_run(task.mission_id)

    assert run.execution_state["resourceBindings"] == {"analyse": "agent-primary"}
    assert run.execution_state["bindingRequirements"] == {
        "analyse": {
                "requiredCapabilities": ["analysis"],
                "domain": "general",
                "resourceTypes": ["agent"],
                "allowedDeploymentTiers": [],
                "allowedResourceIds": ["agent-primary"],
            "excludedResourceIds": [],
            "dataZone": None,
            "ownerScope": None,
            "labels": {},
                "maxCost": None,
                "maxLatencyMs": None,
                "privacyLevel": "internal",
                "requiredModelIds": [],
                "minGpuMemoryMb": 0,
                "allowRemoteExecution": True,
            "preferences": {"resourceId": "agent-primary"},
            "policyMetadata": {
                    "source": "compiled-binding-manifest",
                    "stepId": "analyse",
                    "agentNodeIds": ["agent::analyse"],
                    "maxConcurrency": 1,
                    "compatibilitySource": False,
            },
        }
    }


def test_runtime_accepts_resource_execution_adapters_by_resource_id() -> None:
    adapter = object()
    runtime, _ = _runtime([])
    runtime_with_adapter = ExecutionRuntime(
        agent_registry=runtime.agent_registry,
        workflow_registry=runtime.workflow_registry,
        workflow_store=MemoryWorkflowStore(),
        resource_execution_adapters={"edge-01": adapter},
    )

    assert runtime_with_adapter.resource_execution_adapters == {"edge-01": adapter}


def test_prepare_run_can_freeze_a_registered_remote_execution_resource() -> None:
    agents = AgentRegistry()
    workflows = WorkflowRegistry()
    workflows.register(WorkflowDefinition(
        workflowId="remote-resource-run", name="remote", domain="general", runtimeEngine="acg",
        steps=[WorkflowStepDefinition(stepId="infer", name="infer", agentName="edge-worker", capability="analysis")],
    ))
    resources = ResourceService()
    resources.register(
        ResourceProfile(
            resourceId="edge-01",
            resourceType=ResourceType.WORKER,
            deploymentTier=DeploymentTier.EDGE,
            capabilities=["analysis"],
            executionEndpoint=ResourceEndpoint(protocol="http", address="http://edge-01:9000"),
        ),
        ResourceSnapshot(
            resourceId="edge-01", availableSlots=1, utilization=0.0,
            healthStatus=ResourceHealthStatus.UNKNOWN,
        ),
    )
    resources.heartbeat("edge-01", source="external")
    adapter = object()
    runtime = ExecutionRuntime(
        agent_registry=agents,
        workflow_registry=workflows,
        workflow_store=MemoryWorkflowStore(),
        resource_service=resources,
        resource_execution_adapters={"edge-01": adapter},
    )

    task = runtime.create_mission("remote", workflow_id="remote-resource-run")
    _, run = runtime.prepare_run(task.mission_id)

    assert run.execution_state["resourceBindings"] == {"infer": "edge-01"}


def test_runtime_lazily_builds_remote_adapter_from_registered_profile(monkeypatch) -> None:
    agents = AgentRegistry()
    resources = ResourceService()
    profile = ResourceProfile(
        resourceId="edge-01",
        resourceType=ResourceType.WORKER,
        deploymentTier=DeploymentTier.EDGE,
        capabilities=["analysis"],
        ownerScope="team-a",
        executionEndpoint=ResourceEndpoint(protocol="http", address="http://edge-01:9000"),
    )
    resources.register_remote(
        profile,
        ResourceSnapshot(resourceId="edge-01", availableSlots=1, utilization=0.0),
    )
    built: list[tuple[str, object]] = []

    class _Adapter:
        async def run(self, context):
            return AgentOutput(output={"result": "edge"})

    def factory(profile, *, credential_provider, **kwargs):
        built.append((profile.resource_id, credential_provider))
        return _Adapter()

    monkeypatch.setattr("runtime.workflow_runtime.build_resource_execution_adapter", factory)
    runtime = ExecutionRuntime(
        agent_registry=agents,
        workflow_registry=WorkflowRegistry(),
        workflow_store=MemoryWorkflowStore(),
        resource_service=resources,
    )

    adapter = runtime._resource_execution_adapter("edge-01")

    assert adapter is not None
    assert built == [("edge-01", resources)]
    assert runtime.resource_execution_adapters["edge-01"] is adapter


def test_acg_execution_uses_remote_adapter_after_remote_binding() -> None:
    class _RemoteAdapter:
        def __init__(self) -> None:
            self.calls = 0

        async def run(self, context):
            self.calls += 1
            return AgentOutput(output={"result": "edge"}, summary="remote complete")

    agents = AgentRegistry()
    workflows = WorkflowRegistry()
    workflows.register(WorkflowDefinition(
        workflowId="remote-execute-run", name="remote", domain="general", runtimeEngine="acg",
        steps=[WorkflowStepDefinition(stepId="infer", name="infer", agentName="edge-worker", capability="analysis")],
    ))
    resources = ResourceService()
    resources.register(
        ResourceProfile(
            resourceId="edge-01", resourceType=ResourceType.WORKER,
            deploymentTier=DeploymentTier.EDGE, capabilities=["analysis"],
            executionEndpoint=ResourceEndpoint(protocol="http", address="http://edge-01:9000"),
        ),
        ResourceSnapshot(resourceId="edge-01", availableSlots=1, utilization=0.0),
    )
    resources.heartbeat("edge-01", source="external")
    adapter = _RemoteAdapter()
    runtime = ExecutionRuntime(
        agent_registry=agents,
        workflow_registry=workflows,
        workflow_store=MemoryWorkflowStore(),
        resource_service=resources,
        resource_execution_adapters={"edge-01": adapter},
    )

    task = runtime.create_mission("remote", workflow_id="remote-execute-run")
    _, run = runtime.prepare_run(task.mission_id)
    completed = asyncio.run(runtime.execute_prepared_run(run.run_id))

    assert adapter.calls == 1
    assert completed.status.value == "completed"


def test_remote_failure_marks_edge_unhealthy_and_rebinds_to_cloud() -> None:
    class _FailingEdgeAdapter:
        async def run(self, context):
            raise ResourceExecutionError("REMOTE_EXECUTION_FAILED: edge down")

    class _CloudAdapter:
        def __init__(self) -> None:
            self.calls = 0

        async def run(self, context):
            self.calls += 1
            return AgentOutput(output={"result": "cloud"}, summary="cloud complete")

    agents = AgentRegistry()
    workflows = WorkflowRegistry()
    workflows.register(WorkflowDefinition(
        workflowId="remote-failover-run", name="remote", domain="general", runtimeEngine="acg",
        steps=[WorkflowStepDefinition(stepId="infer", name="infer", agentName="remote-worker", capability="analysis")],
    ))
    resources = ResourceService()
    for resource_id, tier in (("edge-01", DeploymentTier.EDGE), ("cloud-01", DeploymentTier.CLOUD)):
        resources.register(
            ResourceProfile(
                resourceId=resource_id, resourceType=ResourceType.WORKER,
                deploymentTier=tier, capabilities=["analysis"],
                executionEndpoint=ResourceEndpoint(protocol="http", address=f"http://{resource_id}:9000"),
            ),
            ResourceSnapshot(resourceId=resource_id, availableSlots=1, utilization=0.0),
        )
        resources.observe_remote(
            resource_id,
            available_slots=1,
            utilization=0.0,
            latency_ms=10 if tier is DeploymentTier.EDGE else 100,
        )
    cloud = _CloudAdapter()
    runtime = ExecutionRuntime(
        agent_registry=agents,
        workflow_registry=workflows,
        workflow_store=MemoryWorkflowStore(),
        resource_service=resources,
        resource_execution_adapters={
            "edge-01": _FailingEdgeAdapter(),
            "cloud-01": cloud,
        },
    )

    task = runtime.create_mission("remote", workflow_id="remote-failover-run")
    _, run = runtime.prepare_run(task.mission_id)
    completed = asyncio.run(runtime.execute_prepared_run(run.run_id))

    assert cloud.calls == 1
    assert completed.status.value == "completed"
    assert resources.health_monitor.health("edge-01").healthy is False
    assert completed.recovery_count == 1
    assert completed.execution_state["resourceFailoverHistory"][0]["resourceId"] == "edge-01"
    assert {item["binding"]["resourceId"] for item in completed.execution_state["schedulingDecisions"]} == {
        "edge-01", "cloud-01"
    }


def test_remote_failover_stops_after_all_bound_remote_resources_fail() -> None:
    class _FailingAdapter:
        async def run(self, context):
            raise ResourceExecutionError("REMOTE_EXECUTION_FAILED: unavailable")

    agents = AgentRegistry()
    workflows = WorkflowRegistry()
    workflows.register(WorkflowDefinition(
        workflowId="remote-failover-exhausted", name="remote", domain="general", runtimeEngine="acg",
        steps=[WorkflowStepDefinition(stepId="infer", name="infer", agentName="remote-worker", capability="analysis")],
    ))
    resources = ResourceService()
    for resource_id, tier, latency in (
        ("edge-01", DeploymentTier.EDGE, 10),
        ("cloud-01", DeploymentTier.CLOUD, 100),
    ):
        resources.register(
            ResourceProfile(
                resourceId=resource_id, resourceType=ResourceType.WORKER,
                deploymentTier=tier, capabilities=["analysis"],
                executionEndpoint=ResourceEndpoint(protocol="http", address=f"http://{resource_id}:9000"),
            ),
            ResourceSnapshot(resourceId=resource_id, availableSlots=1, utilization=0.0),
        )
        resources.observe_remote(
            resource_id, available_slots=1, utilization=0.0, latency_ms=latency
        )
    runtime = ExecutionRuntime(
        agent_registry=agents,
        workflow_registry=workflows,
        workflow_store=MemoryWorkflowStore(),
        resource_service=resources,
        resource_execution_adapters={
            "edge-01": _FailingAdapter(),
            "cloud-01": _FailingAdapter(),
        },
    )

    task = runtime.create_mission("remote", workflow_id="remote-failover-exhausted")
    _, run = runtime.prepare_run(task.mission_id)

    with pytest.raises(ACGSuperstepError) as caught:
        asyncio.run(asyncio.wait_for(
            runtime.execute_prepared_run(run.run_id), timeout=1.0
        ))

    assert isinstance(caught.value.cause, SchedulerNoEligibleResource)
    failed = runtime.workflow_store.get_run(run.run_id)
    assert failed.status.value == "failed"
    assert [item["resourceId"] for item in failed.execution_state["resourceFailoverHistory"]] == [
        "edge-01", "cloud-01"
    ]


def test_acg_execution_uses_frozen_agent_binding_after_registry_changes() -> None:
    """准备后新增更高优先级 Agent 不能改变已准备运行的执行绑定。"""
    calls: list[str] = []
    runtime, agents = _runtime(calls)
    task = runtime.create_mission("resource", workflow_id="resource-run")
    _, run = runtime.prepare_run(task.mission_id)
    agents.register(_BoundAgent(AgentProfile(
        agentId="agent-new", agentName="new", domain="general",
        capabilities=["analysis"], bindingPriority=99,
    ), calls))

    completed = asyncio.run(runtime.execute_prepared_run(run.run_id))

    assert calls == ["agent-primary"]
    assert completed.execution_state["schedulingDecisions"][0]["lease"]["status"] == "released"
    assert runtime.scheduler_service.coordinator.active_slots("agent-primary") == 0


def test_long_run_refreshes_local_agent_heartbeat_before_later_step() -> None:
    """A local Agent must not age out merely because an earlier node ran past the TTL."""

    calls: list[str] = []
    agents = AgentRegistry()
    agents.register(_BoundAgent(AgentProfile(
        agentId="agent-primary", agentName="primary", domain="general",
        capabilities=["analysis"], bindingPriority=1,
    ), calls, delay=0.03))
    workflows = WorkflowRegistry()
    workflows.register(WorkflowDefinition(
        workflowId="heartbeat-run", name="heartbeat", domain="general", runtimeEngine="acg",
        steps=[
            WorkflowStepDefinition(
                stepId="first", name="first", agentName="primary",
                capability="analysis", nextStepId="second",
            ),
            WorkflowStepDefinition(
                stepId="second", name="second", agentName="primary", capability="analysis",
            ),
        ],
    ))
    runtime = ExecutionRuntime(
        agent_registry=agents,
        workflow_registry=workflows,
        workflow_store=MemoryWorkflowStore(),
        resource_service=ResourceService(
            heartbeat_timeout=timedelta(milliseconds=10)
        ),
    )
    task = runtime.create_mission("heartbeat", workflow_id="heartbeat-run")
    _, run = runtime.prepare_run(task.mission_id)

    completed = asyncio.run(asyncio.wait_for(
        runtime.execute_prepared_run(run.run_id), timeout=1.0
    ))

    assert completed.status.value == "completed"
    assert calls == ["agent-primary", "agent-primary"]


def test_impossible_frozen_binding_fails_instead_of_polling_forever() -> None:
    runtime, _ = _runtime([])
    task = runtime.create_mission("resource", workflow_id="resource-run")
    _, run = runtime.prepare_run(task.mission_id)
    run.execution_state["bindingRequirements"]["analyse"]["requiredCapabilities"] = [
        "missing-capability"
    ]
    runtime.workflow_store.save_run(run)

    with pytest.raises(ACGSuperstepError) as caught:
        asyncio.run(asyncio.wait_for(
            runtime.execute_prepared_run(run.run_id), timeout=1.0
        ))

    assert isinstance(caught.value.cause, SchedulerNoEligibleResource)
    failed = runtime.workflow_store.get_run(run.run_id)
    assert failed.execution_state["failureEvents"][-1]["reasonCode"] == "NO_ELIGIBLE_RESOURCE"


def test_capacity_queue_has_a_bounded_failure_outcome() -> None:
    runtime, _ = _runtime([])
    runtime.scheduler_wait_timeout = 0.02
    task = runtime.create_mission("resource", workflow_id="resource-run")
    _, run = runtime.prepare_run(task.mission_id)
    held = runtime.scheduler_service.coordinator.acquire(
        lease_id="lease-held",
        resource_id="agent-primary",
        capacity=1,
        run_id="other-run",
        step_id="other-step",
        attempt_id="other-attempt",
        ttl=timedelta(minutes=1),
    )
    assert held is not None

    with pytest.raises(ACGSuperstepError) as caught:
        asyncio.run(asyncio.wait_for(
            runtime.execute_prepared_run(run.run_id), timeout=1.0
        ))

    assert isinstance(caught.value.cause, SchedulerAllocationTimeout)
    failed = runtime.workflow_store.get_run(run.run_id)
    assert (
        failed.execution_state["failureEvents"][-1]["reasonCode"]
        == "SCHEDULER_CAPACITY_TIMEOUT"
    )


def test_approved_evolution_version_only_changes_future_general_runs() -> None:
    runtime, _ = _runtime([])
    old_task = runtime.create_mission("old", workflow_id="resource-run")
    _, old_run = runtime.prepare_run(old_task.mission_id)
    proposal = runtime.evolution_service.propose(
        [
            Trajectory(
                trajectoryId=f"trajectory-{index}",
                task={"domain": "general"},
                outcome={"status": "completed"},
            )
            for index in range(3)
        ],
        PolicyMutation(mutationType="budget_adjustment", target="analysis", value=4096),
    )
    assert proposal is not None
    runtime.evolution_service.approve(proposal, approved_by="reviewer")
    new_task = runtime.create_mission("new", workflow_id="resource-run")
    _, new_run = runtime.prepare_run(new_task.mission_id)

    assert old_run.execution_state["evolutionPolicyVersion"] == 0
    assert new_run.execution_state["evolutionPolicyVersion"] == 1
    assert old_run.execution_state["evolutionPolicy"] == {}
    assert new_run.execution_state["evolutionPolicy"] != {}
