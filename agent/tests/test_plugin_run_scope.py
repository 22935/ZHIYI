import asyncio
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentos.agents import AgentOutput, AgentProfile, AgentRegistry, BaseAgent
from agentos.agents.registry import AgentNotFound
from agentos.core.acg import ACGBlueprint, StepNode
from agentos.core.models.types import WorkflowDefinition, WorkflowStepDefinition
from agentos.core.native import register_native_runtime
from agentos.core.plugin_scope import PluginScopeError
from agentos.core.runtime import WorkflowRuntime
from agentos.core.workflow.registry import WorkflowRegistry
from agentos.stores.memory_workflow_store import MemoryWorkflowStore
from agentos.packs.registry import load_pack_manifest
from app.api.agentos_core import create_router
from app.execution.model_runtime import GatewayStructuredGenerationRuntime
from packs.legal import register_pack as register_legal_pack


def _runtime() -> WorkflowRuntime:
    agents = AgentRegistry()
    workflows = WorkflowRegistry()
    register_native_runtime(agent_registry=agents, workflow_registry=workflows)
    runtime = WorkflowRuntime(agent_registry=agents, workflow_registry=workflows)
    runtime.set_model_runtime(GatewayStructuredGenerationRuntime())
    register_legal_pack(
        runtime.agent_registry,
        runtime.workflow_registry,
        runtime.capability_catalog,
    )
    return runtime


def _task(runtime, *, legal: bool, enabled):
    return runtime.create_task(
        title="Contract review" if legal else "Native plan",
        domain="legal" if legal else "general",
        intent="contract_review" if legal else "general",
        enabled_plugin_ids=enabled,
        input=(
            {"contractText": "A simple agreement", "thinkingMode": "disabled"}
            if legal
            else {
                "userIntent": "Create an implementation plan",
                "planningMode": "dynamic",
                "planningDiversity": "balanced",
                "planningSeed": 284731,
                "thinkingMode": "disabled",
            }
        ),
    )


def test_native_only_and_legal_runs_are_isolated_in_one_runtime():
    async def run_test():
        runtime = _runtime()
        global_agents_before = tuple(runtime.agent_registry.all())
        global_capabilities_before = tuple(runtime.capability_catalog.available())
        native_task = _task(runtime, legal=False, enabled=[])
        legal_task = _task(runtime, legal=True, enabled=["kinlin.legal"])
        _, native_prepared = runtime.prepare_run(native_task.task_id, review_mode="auto")
        _, legal_prepared = runtime.prepare_run(legal_task.task_id, review_mode="auto")

        native_run, legal_run = await asyncio.gather(
            runtime.execute_prepared_run(native_prepared.run_id),
            runtime.execute_prepared_run(legal_prepared.run_id),
        )

        assert native_run.status.value == "completed"
        assert native_run.enabled_plugin_ids == []
        assert native_run.plugin_snapshot == []
        assert native_run.planning_diversity == "balanced"
        assert native_run.planning_seed == 284731
        assert all(
            (node.current_binding or {}).get("source") == "native"
            for node in native_run.runtime_graph.nodes
            if node.node_type.value == "step"
        )
        assert legal_run.status.value == "completed"
        assert legal_run.enabled_plugin_ids == ["kinlin.legal"]
        assert legal_run.plugin_snapshot[0].plugin_id == "kinlin.legal"
        assert legal_run.workflow_id == "legal_contract_review_v1"
        assert all(
            (node.current_binding or {}).get("pluginId") == "kinlin.legal"
            for node in legal_run.runtime_graph.nodes
            if node.node_type.value == "step"
        )
        assert tuple(runtime.agent_registry.all()) == global_agents_before
        assert tuple(runtime.capability_catalog.available()) == global_capabilities_before

    asyncio.run(run_test())


def test_explicit_legal_workflow_is_rejected_from_native_only_scope():
    runtime = _runtime()

    with pytest.raises(KeyError, match="WORKFLOW_NOT_AVAILABLE_IN_PLUGIN_SCOPE"):
        runtime.create_task(
            title="Contract review",
            domain="legal",
            intent="contract_review",
            workflow_id="legal_contract_review_v1",
            enabled_plugin_ids=[],
        )


