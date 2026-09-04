"""Composition root for the single AgentOS execution runtime."""

from __future__ import annotations

import os
import asyncio
import json
from pathlib import Path
from threading import Thread
from typing import Any, Mapping

from adapters.model.native import register_native_runtime
from components.auditor.decision_store import SQLiteDecisionStore
from components.communicator.provenance_store import SQLiteProvenanceStore
from components.executor.value_store import SQLiteExecutionValueStore
from components.evolution.service import EvolutionService
from components.evolution.store import SQLiteEvolutionStore
from components.memory.store import SQLiteMemoryStore
from components.content import SQLiteContentManifestStore
from components.resource.service import ResourceService
from components.resource.health import ResourceHealthMonitor
from components.resource.health_store import SQLiteResourceHealthStore
from components.resource.store import SQLiteResourceStore
from components.recovery.checkpoint import ACGCheckpointStore
from components.scheduler.leases import RedisLeaseCoordinator
from components.scheduler.service import SchedulerService
from components.mission_manager.store import WorkflowRegistry
from runtime import ApplicationSetup, ExecutionRuntime
from adapters.guarded_model import GuardedModelRuntime
from adapters.model_runtime import RegisteredModelRuntime
from runtime.v2 import (
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


_DEFAULT_DATABASES = {
    "AGENTOS_LANGGRAPH_CHECKPOINT_DB": "data/langgraph_checkpoints.sqlite3",
    "AGENTOS_EXECUTION_VALUE_DB": "data/execution_values.sqlite3",
    "AGENTOS_CONTENT_MANIFEST_DB": "data/content_manifests.sqlite3",
    "AGENTOS_EXECUTION_MEMORY_DB": "data/execution_memory.sqlite3",
    "AGENTOS_PROVENANCE_DB": "data/provenance.sqlite3",
    "AGENTOS_AUDIT_DB": "data/audit_decisions.sqlite3",
    "AGENTOS_RESOURCE_DB": "data/resources.sqlite3",
    "AGENTOS_RESOURCE_HEALTH_DB": "data/resource_health.sqlite3",
    "AGENTOS_EVOLUTION_DB": "data/evolution.sqlite3",
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
    """Planner adapter backed by the Runtime-owned registered model stream."""

    def __init__(self, runtime: ExecutionRuntime) -> None:
        from app.llm.gateway import get_llm_gateway

        gateway = get_llm_gateway()
        self.provider = gateway.provider_name
        self.model = gateway.model
        self._runtime = GuardedModelRuntime(
            delegate=RegisteredModelRuntime(
                registry=runtime.model_registry,
                provider=self.provider,
                model=self.model,
            ),
            # Planning owns the retry budget so retries cannot restart a stream
            # underneath the one shared planning deadline.
            retries=0,
        )

    def is_available(self) -> bool:
        return self._runtime.is_available()

    def describe_model(self):
        return self._runtime.describe_model()

    def stream_generate_json(self, **kwargs):
        return self._runtime.stream_generate_json(**kwargs)

    def generate_json(self, prompt: str, schema: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        result = _run_coroutine_sync(
            lambda: self._runtime.generate_json(prompt=prompt, schema=schema, **kwargs)
        )
        return result.model_dump(by_alias=True, mode="json")


def bind_registered_planner_llm(runtime: ExecutionRuntime) -> bool:
    """Switch the production planner to the same registry used by node runtime."""
    current = getattr(runtime, "_intent_llm", None)
    if not isinstance(current, GatewayIntentLLM):
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
    return setup


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
    workflow_path = _workflow_db_path(env)
    acquire_workflow_instance_lock(str(workflow_path))

    resource_service = ResourceService(
        store=SQLiteResourceStore(
            Path(str(env.get("AGENTOS_RESOURCE_DB") or workflow_path.with_name("resources.sqlite3")))
        ),
        health_monitor=ResourceHealthMonitor(
            store=SQLiteResourceHealthStore(_database_path(env, "AGENTOS_RESOURCE_HEALTH_DB"))
        ),
        credential_key=resource_credential_key,
    )
    coordination_url = str(env.get("AGENTOS_COORDINATION_REDIS_URL") or "").strip()
    scheduler_service = None
    if coordination_client is not None or coordination_url:
        coordinator = RedisLeaseCoordinator(
            coordination_client or _build_coordination_client(env)
        )
        scheduler_service = SchedulerService(
            resource_service=resource_service,
            coordinator=coordinator,
        )
    identity_service = AcgIdentityLifecycleService.from_sqlite(
        Path(str(
            env.get("AGENTOS_IDENTITY_DB")
            or workflow_path.with_name("identity_v2.sqlite3")
        ))
    )
    # The identity projection and the single ExecutionRuntime must observe the
    # same ContentManifest store.  Artifact is only a V2 identity projection of
    # sealed manifests; it is not a second content database.
    content_manifest_store = SQLiteContentManifestStore(
        _database_path(env, "AGENTOS_CONTENT_MANIFEST_DB")
    )
    identity_adapter = IdentityProjectionBridge(
        identity_service,
        identity_service.repositories,
        content_manifest_store,
    )
    runtime = ExecutionRuntime(
        agent_registry=AgentRegistry(),
        workflow_registry=WorkflowRegistry(),
        workflow_store=SQLiteWorkflowStore(workflow_path),
        checkpoint_store=ACGCheckpointStore(db_path=_database_path(env, "AGENTOS_LANGGRAPH_CHECKPOINT_DB")),
        execution_value_store=SQLiteExecutionValueStore(db_path=_database_path(env, "AGENTOS_EXECUTION_VALUE_DB")),
        content_manifest_store=content_manifest_store,
        memory_store=SQLiteMemoryStore(db_path=_database_path(env, "AGENTOS_EXECUTION_MEMORY_DB")),
        resource_service=resource_service,
        scheduler_service=scheduler_service,
        evolution_service=EvolutionService(
            store=SQLiteEvolutionStore(db_path=_database_path(env, "AGENTOS_EVOLUTION_DB")),
            proposal_threshold=1,
        ),
        provenance_store=SQLiteProvenanceStore(db_path=_database_path(env, "AGENTOS_PROVENANCE_DB")),
        decision_store=SQLiteDecisionStore(db_path=_database_path(env, "AGENTOS_AUDIT_DB")),
        tool_runtime=tool_runtime or get_tool_runtime(),
        identity_lifecycle=identity_adapter,
        require_planner_identity=True,
    )
    reconciliation = IdentityProjectionReconciler(
        identity_adapter
    ).reconcile_workflow_store(runtime.workflow_store)
    runtime.identity_reconciliation_report = reconciliation
    register_native_runtime(agent_registry=runtime.agent_registry, workflow_registry=runtime.workflow_registry)
    runtime.plugin_manifests = register_installed_packs(
        agent_registry=runtime.agent_registry,
        workflow_registry=runtime.workflow_registry,
        capability_catalog=runtime.capability_catalog,
    )
    return configure_runtime(runtime, intent_llm=intent_llm, model_runtime=model_runtime)


def close_runtime(runtime: ExecutionRuntime) -> None:
    """Close resources created by this composition root without changing workflow state."""
    resources = (
        runtime.workflow_store,
        runtime.checkpoint_store,
        runtime.execution_value_store,
        runtime.content_manifest_store,
        runtime.memory_store,
        runtime.resource_service.store,
        runtime.resource_service.health_monitor.store,
        runtime.scheduler_service.coordinator,
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
    seen: set[int] = set()
    for resource in resources:
        if resource is None or id(resource) in seen:
            continue
        seen.add(id(resource))
        close = getattr(resource, "close", None)
        if callable(close):
            close()
    release_workflow_instance_lock()


__all__ = [
    "GatewayIntentLLM",
    "RegisteredPlannerLLM",
    "bind_registered_planner_llm",
    "build_default_runtime",
    "build_model_setup",
    "close_runtime",
    "configure_runtime",
]
