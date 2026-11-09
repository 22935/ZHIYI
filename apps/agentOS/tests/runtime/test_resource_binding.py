"""资源绑定执行链：需求冻结、READY 绑定、远程执行与故障切换。

Preparation 只持久化 ExecutionRequirement；具体绑定由 ResourceBinder 在
READY 时完成。远程 Runtime 通过带凭据登记 + 外部心跳参与调度，失败后
标记不健康并自动换绑，全部候选耗尽则以致命错误收场。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx

import pytest

from components.executor.graph import ACGSuperstepError
from components.mission_manager.store import WorkflowRegistry
from components.memory.store import MemoryStore
from components.resource.runtime.embedded_runtime import EMBEDDED_AGENTS_RUNTIME_ID
from components.resource.application.resource_plane import ResourcePlane
from components.scheduler.binder import ResourceBinder
from components.scheduler.models import (
    SchedulerAllocationTimeout,
    SchedulerNoEligibleResource,
)
from adapters.resource_execution import ResourceExecutionError
from adapters.resource_execution import HttpResourceExecutionAdapter
from contracts.evolution import PolicyMutation, Trajectory
from contracts.resource import (
    HealthStatus,
    Placement,
    ResourceEndpoint,
    RuntimeKind,
    RuntimeProfile,
    RuntimeSnapshot,
    TrustLevel,
)
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


def _runtime(calls: list[str], **overrides) -> tuple[ExecutionRuntime, AgentRegistry]:
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
    values = dict(
        agent_registry=agents,
        workflow_registry=workflows,
        workflow_store=MemoryWorkflowStore(),
        # 默认记忆库指向共享 SQLite 文件，会在每次图构建时全量重建向量索引；
        # 测试必须使用隔离存储，避免随历史运行累积而变慢。
        memory_store=MemoryStore(),
    )
    values.update(overrides)
    return ExecutionRuntime(**values), agents


def _register_remote(plane: ResourcePlane, runtime_id: str, *, capability: str = "analysis", placement: Placement = Placement.EDGE, latency_ms: float = 10.0) -> None:
    node = f"node:{placement.value}-{runtime_id}"
    plane.ensure_node(node, placement=placement, trust=TrustLevel.TRUSTED)
    plane.register_remote_runtime(
        RuntimeProfile(
            runtimeId=runtime_id,
            kind=RuntimeKind.EXECUTION_BACKEND,
            nodeId=node,
            placement=placement,
            capabilities=[capability],
            trust=TrustLevel.TRUSTED,
            endpoint=ResourceEndpoint(protocol="http", address=f"http://{runtime_id}:9000/execute"),
            ownerScope="scope-remote",
            capacity=1,
        ),
        RuntimeSnapshot(
            runtimeId=runtime_id,
            availableSlots=1,
            utilization=0.0,
            healthStatus=HealthStatus.UNKNOWN,
        ),
    )
    plane.observe_remote_runtime(
        runtime_id,
        available_slots=1,
        utilization=0.0,
        latency_ms=latency_ms,
        observation_sequence=1,
    )


def test_prepare_run_defers_concrete_resource_binding_to_binder(monkeypatch) -> None:
    """Preparation persists requirements; the binder creates bindings at READY."""
    runtime, _ = _runtime([])
    calls: list[str] = []
    prepare = runtime.runtime_binding_service.prepare

    def record_prepare(**kwargs):
        calls.append(kwargs["run"].run_id)
        return prepare(**kwargs)

    monkeypatch.setattr(runtime.runtime_binding_service, "prepare", record_prepare)
    task = runtime.create_mission("resource", workflow_id="resource-run")

    _, run = runtime.prepare_run(task.mission_id)

    assert calls == [run.run_id]
    assert run.execution_state["resourceBindings"] == {}
    requirement = run.execution_state["bindingRequirements"]["analyse"]
    assert requirement["requiredCapabilities"] == ["analysis"]
    assert requirement["runtimeKinds"] == ["execution_backend"]
    # 需求只声明能力与约束，不冻结允许清单与放置位置。
    assert requirement["allowedRuntimeIds"] == []
    assert requirement["allowedPlacements"] == []
    assert requirement["policyMetadata"]["source"] == "compiled-binding-manifest"
    assert requirement["policyMetadata"]["stepId"] == "analyse"
    assert requirement["routingHints"] == {}


def test_runtime_accepts_resource_execution_adapters_by_runtime_id() -> None:
    adapter = object()
    runtime, _ = _runtime([])
    runtime_with_adapter = ExecutionRuntime(
        agent_registry=runtime.agent_registry,
        workflow_registry=runtime.workflow_registry,
        workflow_store=MemoryWorkflowStore(),
        resource_execution_adapters={"edge-01": adapter},
    )

    assert runtime_with_adapter.resource_execution_adapters == {"edge-01": adapter}


def test_prepare_run_keeps_registered_remote_runtime_eligible_without_binding() -> None:
    plane = ResourcePlane()
    _register_remote(plane, "edge-01")
    agents = AgentRegistry()
    workflows = WorkflowRegistry()
    workflows.register(WorkflowDefinition(
        workflowId="remote-resource-run", name="remote", domain="general", runtimeEngine="acg",
        steps=[WorkflowStepDefinition(stepId="infer", name="infer", agentName="edge-worker", capability="analysis")],
    ))
    runtime = ExecutionRuntime(
        agent_registry=agents,
        workflow_registry=workflows,
        workflow_store=MemoryWorkflowStore(),
        memory_store=MemoryStore(),
        resource_plane=plane,
        resource_execution_adapters={"edge-01": object()},
    )

    task = runtime.create_mission("remote", workflow_id="remote-resource-run")
    _, run = runtime.prepare_run(task.mission_id)

    assert run.execution_state["resourceBindings"] == {}
    requirement = run.execution_state["bindingRequirements"]["infer"]
    assert requirement["requiredCapabilities"] == ["analysis"]
    assert requirement["allowedRuntimeIds"] == []


def test_runtime_lazily_builds_remote_adapter_from_registered_profile(monkeypatch) -> None:
    plane = ResourcePlane()
    _register_remote(plane, "edge-01")
    built: list[tuple[str, object]] = []

    class _Adapter:
        async def run(self, context):
            return AgentOutput(output={"result": "edge"})

    def factory(profile, *, credential_provider, **kwargs):
        built.append((profile.runtime_id, credential_provider))
        return _Adapter()

    monkeypatch.setattr("runtime.acg_execution.build_resource_execution_adapter", factory)
    runtime, _ = _runtime([], resource_plane=plane)

    adapter = runtime.acg_execution_service._remote_runtime_adapter("edge-01")

    assert adapter is not None
    assert built == [("edge-01", plane)]
    assert runtime.resource_execution_adapters["edge-01"] is adapter


def test_remote_runtime_without_endpoint_has_no_adapter() -> None:
    runtime, _ = _runtime([])
    plane = runtime.resource_plane
    plane.ensure_node("node:device:local", placement=Placement.DEVICE)
    plane.register_runtime(RuntimeProfile(
        runtimeId="runtime:in-process",
        nodeId="node:device:local",
        placement=Placement.DEVICE,
        capabilities=["analysis"],
    ))

    assert runtime.acg_execution_service._remote_runtime_adapter("runtime:in-process") is None


def test_acg_execution_uses_remote_adapter_after_remote_binding() -> None:
    class _RemoteAdapter:
        def __init__(self) -> None:
            self.calls = 0

        async def run(self, context):
            self.calls += 1
            return AgentOutput(output={"result": "edge"}, summary="remote complete")

    plane = ResourcePlane()
    _register_remote(plane, "edge-01")
    adapter = _RemoteAdapter()
    agents = AgentRegistry()
    workflows = WorkflowRegistry()
    workflows.register(WorkflowDefinition(
        workflowId="remote-execute-run", name="remote", domain="general", runtimeEngine="acg",
        steps=[WorkflowStepDefinition(stepId="infer", name="infer", agentName="edge-worker", capability="analysis")],
    ))
    runtime = ExecutionRuntime(
        agent_registry=agents,
        workflow_registry=workflows,
        workflow_store=MemoryWorkflowStore(),
        memory_store=MemoryStore(),
        resource_plane=plane,
        resource_execution_adapters={"edge-01": adapter},
    )

    task = runtime.create_mission("remote", workflow_id="remote-execute-run")
    _, run = runtime.prepare_run(task.mission_id)
    completed = asyncio.run(runtime.execute_prepared_run(run.run_id))

    assert adapter.calls == 1
    assert completed.status.value == "completed"
    assert completed.execution_state["executionBindings"]["infer"]["resourceId"] == "edge-01"
    assert completed.execution_state["executionBindings"]["infer"]["runtimeKind"] == "execution_backend"
    assert completed.execution_state["resourceBindings"]["infer"] == "edge-01"


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

    plane = ResourcePlane()
    _register_remote(plane, "edge-01", latency_ms=10.0)
    _register_remote(plane, "cloud-01", placement=Placement.CLOUD, latency_ms=100.0)
    cloud = _CloudAdapter()
    agents = AgentRegistry()
    workflows = WorkflowRegistry()
    workflows.register(WorkflowDefinition(
        workflowId="remote-failover-run", name="remote", domain="general", runtimeEngine="acg",
        steps=[WorkflowStepDefinition(stepId="infer", name="infer", agentName="remote-worker", capability="analysis")],
    ))
    runtime = ExecutionRuntime(
        agent_registry=agents,
        workflow_registry=workflows,
        workflow_store=MemoryWorkflowStore(),
        memory_store=MemoryStore(),
        resource_plane=plane,
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
    assert plane.health_monitor.health("edge-01").healthy is False
    assert completed.recovery_count == 1
    assert completed.execution_state["resourceFailoverHistory"][0]["resourceId"] == "edge-01"
    assert {item["binding"]["resourceId"] for item in completed.execution_state["schedulingDecisions"]} == {
        "edge-01", "cloud-01"
    }


@pytest.mark.parametrize("response_kind", ["accepted", "running", "read_timeout", "write_timeout", "server_error", "wrapped_unknown", "state_running", "success_false"])
def test_unknown_http_execution_retains_lease_without_second_execution(response_kind):
    calls = []
    class Credentials:
        def current_signing_credential(self, resource_id):
            return "credential", "secret"
    async def handler(request):
        calls.append(request.url.host)
        if response_kind == "wrapped_unknown":
            try:
                raise ResourceExecutionError("outcome lost", outcome_unknown=True)
            except ResourceExecutionError:
                raise ResourceExecutionError("outer wrapper without explicit cause")
        if response_kind == "read_timeout":
            raise httpx.ReadTimeout("reply lost after execution", request=request)
        if response_kind == "write_timeout":
            raise httpx.WriteTimeout("partial request delivery", request=request)
        if response_kind == "server_error":
            return httpx.Response(503, json={"error": "result lost"})
        if response_kind == "state_running":
            return httpx.Response(200, json={"state": "RUNNING", "output": {}})
        if response_kind == "success_false":
            return httpx.Response(200, json={"success": False, "output": {}})
        return httpx.Response(202 if response_kind == "accepted" else 200, json={"status": "RUNNING"})
    plane = ResourcePlane()
    _register_remote(plane, "edge-01", latency_ms=10)
    _register_remote(plane, "cloud-01", placement=Placement.CLOUD, latency_ms=100)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapters = {rid: HttpResourceExecutionAdapter(resource_id=rid, address=f"http://{rid}/execute",
                credential_provider=Credentials(), client=client) for rid in ("edge-01", "cloud-01")}
            runtime, _ = _runtime([], resource_plane=plane, resource_execution_adapters=adapters)
            task = runtime.create_mission("unknown", workflow_id="resource-run")
            _, run = runtime.prepare_run(task.mission_id)
            # The planning failure observer must not turn UNKNOWN into a replan.
            run.execution_state["planningLoop"] = {}
            runtime.workflow_store.save_run(run)
            async def observe(*args):
                pytest.fail("UNKNOWN must await reconciliation, not automatic planning")
            runtime.acg_execution_service._observe_boundary = observe
            with pytest.raises(ACGSuperstepError) as caught:
                await runtime.execute_prepared_run(run.run_id)
            assert caught.value.outcome_unknown is True
            saved = runtime.workflow_store.get_run(run.run_id)
            assert calls == ["edge-01"]
            assert saved.recovery_count == 0
            assert saved.execution_state["recoveryOutcome"]["action"] == "review"
            assert saved.execution_state["recoveryOutcome"]["status"] == "required"
            assert saved.execution_state["recoveryOutcome"]["reasonCode"] == "REMOTE_EXECUTION_OUTCOME_UNKNOWN"
            assert not saved.execution_state.get("resourceFailoverHistory")
            assert saved.execution_state["resourceBindings"]["analyse"] == "edge-01"
            assert saved.execution_state["executionBindings"]["analyse"]["resourceId"] == "edge-01"
            settlement, = saved.execution_state["taskSettlement"].values()
            assert settlement["outcome"] == "unknown"
            assert settlement["leaseState"] == "retained_unknown"
            assert plane.runtime("edge-01").enabled is False
            assert plane.health_monitor.health("edge-01").healthy is False
            assert runtime.resource_binder.coordinator.active_slots("edge-01") == 1
            assert runtime.resource_binder.coordinator.active_slots("cloud-01") == 0
            assert saved.completed_step_ids == []
            assert not any(event.event_type.value == "step_succeeded" for event in saved.trace)
            assert saved.output == {}
    asyncio.run(scenario())


def test_remote_failover_stops_after_all_bound_remote_runtimes_fail() -> None:
    class _FailingAdapter:
        async def run(self, context):
            raise ResourceExecutionError("REMOTE_EXECUTION_FAILED: unavailable")

    plane = ResourcePlane()
    _register_remote(plane, "edge-01", latency_ms=10.0)
    _register_remote(plane, "cloud-01", placement=Placement.CLOUD, latency_ms=100.0)
    agents = AgentRegistry()
    workflows = WorkflowRegistry()
    workflows.register(WorkflowDefinition(
        workflowId="remote-failover-exhausted", name="remote", domain="general", runtimeEngine="acg",
        steps=[WorkflowStepDefinition(stepId="infer", name="infer", agentName="remote-worker", capability="analysis")],
    ))
    runtime = ExecutionRuntime(
        agent_registry=agents,
        workflow_registry=workflows,
        workflow_store=MemoryWorkflowStore(),
        memory_store=MemoryStore(),
        resource_plane=plane,
        resource_execution_adapters={
            "edge-01": _FailingAdapter(),
            "cloud-01": _FailingAdapter(),
        },
    )

    task = runtime.create_mission("remote", workflow_id="remote-failover-exhausted")
    _, run = runtime.prepare_run(task.mission_id)

    with pytest.raises(ACGSuperstepError) as caught:
        asyncio.run(asyncio.wait_for(
            runtime.execute_prepared_run(run.run_id), timeout=2.0
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
    assert runtime.resource_binder.coordinator.active_slots(EMBEDDED_AGENTS_RUNTIME_ID) == 0
    assert completed.execution_state["logicalAgents"]["analyse"] == "agent-primary"


def test_long_run_refreshes_embedded_runtime_heartbeat_before_later_step() -> None:
    """嵌入式后端不能因前一步耗时超过健康 TTL 而被判不可用。"""
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
    runtime, _ = _runtime(
        calls,
        agent_registry=agents,
        workflow_registry=workflows,
        resource_plane=ResourcePlane(heartbeat_timeout=timedelta(milliseconds=10)),
    )

    task = runtime.create_mission("heartbeat", workflow_id="heartbeat-run")
    _, run = runtime.prepare_run(task.mission_id)

    completed = asyncio.run(asyncio.wait_for(
        runtime.execute_prepared_run(run.run_id), timeout=2.0
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
            runtime.execute_prepared_run(run.run_id), timeout=2.0
        ))

    assert isinstance(caught.value.cause, SchedulerNoEligibleResource)
    failed = runtime.workflow_store.get_run(run.run_id)
    assert failed.execution_state["failureEvents"][-1]["reasonCode"] == "NO_ELIGIBLE_RESOURCE"


def test_capacity_queue_has_a_bounded_failure_outcome() -> None:
    runtime, _ = _runtime([])
    runtime.scheduler_wait_timeout = 0.02
    task = runtime.create_mission("resource", workflow_id="resource-run")
    _, run = runtime.prepare_run(task.mission_id)
    held = runtime.resource_binder.coordinator.acquire(
        lease_id="lease-held",
        resource_id=EMBEDDED_AGENTS_RUNTIME_ID,
        capacity=1,
        run_id="other-run",
        step_id="other-step",
        attempt_id="other-attempt",
        slot_count=1,
        ttl=timedelta(minutes=1),
        now=datetime.now(timezone.utc),
    )
    assert held is not None

    with pytest.raises(ACGSuperstepError) as caught:
        asyncio.run(asyncio.wait_for(
            runtime.execute_prepared_run(run.run_id), timeout=2.0
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
