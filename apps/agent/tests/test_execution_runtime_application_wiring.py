from __future__ import annotations

from pathlib import Path

from components.auditor.decision_store import SQLiteDecisionStore
from components.communicator.provenance_store import SQLiteProvenanceStore
from components.executor.value_store import SQLiteExecutionValueStore
from components.evolution.store import SQLiteEvolutionStore
from components.memory.store import SQLiteMemoryStore
from components.content import SQLiteContentManifestStore
from components.resource.runtime.embedded_runtime import EMBEDDED_AGENTS_RUNTIME_ID
from components.resource.infrastructure.runtime_store import SQLiteResourceStore
from components.resource.infrastructure.health_store import SQLiteResourceHealthStore
from components.resource.infrastructure.node_store import SQLiteNodeStore
from components.recovery.checkpoint import ACGCheckpointStore
from components.resource.scheduler.binder import ResourceBinder
from components.resource.scheduler.leases import RedisLeaseCoordinator
from adapters.guarded_model import GuardedModelRuntime
from adapters.model_compatibility import ModelCompatibilityRegistry
from runtime import ExecutionRuntime
from contracts.resource import NodeProfile, NodeSnapshot, Placement
from support.stores.sqlite_workflow_store import SQLiteWorkflowStore

from app.execution.wiring import (
    GatewayIntentLLM,
    RegisteredPlannerLLM,
    bind_registered_planner_llm,
    build_default_runtime,
    build_model_setup,
    close_runtime,
)
from app.llm.gateway import LLMGateway, set_llm_gateway_for_tests
from app.tools.formal_workspace import FormalWorkspaceTools


class _InjectedToolRuntime:
    def scoped(self, allowed_tools):
        return self


class _InjectedModelRuntime:
    pass


class _InjectedIntentLLM:
    pass


class _UnavailablePlannerProvider:
    provider_name = "unavailable"
    model = ""

    def generate_text(self, prompt, **kwargs):
        raise AssertionError("unavailable planner provider should not be called")

    def generate_json(self, prompt, schema, **kwargs):
        raise AssertionError("unavailable planner provider should not be called")


class _PlannerRuntimeWithoutConfiguredModel:
    def __init__(self) -> None:
        self._intent_llm = GatewayIntentLLM()
        self.model_registry = ModelCompatibilityRegistry()
        self.bound = False

    def set_intent_llm(self, intent_llm) -> None:
        self.bound = True
        self._intent_llm = intent_llm


class _InjectedRedis:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _environment(root: Path) -> dict[str, str]:
    return {
        "AGENTOS_WORKFLOW_DB_PATH": str(root / "workflows.sqlite3"),
        "AGENTOS_LANGGRAPH_CHECKPOINT_DB": str(root / "langgraph_checkpoints.sqlite3"),
        "AGENTOS_EXECUTION_VALUE_DB": str(root / "execution_values.sqlite3"),
        "AGENTOS_CONTENT_MANIFEST_DB": str(root / "content_manifests.sqlite3"),
        "AGENTOS_EXECUTION_MEMORY_DB": str(root / "execution_memory.sqlite3"),
        "AGENTOS_PROVENANCE_DB": str(root / "provenance.sqlite3"),
        "AGENTOS_AUDIT_DB": str(root / "audit_decisions.sqlite3"),
        "AGENTOS_RESOURCE_DB": str(root / "resources.sqlite3"),
        "AGENTOS_NODE_DB": str(root / "nodes.sqlite3"),
        "AGENTOS_AGENT_DB": str(root / "agents.sqlite3"),
        "AGENTOS_RESOURCE_HEALTH_DB": str(root / "resource_health.sqlite3"),
        "AGENTOS_EVOLUTION_DB": str(root / "evolution.sqlite3"),
    }


def test_application_builds_the_single_execution_runtime_with_authoritative_resource_store(tmp_path: Path) -> None:
    tools = _InjectedToolRuntime()
    model = _InjectedModelRuntime()
    intent = _InjectedIntentLLM()
    runtime = build_default_runtime(
        environment=_environment(tmp_path),
        tool_runtime=tools,
        model_runtime=model,
        intent_llm=intent,
    )
    try:
        assert type(runtime) is ExecutionRuntime
        assert isinstance(runtime.workflow_store, SQLiteWorkflowStore)
        assert isinstance(runtime.checkpoint_store, ACGCheckpointStore)
        assert isinstance(runtime.execution_value_store, SQLiteExecutionValueStore)
        assert isinstance(runtime.content_manifest_store, SQLiteContentManifestStore)
        assert isinstance(runtime.memory_store, SQLiteMemoryStore)
        assert isinstance(runtime.provenance_store, SQLiteProvenanceStore)
        assert isinstance(runtime.decision_store, SQLiteDecisionStore)
        assert isinstance(runtime.resource_plane.node_store, SQLiteNodeStore)
        assert isinstance(runtime.resource_binder, ResourceBinder)
        assert runtime.resource_binder.plane is runtime.resource_plane
        assert isinstance(runtime.resource_plane.store, SQLiteResourceStore)
        from components.resource.infrastructure.audit_store import SQLiteResourceAuditStore
        assert isinstance(runtime.resource_plane.audit_store, SQLiteResourceAuditStore)
        assert {item.catalog_id for item in runtime.marketplace_service.list_catalog()} >= {"tool.pdf-parser", "tool.file-converter"}
        assert runtime.marketplace_service._monitor.is_alive()
        assert isinstance(runtime.resource_plane.health_monitor.store, SQLiteResourceHealthStore)
        assert isinstance(runtime.evolution_service.store, SQLiteEvolutionStore)
        # hands 唯一后端：装配恒以 FormalWorkspaceTools 包装注入的工具运行时。
        assert isinstance(runtime.tool_runtime, FormalWorkspaceTools)
        assert runtime.tool_runtime.fallback is tools
        assert isinstance(runtime._model_runtime, GuardedModelRuntime)
        assert runtime._model_runtime.delegate is model
        assert runtime._intent_llm is intent
        assert runtime.require_planner_identity is True
        assert runtime.identity_lifecycle is not None
        assert runtime.agent_registry.all()
        # 逻辑 Agent 注册表整体投影为一个嵌入式执行后端，而非逐个登记为资源。
        embedded = runtime.resource_plane.runtime(EMBEDDED_AGENTS_RUNTIME_ID)
        registry_capabilities = {
            capability
            for agent in runtime.agent_registry.all()
            for capability in agent.profile.capabilities
        }
        assert set(embedded.capabilities).issuperset(registry_capabilities)
        assert runtime.workflow_registry.all()
        assert {manifest.pack_id for manifest in runtime.plugin_manifests} == {
            "workspace",
        }
    finally:
        close_runtime(runtime)


