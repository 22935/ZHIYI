"""Composition root for the single AgentOS execution runtime."""

from __future__ import annotations

import os
import asyncio
import json
import logging
from datetime import timedelta
from pathlib import Path
from threading import Thread
from typing import Any, Mapping

from adapters.model.native import register_native_runtime
from adapters.local_runtime import LocalRuntimeClient
from components.auditor.decision_store import SQLiteDecisionStore
from components.communicator.provenance_store import SQLiteProvenanceStore
from components.executor.value_store import SQLiteExecutionValueStore
from components.evolution.service import EvolutionService
from components.evolution.store import SQLiteEvolutionStore
from components.memory.store import SQLiteMemoryStore
from components.content import SQLiteContentManifestStore
from components.attachments import (
    AttachmentLimits,
    DocumentTextExtractorRegistry,
    DocxTextExtractor,
    InputAttachmentService,
    LocalAttachmentStorage,
    PdfTextExtractor,
    PlainTextExtractor,
)
from components.resource.application.resource_plane import ResourcePlane
from components.resource.runtime.local_runtime import (
    LOCAL_RUNTIME_RESOURCE_CAPABILITIES,
    LocalRuntimeHealthProjector,
    LocalRuntimeResourceConfig,
    ensure_local_runtime_resource,
)
from contracts.local_runtime import LocalRuntimeAuthorizationRef
from components.resource.domain.runtime_health import ResourceHealthMonitor
from components.resource.infrastructure.health_store import SQLiteResourceHealthStore
from components.resource.infrastructure.node_store import SQLiteNodeStore
from components.resource.infrastructure.runtime_store import SQLiteResourceStore
from components.resource.scheduler.binder import ResourceBinder
from components.recovery.checkpoint import ACGCheckpointStore
from components.resource.scheduler.leases import RedisLeaseCoordinator
from components.marketplace.application.service import MarketplaceService
from components.marketplace.builtins.catalog import ensure_builtin_catalog
from components.resource.infrastructure.audit_store import SQLiteResourceAuditStore
from components.marketplace.infrastructure import DirectoryCatalog, LocalPackageLauncher, LoopbackHttpEndpointProbe, SQLiteInstallationJobStore
from components.mission_manager.store import WorkflowRegistry
from runtime import ApplicationSetup, ExecutionRuntime
from adapters.guarded_model import GuardedModelRuntime
from adapters.model_runtime import RegisteredModelRuntime
from runtime import (
    AcgIdentityLifecycleService,
    IdentityProjectionReconciler,
    IdentityProjectionBridge,
)
from service.agents import AgentRegistry
from support.packs.registry import register_installed_packs
from support.stores.sqlite_workflow_store import SQLiteWorkflowStore

from app.execution.instance_lock import acquire_workflow_instance_lock, release_workflow_instance_lock
from app.execution.model_runtime import GatewayStructuredGenerationRuntime
from app.tools import get_tool_runtime


LOGGER = logging.getLogger(__name__)


_DEFAULT_DATABASES = {
    "AGENTOS_LANGGRAPH_CHECKPOINT_DB": "data/langgraph_checkpoints.sqlite3",
    "AGENTOS_EXECUTION_VALUE_DB": "data/execution_values.sqlite3",
    "AGENTOS_CONTENT_MANIFEST_DB": "data/content_manifests.sqlite3",
    "AGENTOS_EXECUTION_MEMORY_DB": "data/execution_memory.sqlite3",
    "AGENTOS_PROVENANCE_DB": "data/provenance.sqlite3",
    "AGENTOS_AUDIT_DB": "data/audit_decisions.sqlite3",
    "AGENTOS_RESOURCE_DB": "data/resources.sqlite3",
    "AGENTOS_NODE_DB": "data/nodes.sqlite3",
    "AGENTOS_RESOURCE_HEALTH_DB": "data/resource_health.sqlite3",
    "AGENTOS_EVOLUTION_DB": "data/evolution.sqlite3",
    "AGENTOS_MARKETPLACE_DB": "data/marketplace.sqlite3",
}