def test_async_api_rejects_unknown_plugin_with_structured_error():
    app = FastAPI()
    app.include_router(create_router(_runtime()), prefix="/ai")

    response = TestClient(app).post(
        "/ai/core/workflows/start-async",
        json={
            "title": "Unknown plugin",
            "domain": "general",
            "intent": "general",
            "enabledPluginIds": ["missing.plugin"],
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "PLUGIN_NOT_AVAILABLE",
        "message": "missing.plugin",
    }


def test_installed_plugins_api_returns_safe_legal_projection():
    runtime = _runtime()
    runtime.plugin_manifests = (
        load_pack_manifest(
            Path(__file__).parents[1] / "packs" / "legal" / "manifest.yaml"
        ),
    )
    app = FastAPI()
    app.include_router(create_router(runtime), prefix="/ai")

    response = TestClient(app).get("/ai/core/plugins")

    assert response.status_code == 200
    assert response.json() == [{
        "pluginId": "kinlin.legal",
        "version": "0.1.0",
        "displayName": "法律能力包",
        "description": "合同审查、证据匹配、风险分析与法律报告能力。",
        "available": True,
        "capabilityCount": 7,
        "agentCount": 14,
        "workflowCount": 2,
        "uiExtensionId": "kinlin.legal",
    }]


def test_legacy_null_resolves_legal_workflow_owner_and_freezes_checkpoint_scope():
    async def run_test():
        runtime = _runtime()
        task = _task(runtime, legal=True, enabled=None)
        _, prepared = runtime.prepare_run(task.task_id, review_mode="auto")
        run = await runtime.execute_prepared_run(prepared.run_id)

        assert run.enabled_plugin_ids == ["kinlin.legal"]
        assert run.execution_scope.enabled_plugin_ids == ("kinlin.legal",)
        assert run.execution_state["pluginScopeResolution"] == "legacy_compatibility"
        assert run.checkpoints
        snapshot = run.checkpoints[-1].state_snapshot
        assert snapshot["executionScope"] == run.execution_scope.model_dump(
            by_alias=True, mode="json"
        )
        assert snapshot["executionScope"]["pluginSnapshots"] == [
            item.model_dump(by_alias=True, mode="json")
            for item in run.plugin_snapshot
        ]

    asyncio.run(run_test())


def test_request_mutation_after_prepare_does_not_change_run_scope():
    runtime = _runtime()
    requested = ["kinlin.legal"]
    task = _task(runtime, legal=True, enabled=requested)
    _, run = runtime.prepare_run(task.task_id, review_mode="auto")
    requested.clear()
    task.enabled_plugin_ids.clear()

    persisted = runtime.get_status(run.run_id)
    assert persisted.enabled_plugin_ids == ["kinlin.legal"]
    assert persisted.execution_scope.enabled_plugin_ids == ("kinlin.legal",)


def test_alternate_binding_cannot_cross_native_only_scope():
    calls = []

    class _Primary(BaseAgent):
        def __init__(self):
            super().__init__(
                AgentProfile(
                    agentName="scope_primary",
                    domain="general",
                    capabilities=["scope_work"],
                )
            )

        async def run(self, context):
            calls.append("primary")
            raise AgentNotFound("primary unavailable")

    class _PluginAlternate(BaseAgent):
        def __init__(self):
            super().__init__(
                AgentProfile(
                    agentName="scope_plugin_alternate",
                    domain="general",
                    capabilities=["scope_work"],
                    source="plugin",
                    pluginId="sample.alternate",
                    pluginVersion="1.0.0",
                    contributionId="scope_plugin_alternate",
                )
            )

        async def run(self, context):
            calls.append("plugin")
            return AgentOutput(output={"ok": True})

    async def run_test():
        agents, workflows = AgentRegistry(), WorkflowRegistry()
        agents.register(_Primary())
        agents.register(_PluginAlternate())
        workflows.register(
            WorkflowDefinition(
                workflowId="scope_binding_workflow",
                name="Scope binding",
                domain="general",
                intent="scope_binding",
                runtimeEngine="acg",
                steps=[
                    WorkflowStepDefinition(
                        stepId="work",
                        name="Work",
                        agentName="scope_primary",
                        capability="scope_work",
                        maxRetries=1,
                    )
                ],
            )
        )
        runtime = WorkflowRuntime(
            agent_registry=agents,
            workflow_registry=workflows,
        )
        blueprint = ACGBlueprint(
            graphId="scope_binding_graph",
            nodes=[
                StepNode(
                    nodeId="work",
                    name="Work",
                    agentName="scope_primary",
                    capability="scope_work",
                    retryLimit=1,
                )
            ],
            edges=[],
        )
        task = runtime.create_task(
            title="Scoped binding",
            domain="general",
            intent="scope_binding",
            workflow_id="scope_binding_workflow",
            enabled_plugin_ids=[],
            input={"acgBlueprint": blueprint.model_dump(by_alias=True, mode="json")},
        )
        run = await runtime.start(
            task.task_id,
            workflow_id="scope_binding_workflow",
        )

        assert run.status.value == "failed"
        assert calls == ["primary"]
        assert run.runtime_graph.graph_version == 1
        assert run.runtime_graph.get_node("work").binding_switch_count == 0
        assert run.runtime_graph.runtime_events[0].status.value == "REJECTED"

    asyncio.run(run_test())


def test_restored_run_does_not_expand_scope_when_original_plugin_is_unavailable():
    async def run_test():
        store = MemoryWorkflowStore()
        original = _runtime()
        original.workflow_store = store
        original.task_manager.workflow_store = store
        original.runtime_controller.workflow_store = store
        task = _task(original, legal=True, enabled=["kinlin.legal"])
        _, prepared = original.prepare_run(task.task_id, review_mode="auto")

        agents, workflows = AgentRegistry(), WorkflowRegistry()
        register_native_runtime(agent_registry=agents, workflow_registry=workflows)
        restored = WorkflowRuntime(
            agent_registry=agents,
            workflow_registry=workflows,
            workflow_store=store,
        )

        with pytest.raises(PluginScopeError, match="PLUGIN_SNAPSHOT_UNAVAILABLE"):
            await restored.execute_prepared_run(prepared.run_id)
        failed = store.get_run(prepared.run_id)
        assert failed.status.value == "failed"
        assert failed.enabled_plugin_ids == ["kinlin.legal"]
        assert failed.execution_scope == prepared.execution_scope

    asyncio.run(run_test())