def test_application_node_store_persists_remote_credentials(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    runtime = build_default_runtime(
        environment=environment,
        tool_runtime=_InjectedToolRuntime(),
        model_runtime=_InjectedModelRuntime(),
        intent_llm=_InjectedIntentLLM(),
    )
    try:
        issued = runtime.resource_plane.register_remote_node(
            NodeProfile(
                nodeId="wired-node",
                placement=Placement.EDGE,
                ownerScope="tenant-a",
            ),
            NodeSnapshot(nodeId="wired-node"),
        )
    finally:
        close_runtime(runtime)

    reopened = SQLiteNodeStore(environment["AGENTOS_NODE_DB"])
    try:
        assert reopened.get_credential("wired-node").credential_id == issued.credential_id
    finally:
        reopened.close()


def test_production_runtime_requires_resource_credential_master_key(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    environment["ENVIRONMENT"] = "production"

    try:
        build_default_runtime(
            environment=environment,
            tool_runtime=_InjectedToolRuntime(),
            model_runtime=_InjectedModelRuntime(),
            intent_llm=_InjectedIntentLLM(),
        )
    except RuntimeError as error:
        assert str(error) == "AGENTOS_RESOURCE_CREDENTIAL_KEY is required in production"
    else:
        raise AssertionError("production runtime accepted a missing resource credential key")


def test_production_python_does_not_import_the_removed_agentos_package() -> None:
    root = Path(__file__).resolve().parents[1]
    offenders = []
    for source in [*(root / "app").rglob("*.py"), *(root / "packs").rglob("*.py")]:
        text = source.read_text(encoding="utf-8")
        if "from agentos" in text or "import agentos" in text or "agentos.core" in text:
            offenders.append(str(source.relative_to(root)))
    assert offenders == []


def test_application_wires_an_injected_redis_lease_coordinator(tmp_path: Path) -> None:
    client = _InjectedRedis()
    runtime = build_default_runtime(
        environment=_environment(tmp_path),
        tool_runtime=_InjectedToolRuntime(),
        model_runtime=_InjectedModelRuntime(),
        intent_llm=_InjectedIntentLLM(),
        coordination_client=client,
    )
    try:
        assert isinstance(runtime.resource_binder.coordinator, RedisLeaseCoordinator)
        assert runtime.resource_binder.coordinator.client is client
    finally:
        close_runtime(runtime)
    assert client.closed is True


def test_model_setup_reuses_the_single_workflow_runtime_registry(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    runtime = build_default_runtime(
        environment=environment,
        tool_runtime=_InjectedToolRuntime(),
        model_runtime=_InjectedModelRuntime(),
        intent_llm=_InjectedIntentLLM(),
    )
    try:
        setup = build_model_setup(runtime, environment=environment)
        assert setup.model_registry is runtime.model_registry
    finally:
        close_runtime(runtime)


def test_planner_registry_binding_skips_unconfigured_gateway_model() -> None:
    runtime = _PlannerRuntimeWithoutConfiguredModel()
    set_llm_gateway_for_tests(LLMGateway(provider=_UnavailablePlannerProvider()))
    try:
        assert bind_registered_planner_llm(runtime) is False
        assert runtime.bound is False
        assert isinstance(runtime._intent_llm, GatewayIntentLLM)
    finally:
        set_llm_gateway_for_tests(None)


def test_copilot_model_binding_is_isolated_from_runtime_default():
    from types import SimpleNamespace
    class Registry:
        def resolve(self, provider, model):
            assert (provider, model) == ("test", "other")
        def list_models(self):
            return ({"id": "test/other", "provider": "test", "model": "other"},)
    runtime = SimpleNamespace(default_model_binding={"provider": "test", "model": "default"}, model_registry=Registry())
    default = RegisteredPlannerLLM(runtime)
    selected = default.for_model("test", "other")
    assert selected.model == "other" and selected._model_runtime.model == "other"
    assert default.model == runtime.default_model_binding["model"] == "default"
    assert selected.copilot_models()[0]["id"] == "test/other"