class GatewayIntentLLM:
    def generate_json(self, prompt: str, schema: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        from app.llm.gateway import get_llm_gateway

        return get_llm_gateway().generate_json(prompt, schema, **kwargs)


def _run_coroutine_sync(factory):
    """Bridge the legacy synchronous planner boundary to the async model runtime."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())
    result: dict[str, Any] = {}
    failure: list[BaseException] = []

    def runner() -> None:
        try:
            result["value"] = asyncio.run(factory())
        except BaseException as exc:  # pragma: no cover - only reached in nested-loop hosts
            failure.append(exc)

    thread = Thread(target=runner, name="agentos-planner-model-bridge", daemon=True)
    thread.start()
    thread.join()
    if failure:
        raise failure[0]
    return result.get("value")


class RegisteredPlannerLLM:
    """Bridge planner calls to the Runtime-owned model registry."""

    def __init__(self, runtime: ExecutionRuntime, binding: dict[str, Any] | None = None) -> None:
        self._runtime = runtime
        self._binding = dict(binding) if binding is not None else None

    def copilot_models(self):
        from app.llm.capabilities import provider_model_capabilities
        return tuple({**route, "reasoningEfforts": list(caps.reasoning_efforts or []),
            "defaultReasoningEffort": caps.default_reasoning_effort}
            for route in self._runtime.model_registry.list_models()
            for caps in [provider_model_capabilities(route["model"], "", route["provider"])])

    def for_model(self, provider: str, model: str):
        self._runtime.model_registry.resolve(provider, model)
        return RegisteredPlannerLLM(self._runtime, {"provider": provider, "model": model})

    @property
    def binding(self):
        return self._binding if self._binding is not None else self._runtime.default_model_binding or {}

    @property
    def _model_runtime(self) -> RegisteredModelRuntime:
        binding = self.binding
        return RegisteredModelRuntime(
            registry=self._runtime.model_registry,
            provider=str(binding.get("provider") or ""),
            model=str(binding.get("model") or ""),
            version=binding.get("version"),
        )

    @property
    def provider(self) -> str:
        return str(self.binding.get("provider") or "")

    @property
    def model(self) -> str:
        return str(self.binding.get("model") or "")

    def is_available(self) -> bool:
        if not self.provider or not self.model:
            return False
        return self._model_runtime.is_available()

    def describe_model(self):
        return self._model_runtime.describe_model()

    def stream_generate_json(self, **kwargs):
        return self._model_runtime.stream_generate_json(**kwargs)

    def generate_json(self, prompt: str, schema: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        call_kwargs = dict(kwargs)
        if "max_tokens" in call_kwargs:
            call_kwargs["max_output_tokens"] = call_kwargs.pop("max_tokens")
        # Legacy planner audit identity is separate from model request parameters.
        template_hash = call_kwargs.pop("prompt_template_hash", None)
        result = _run_coroutine_sync(lambda: self._model_runtime.generate_json(
            prompt=prompt, schema=schema, **call_kwargs,
        ))
        return {
            **result.audit_record(), "data": result.data,
            "latency_ms": result.latency_ms,
            **({"prompt_template_hash": template_hash} if template_hash else {}),
        }


def bind_registered_planner_llm(runtime: ExecutionRuntime) -> bool:
    """Switch the production planner to the same registry used by node runtime."""
    current = getattr(runtime, "_intent_llm", None)
    if not isinstance(current, GatewayIntentLLM):
        return False
    if not getattr(runtime, "default_model_binding", None):
        return False
    candidate = RegisteredPlannerLLM(runtime)
    if not candidate.is_available():
        return False
    runtime.set_intent_llm(candidate)
    return True


def _workflow_db_path(environment: Mapping[str, str]) -> Path:
    configured = str(environment.get("AGENTOS_WORKFLOW_DB_PATH") or "").strip()
    if not configured:
        raise RuntimeError("AGENTOS_WORKFLOW_DB_PATH is required outside test mode")
    return Path(configured)


def _database_path(environment: Mapping[str, str], name: str) -> Path:
    return Path(str(environment.get(name) or _DEFAULT_DATABASES[name]).strip())


def _read_optional_secret(environment: Mapping[str, str], name: str) -> str | None:
    direct = str(environment.get(name) or "").strip()
    if direct:
        return direct
    secret_path = str(environment.get(f"{name}_FILE") or "").strip()
    if not secret_path:
        return None
    return Path(secret_path).read_text(encoding="utf-8").strip() or None


def _build_coordination_client(environment: Mapping[str, str]):
    from redis import Redis

    return Redis.from_url(
        str(environment["AGENTOS_COORDINATION_REDIS_URL"]),
        password=_read_optional_secret(environment, "REDIS_PASSWORD"),
        decode_responses=False,
    )


def configure_runtime(
    runtime: ExecutionRuntime,
    *,
    intent_llm: object | None = None,
    model_runtime: object | None = None,
) -> ExecutionRuntime:
    runtime.set_intent_llm(intent_llm or GatewayIntentLLM())
    runtime.set_model_runtime(model_runtime or GatewayStructuredGenerationRuntime())
    return runtime


def sync_agent_registry_to_ledger(runtime: ExecutionRuntime) -> None:
    """Project callable application Agents into the embedded runtime resource."""
    from components.resource.runtime.embedded_runtime import register_embedded_agents_runtime

    register_embedded_agents_runtime(runtime.resource_plane, runtime.agent_registry.all())


def build_model_setup(
    runtime: ExecutionRuntime,
    *,
    environment: Mapping[str, str] | None = None,
) -> ApplicationSetup:
    """Bind configured adapters to the Runtime-owned model registry."""
    values = dict(os.environ if environment is None else environment)
    if not str(values.get("AGENTOS_MODELS") or "").strip():
        # The application historically configured the same provider through the
        # legacy gateway variables. Promote that route into the Runtime registry
        # so Planner never silently falls back to a synchronous provider call.
        from app.llm.gateway import get_llm_gateway

        gateway = get_llm_gateway()
        config = gateway.config
        if (
            gateway.provider_name not in {"", "mock", "unavailable"}
            and gateway.model
            and config.base_url
            and config.api_key
        ):
            key_env = "AGENTOS_RUNTIME_MODEL_API_KEY"
            values[key_env] = config.api_key
            values["AGENTOS_MODELS"] = json.dumps([{
                "capabilityId": f"model.gateway.{gateway.provider_name}",
                "provider": gateway.provider_name,
                "models": [gateway.model],
                "baseUrl": config.base_url,
                "apiKeyEnv": key_env,
                "version": "1.0.0",
                "priority": 100,
                "requestTimeoutSeconds": config.timeout_seconds,
            }])
    setup = ApplicationSetup.from_environment(
        values,
        model_registry=runtime.model_registry,
    )
    runtime.default_model_binding = setup.default_model_binding
    _sync_model_endpoints_from_registry(runtime)
    return setup


def _sync_model_endpoints_from_registry(runtime: ExecutionRuntime) -> None:
    """把模型注册表的当前路由投影为资源平面的模型端点目录。

    模型端点是资源事实（provider/model/上下文窗口/特性），与执行后端
    相互独立；任务侧的 ModelDemand 依据这份目录完成绑定。
    """

    def describe(provider: str, model: str):
        try:
            adapter = runtime.model_registry.resolve(provider, model)
        except LookupError:
            return None
        try:
            return adapter.describe_model(model)
        except Exception:
            return None

    routes = [
        {"provider": route.get("provider"), "model": route.get("model")}
        for route in runtime.model_registry.list_models()
    ]
    plane = getattr(runtime, "resource_plane", None)
    if plane is None:
        return
    try:
        plane.sync_model_endpoints(routes, describe_model=describe)
    except Exception:
        # 端点目录是调度增强，不是启动前置条件；失败降级为日志。
        import logging

        logging.getLogger(__name__).warning(
            "model endpoint sync failed", exc_info=True
        )


class _AssemblyProgress:
    """Track partially constructed resources so a failed composition cleans up."""

    def __init__(self) -> None:
        self.runtime: ExecutionRuntime | None = None
        self.owned: list[Any] = []

    def own(self, resource):
        self.owned.append(resource)
        return resource


def build_default_runtime(
    *,
    environment: Mapping[str, str] | None = None,
    intent_llm: object | None = None,
    model_runtime: object | None = None,
    tool_runtime: object | None = None,
    coordination_client: object | None = None,
) -> ExecutionRuntime:
    """Construct all registries, stores, and external adapters in the application."""
    env = environment or os.environ
    environment_name = str(env.get("ENVIRONMENT") or "development").strip().lower()
    resource_credential_key = _read_optional_secret(env, "AGENTOS_RESOURCE_CREDENTIAL_KEY")
    if environment_name in {"prod", "production"} and not resource_credential_key:
        raise RuntimeError(
            "AGENTOS_RESOURCE_CREDENTIAL_KEY is required in production"
        )
    semantic_enabled = str(
        env.get("AGENTOS_MISSION_SEMANTIC_CONVERGENCE") or "false"
    ).lower() == "true"
    c2_execution_authorities = (
        str(env.get("AGENTOS_C2_EXECUTION_AUTHORITIES") or "false").lower() == "true"
    )
    if c2_execution_authorities and not semantic_enabled:
        # The C2 authorities validate against mission semantics and a trusted
        # semantic principal; assembly without convergence has no valid contract.
        # Refuse before taking the instance lock or constructing any resource.
        raise RuntimeError(
            "AGENTOS_C2_EXECUTION_AUTHORITIES requires AGENTOS_MISSION_SEMANTIC_CONVERGENCE"
        )
    if str(env.get("AGENTOS_C2_EXECUTION_DISPATCH") or "false").lower() == "true" and not c2_execution_authorities:
        raise RuntimeError("AGENTOS_C2_EXECUTION_DISPATCH requires C2 execution authorities")
    workflow_path = _workflow_db_path(env)
    acquire_workflow_instance_lock(str(workflow_path))
    progress = _AssemblyProgress()
    try:
        return _assemble_default_runtime(
            env=env,
            workflow_path=workflow_path,
            semantic_enabled=semantic_enabled,
            c2_execution_authorities=c2_execution_authorities,
            resource_credential_key=resource_credential_key,
            intent_llm=intent_llm,
            model_runtime=model_runtime,
            tool_runtime=tool_runtime,
            coordination_client=coordination_client,
            progress=progress,
        )
    except BaseException:
        # Close whatever the failed composition already created and free the
        # instance lock, then let the original assembly error propagate.
        _cleanup_failed_assembly(progress)
        raise


def _assemble_default_runtime(
    *,
    env: Mapping[str, str],
    workflow_path: Path,
    semantic_enabled: bool,
    c2_execution_authorities: bool,
    resource_credential_key: str | None,
    intent_llm: object | None,
    model_runtime: object | None,
    tool_runtime: object | None,
    coordination_client: object | None,
    progress: _AssemblyProgress,
) -> ExecutionRuntime:
    resource_store = progress.own(SQLiteResourceStore(_database_path(env, "AGENTOS_RESOURCE_DB")))
    node_store = progress.own(SQLiteNodeStore(_database_path(env, "AGENTOS_NODE_DB")))
    health_store = progress.own(SQLiteResourceHealthStore(_database_path(env, "AGENTOS_RESOURCE_HEALTH_DB")))
    resource_plane = ResourcePlane(
        store=resource_store,
        node_store=node_store,
        health_monitor=ResourceHealthMonitor(
            store=health_store,
            heartbeat_timeout=timedelta(seconds=float(env.get("AGENTOS_RESOURCE_HEARTBEAT_TIMEOUT_SECONDS") or 60)),
        ),
        credential_key=resource_credential_key,
        audit_store=progress.own(SQLiteResourceAuditStore(_database_path(env, "AGENTOS_RESOURCE_DB"))),
    )
    coordination_url = str(env.get("AGENTOS_COORDINATION_REDIS_URL") or "").strip()
    coordinator = None
    if coordination_client is not None or coordination_url:
        coordinator = RedisLeaseCoordinator(
            coordination_client or _build_coordination_client(env)
        )
        progress.owned.append(coordinator)
    resource_binder = ResourceBinder(resource_plane, coordinator=coordinator)
    identity_service = AcgIdentityLifecycleService.from_sqlite(
        Path(str(
            env.get("AGENTOS_IDENTITY_DB")
            or workflow_path.with_name("identity_v2.sqlite3")
        ))
    )
    progress.owned.append(identity_service)
    # The identity projection and the single ExecutionRuntime must observe the
    # same ContentManifest store.  Artifact is only a V2 identity projection of
    # sealed manifests; it is not a second content database.
    content_manifest_store = SQLiteContentManifestStore(
        _database_path(env, "AGENTOS_CONTENT_MANIFEST_DB")
    )
    progress.owned.append(content_manifest_store)
    identity_adapter = IdentityProjectionBridge(
        identity_service,
        identity_service.repositories,
        content_manifest_store,
    )
    attachment_limits = AttachmentLimits(
        max_file_bytes=int(env["AGENTOS_ATTACHMENT_MAX_FILE_BYTES"]) if env.get("AGENTOS_ATTACHMENT_MAX_FILE_BYTES") else None,
        max_total_bytes=int(env["AGENTOS_ATTACHMENT_MAX_TOTAL_BYTES"]) if env.get("AGENTOS_ATTACHMENT_MAX_TOTAL_BYTES") else None,
        max_context_characters=int(env.get("AGENTOS_ATTACHMENT_MAX_CONTEXT_CHARACTERS") or 120_000),
    )
    attachment_service = InputAttachmentService(
        repository=identity_service.repositories.input_attachments,
        storage=LocalAttachmentStorage(
            Path(str(env.get("AGENTOS_ATTACHMENT_STORAGE_DIR") or workflow_path.parent / "attachments"))
        ),
        extractors=DocumentTextExtractorRegistry((
            PlainTextExtractor(),
            PdfTextExtractor(max_pages=int(env.get("AGENTOS_ATTACHMENT_PDF_MAX_PAGES") or 500)),
            DocxTextExtractor(
                max_uncompressed_bytes=int(
                    env.get("AGENTOS_ATTACHMENT_DOCX_MAX_UNCOMPRESSED_BYTES") or 50 * 1024 * 1024
                )
            ),
        )),
        content_store=content_manifest_store,
        limits=attachment_limits,
    )
    workflow_store = SQLiteWorkflowStore(workflow_path)
    progress.owned.append(workflow_store)
    semantic_service = None
    if semantic_enabled:
        from components.mission_manager.semantic_service import MissionSemanticService
        # Activation never upgrades the business database. An operator must
        # explicitly install the S00-01 schema before enabling this path.
        workflow_store.enable_existing_mission_semantics()

        def authorize_semantics(principal, mission_id, action):
            mission = identity_service.repositories.missions.get(mission_id)
            if mission is not None:
                owner, tenant = mission.user_id, mission.metadata.get("tenantId")
            else:
                # Creation can defer Identity projection. Ownership here was
                # stamped by the trusted HTTP boundary, never taken as a principal.
                try:
                    record = workflow_store.get_mission(mission_id)
                except KeyError:
                    return False
                owner = record.input.get("authenticatedUserId")
                tenant = record.input.get("authenticatedTenantId")
            return bool(owner) and owner == principal.actor_id and (tenant or "__unscoped__") == principal.tenant_id

        semantic_service = MissionSemanticService(store=workflow_store, authorize=authorize_semantics)
    from app.security.internal_auth import current_semantic_principal
    checkpoint_store = progress.own(ACGCheckpointStore(db_path=_database_path(env, "AGENTOS_LANGGRAPH_CHECKPOINT_DB")))
    execution_value_store = progress.own(SQLiteExecutionValueStore(db_path=_database_path(env, "AGENTOS_EXECUTION_VALUE_DB")))
    memory_store = progress.own(SQLiteMemoryStore(db_path=_database_path(env, "AGENTOS_EXECUTION_MEMORY_DB")))
    evolution_store = progress.own(SQLiteEvolutionStore(db_path=_database_path(env, "AGENTOS_EVOLUTION_DB")))
    evolution_service = EvolutionService(store=evolution_store, proposal_threshold=1)
    provenance_store = progress.own(SQLiteProvenanceStore(db_path=_database_path(env, "AGENTOS_PROVENANCE_DB")))
    decision_store = progress.own(SQLiteDecisionStore(db_path=_database_path(env, "AGENTOS_AUDIT_DB")))
    runtime = ExecutionRuntime(
        agent_registry=AgentRegistry(),
        workflow_registry=WorkflowRegistry(),
        workflow_store=workflow_store,
        mission_semantic_service=semantic_service,
        semantic_principal_provider=current_semantic_principal,
        allow_legacy_mission_intent=str(env.get("AGENTOS_ALLOW_LEGACY_MISSION_INTENT") or "false").lower() == "true",
        checkpoint_store=checkpoint_store,
        execution_value_store=execution_value_store,
        content_manifest_store=content_manifest_store,
        memory_store=memory_store,
        resource_plane=resource_plane,
        resource_binder=resource_binder,
        evolution_service=evolution_service,
        provenance_store=provenance_store,
        decision_store=decision_store,
        tool_runtime=tool_runtime or get_tool_runtime(),
        identity_lifecycle=identity_adapter,
        require_planner_identity=True,
    )
    marketplace_jobs = progress.own(
        SQLiteInstallationJobStore(_database_path(env, "AGENTOS_MARKETPLACE_DB"))
    )
    marketplace_package_root = Path(str(
        env.get("AGENTOS_MARKETPLACE_PACKAGE_DIR") or workflow_path.parent / "marketplace" / "packages"
    ))
    marketplace_catalog_root = Path(str(env.get("AGENTOS_MARKETPLACE_CATALOG_DIR") or workflow_path.parent / "marketplace" / "catalog"))
    ensure_builtin_catalog(marketplace_catalog_root, marketplace_package_root)
    runtime.marketplace_service = MarketplaceService(
        catalog=DirectoryCatalog(marketplace_catalog_root),
        jobs=marketplace_jobs,
        package_root=marketplace_package_root,
        launcher=progress.own(LocalPackageLauncher(
            package_root=marketplace_package_root,
            install_root=env.get("AGENTOS_MARKETPLACE_INSTALL_DIR") or workflow_path.parent / "marketplace" / "installed",
        )),
        endpoint_probe=LoopbackHttpEndpointProbe(),
        plane=resource_plane,
    )
    progress.own(runtime.marketplace_service)
    runtime.marketplace_service.start_monitor()
    progress.runtime = runtime
    runtime._assembly_owned_resources = progress.owned
    runtime.attachment_service = attachment_service
    runtime.attachment_context_builder = attachment_service.context_builder
    if c2_execution_authorities:
        # Explicit assembly over operator-upgraded ledgers, in the authorities'
        # own construction order. Every store is verify-only: a missing marker
        # table or a path mismatch aborts startup instead of degrading new
        # Runs to legacy direct execution.
        from support.stores.execution_permit_store import SQLiteExecutionPermitStore
        from support.stores.graph_activation_store import SQLiteGraphActivationStore
        from support.stores.graph_handoff_store import (
            SQLiteGraphHandoffStore,
            SQLiteStagedGraphCheckpointStore,
        )
        from support.stores.graph_materialization_store import (
            SQLiteGraphMaterializationStore,
        )
        from support.stores.planning_commit_store import SQLitePlanningCommitStore

        workflow_db_path = runtime.workflow_store.db_path
        checkpoint_db_path = runtime.checkpoint_store.db_path
        runtime.enable_planning_commit(SQLitePlanningCommitStore(workflow_db_path))
        runtime.enable_graph_materialization(
            SQLiteGraphMaterializationStore(workflow_db_path)
        )
        runtime.enable_graph_activation(SQLiteGraphActivationStore(workflow_db_path))
        runtime.enable_graph_handoff(
            SQLiteGraphHandoffStore(workflow_db_path),
            SQLiteStagedGraphCheckpointStore(checkpoint_db_path),
        )
        runtime.enable_execution_permit(SQLiteExecutionPermitStore(workflow_db_path))
    runtime.execution_dispatch_store = None
    runtime.execution_dispatch_enabled = str(env.get("AGENTOS_C2_EXECUTION_DISPATCH") or "false").lower() == "true"
    if runtime.execution_dispatch_enabled:
        from support.stores.execution_dispatch_store import SQLiteExecutionDispatchStore
        runtime.execution_dispatch_store = SQLiteExecutionDispatchStore(runtime.workflow_store.db_path)
    reconciliation = IdentityProjectionReconciler(
        identity_adapter
    ).reconcile_workflow_store(runtime.workflow_store, audit_existing=False)
    runtime.identity_reconciliation_report = reconciliation
    local_runtime_endpoint = str(env.get("AGENTOS_LOCAL_RUNTIME_ENDPOINT") or "").strip()
    if local_runtime_endpoint:
        configured_capabilities = tuple(
            item.strip()
            for item in str(env.get("AGENTOS_LOCAL_RUNTIME_CAPABILITIES") or "").split(",")
            if item.strip()
        )
        local_runtime_config = LocalRuntimeResourceConfig(
            resource_id=str(env.get("AGENTOS_LOCAL_RUNTIME_RESOURCE_ID") or "zhiyi-local-runtime"),
            owner_scope=str(env.get("AGENTOS_LOCAL_RUNTIME_OWNER_SCOPE") or "desktop-user"),
            execution_endpoint=local_runtime_endpoint,
            version=int(env.get("AGENTOS_LOCAL_RUNTIME_VERSION") or 1),
            capacity=int(env.get("AGENTOS_LOCAL_RUNTIME_CAPACITY") or 1),
            credential_id=str(env.get("AGENTOS_LOCAL_RUNTIME_CREDENTIAL_ID") or "").strip() or None,
            credential_secret=_read_optional_secret(env, "AGENTOS_LOCAL_RUNTIME_CREDENTIAL_SECRET"),
            capabilities=configured_capabilities or LOCAL_RUNTIME_RESOURCE_CAPABILITIES,
            shell_exec_enabled=str(env.get("AGENTOS_LOCAL_RUNTIME_SHELL_ENABLED") or "false").strip().lower()
            in {"1", "true", "yes", "on"},
        )
        registered_local_runtime = ensure_local_runtime_resource(
            resource_plane, local_runtime_config
        )
        # hands 是唯一执行后端（DSH 基座）；Local Runtime 仅作为协议/合同层保留。
        from adapters.hands_http import HandsHttpTransport
        local_runtime_transport = HandsHttpTransport(
            resource_id=registered_local_runtime.profile.runtime_id,
            address=registered_local_runtime.profile.endpoint.address,
            credential_provider=resource_plane,
            timeout_seconds=float(env.get("AGENTOS_LOCAL_RUNTIME_TIMEOUT_SECONDS") or 120),
        )
        progress.own(local_runtime_transport)
        runtime.local_runtime_resource = registered_local_runtime
        runtime.local_runtime_transport = local_runtime_transport
        runtime.local_runtime_client = LocalRuntimeClient(local_runtime_transport)
        runtime.local_runtime_health_projector = LocalRuntimeHealthProjector(
            resource_plane, registered_local_runtime.profile.runtime_id
        )
        workspace_id = str(env.get("AGENTOS_LOCAL_RUNTIME_WORKSPACE_ID") or "").strip()
        grant_id = str(env.get("AGENTOS_LOCAL_RUNTIME_GRANT_ID") or "").strip()
        runtime.local_runtime_authorization = (
            LocalRuntimeAuthorizationRef(
                grantId=grant_id,
                workspaceId=workspace_id,
            )
            if workspace_id and grant_id
            else None
        )
    if env.get('AGENTOS_WORKSPACE_DATABASE_URL'):
        from app.execution.workspace_authority import WorkspaceAuthority
        runtime.workspace_authority = WorkspaceAuthority(env, runtime.local_runtime_resource.profile.runtime_id)
    # hands 唯一后端：mission 链工具恒走正式五步（收据闭环）。
    from app.tools.formal_workspace import FormalWorkspaceTools
    runtime.tool_runtime = FormalWorkspaceTools(runtime, runtime.tool_runtime)
    register_native_runtime(agent_registry=runtime.agent_registry, workflow_registry=runtime.workflow_registry)
    runtime.plugin_manifests = register_installed_packs(
        agent_registry=runtime.agent_registry,
        workflow_registry=runtime.workflow_registry,
        capability_catalog=runtime.capability_catalog,
    )
    sync_agent_registry_to_ledger(runtime)
    return configure_runtime(runtime, intent_llm=intent_llm, model_runtime=model_runtime)


def _runtime_close_sequence(runtime: ExecutionRuntime) -> tuple[Any, ...]:
    """Every resource owned by a composed Runtime, in close order."""
    resource_plane = getattr(runtime, "resource_plane", None)
    resources = (
        *reversed(getattr(runtime, "_assembly_owned_resources", ())),
        getattr(runtime, "local_runtime_transport", None),
        runtime.workflow_store,
        runtime.checkpoint_store,
        runtime.execution_value_store,
        runtime.content_manifest_store,
        runtime.memory_store,
        getattr(resource_plane, "store", None),
        getattr(getattr(resource_plane, "health_monitor", None), "store", None),
        getattr(resource_plane, "node_store", None),
        getattr(getattr(runtime, "resource_binder", None), "coordinator", None),
        runtime.evolution_service.store,
        runtime.provenance_store,
        runtime.decision_store,
        getattr(runtime, "_model_runtime", None),
        getattr(
            getattr(runtime, "identity_lifecycle", None),
            "lifecycle_service",
            None,
        ),
    )
    # The C2 authority stores hold no persistent handles today (per-operation
    # connections); walk them anyway so a future close() is never missed.
    handoff_authority = runtime.graph_handoff_authority
    resources += tuple(
        store
        for authority in (
            runtime.planning_commit_authority,
            runtime.graph_materialization_authority,
            runtime.graph_activation_authority,
            handoff_authority,
            runtime.execution_permit_authority,
        )
        if authority is not None
        for store in (
            (authority.store, authority.staged_store)
            if authority is handoff_authority
            else (authority.store,)
        )
    )
    return resources


def _close_resources(resources) -> list[Exception]:
    errors = []
    seen: set[int] = set()
    for resource in resources:
        if resource is None or id(resource) in seen:
            continue
        seen.add(id(resource))
        try:
            aclose = getattr(resource, "aclose", None)
            close = getattr(resource, "close", None)
            if callable(aclose):
                _run_coroutine_sync(aclose)
            elif callable(close):
                close()
        except Exception as exc:
            errors.append(exc)
            LOGGER.warning("runtime cleanup failed for %r", resource, exc_info=True)
    return errors


def close_runtime(runtime: ExecutionRuntime) -> None:
    """Synchronous shutdown; async hosts must await aclose_runtime instead."""
    errors = _close_resources(_runtime_close_sequence(runtime))
    try:
        release_workflow_instance_lock()
    except Exception as exc:
        errors.append(exc)
    if errors:
        raise errors[0]


async def aclose_runtime(runtime: ExecutionRuntime) -> None:
    """Attempt every close and release the lock before propagating cancellation.

    An interrupted client may remain open. Keep its owned reference for an
    explicit shutdown retry; do not silently retry or shield an unbounded close.
    Cancellation wins over ordinary cleanup failures, which remain logged.
    """
    errors = []
    cancelled: asyncio.CancelledError | None = None
    seen: set[int] = set()
    try:
        for resource in _runtime_close_sequence(runtime):
            if resource is None or id(resource) in seen:
                continue
            seen.add(id(resource))
            try:
                aclose = getattr(resource, "aclose", None)
                if callable(aclose):
                    await aclose()
                else:
                    errors.extend(_close_resources((resource,)))
            except asyncio.CancelledError as exc:
                if cancelled is None:
                    cancelled = exc
                LOGGER.warning(
                    "runtime close cancelled for %r; resource may remain open; "
                    "retry shutdown explicitly", resource, exc_info=True,
                )
            except Exception as exc:
                errors.append(exc)
                LOGGER.warning("async runtime cleanup failed for %r", resource, exc_info=True)
    finally:
        try:
            # The lock helper invalidates its state before attempting OS release.
            release_workflow_instance_lock()
        except Exception as exc:
            errors.append(exc)
            LOGGER.warning("runtime instance lock release failed", exc_info=True)
    if cancelled is not None:
        if errors:
            cancelled.add_note(f"{len(errors)} other runtime cleanup error(s); see cleanup logs")
        raise cancelled
    if errors:
        raise errors[0]


def _cleanup_failed_assembly(progress: _AssemblyProgress) -> None:
    """The construction ledger is authoritative even if Runtime.__init__ failed."""
    resources = list(reversed(progress.owned))
    if progress.runtime is not None:
        try:
            resources.extend(_runtime_close_sequence(progress.runtime))
        except Exception:
            LOGGER.warning("assembly cleanup: runtime enumeration failed", exc_info=True)
    _close_resources(resources)
    try:
        release_workflow_instance_lock()
    except Exception:
        LOGGER.warning("assembly cleanup: instance lock release failed", exc_info=True)


__all__ = [
    "GatewayIntentLLM",
    "RegisteredPlannerLLM",
    "bind_registered_planner_llm",
    "build_default_runtime",
    "build_model_setup",
    "close_runtime",
    "aclose_runtime",
    "configure_runtime",
    "sync_agent_registry_to_ledger",
]
