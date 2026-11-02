"""AgentOS Core 的正式运行时文件，延续原 core.workflow_runtime 的实现并承载任务、工作流、审核和恢复入口。"""


from __future__ import annotations

import asyncio
import sqlite3
from copy import deepcopy
from datetime import datetime
import json
import logging
import os
import secrets
import threading
from time import monotonic
from typing import Any, Callable, Mapping, Optional

from service.agents import AgentRegistry
from support.acg.legacy.workflow_adapter import promote_workflow_to_acg
from support.acg.schema import RuntimeBlueprintSpec
from components.auditor.governance.evaluation import WorkflowEvaluator
from components.mission_manager.store import WorkflowRegistry
from components.auditor.governance.review import ReviewManager
from components.mission_manager.state_machine import StateMachine
from components.mission_manager.service import MissionManager
from components.auditor.governance.trace import TraceStore
from components.auditor.decision_store import DecisionStore, SQLiteDecisionStore
from components.communicator import SQLiteReliableCommunicationStore
from components.communicator.provenance import ProvenanceLedger
from components.communicator.provenance_store import SQLiteProvenanceStore
from components.executor import (
    ACGExecutionState,
    ACGGraphCompiler,
    ACGNodeRunner,
    ExecutionOrphanCleaner,
    ExecutionValueStore,
    SQLiteExecutionValueStore,
)
from components.evolution.service import EvolutionService
from contracts.evolution import (
    EvolutionPolicyVersion,
    EvolutionProposal,
    Trajectory,
    TrajectoryEvaluation,
)
from components.memory.store import SQLiteMemoryStore
from components.content import ContentManifestStore, SQLiteContentManifestStore
from contracts.acg_lifecycle import AcgIdentityLifecyclePort
from contracts.planning import (
    TaskImplementationBinding,
    TaskPlan,
)
from contracts.task_acceptance import frozen_task_acceptance
from components.planner.acg_semantic_validator import (
    validate_bound_acg_semantics,
)
from components.resource.service import ResourcePlane
from components.scheduler.binder import ResourceBinder
from components.recovery.checkpoint import (
    ACGCheckpointStore,
    ExecutionResumeCommand,
)
from adapters.resource_execution import ResourceExecutionAdapter
from adapters.guarded_model import GuardedModelRuntime
from adapters.model_compatibility import ModelCompatibilityRegistry, ModelProviderAdapter
from contracts.workflow import (
    MissionRecordState,
    RuntimeMissionRecord,
    Checkpoint,
    EvaluationRun,
    ReviewDecision,
    ReviewRecord,
    StepStatus,
    TraceEventType,
    WorkflowDefinition,
    RuntimeRunRecord,
    WorkflowStatus,
    WorkflowStep,
    RunExecutionScope,
    utc_now,
)
from contracts.execution import WorkflowProgressPhase
from contracts.recovery import GraphPatchResult, SemanticPatchRequest
from contracts.planning_commit import PlanningCommitReceipt
from runtime.compatibility import GLOBAL_RUN_LOCK_MANAGER, RunLockManager
from runtime.execution_migration import ExecutionEngineMigratingError
from support.acg.capabilities import CapabilityCatalog
from support.acg.native_capabilities import build_default_capability_catalog
from components.planner.algorithms import (
    PLANNER_ALGORITHM_VERSION,
    normalize_planning_diversity,
    normalize_planning_seed,
)
from components.planner.complexity import transport_error_code
from components.planner.service import (
    normalize_capability_profile,
)
from runtime.binding import RuntimeBindingService
from runtime.acg_execution import ACGExecutionService, ExecutionRunCancelled, ExecutionStateChanged
from runtime.ports import CollaboratorAccess, RuntimeCollaborators
from runtime.review import ReviewConflictError, ReviewService
from runtime.runtime_recovery import RuntimeRecoveryCoordinator
from runtime.semantic_revision import SemanticRevisionService
from runtime.state_persistence import (
    ACGStatePersistenceService,
    acg_execution_state_from_run,
)
from runtime.planning_loop import RuntimePlanningCoordinator
from runtime.planning_application import RuntimePlanningApplication
from runtime.dependencies import PluginScopeError, PluginScopeResolver
from support.packs.registry import register_installed_packs
from adapters.model.native import register_native_runtime
from support.stores.memory_workflow_store import MemoryWorkflowStore
from support.stores.sqlite_workflow_store import SQLiteWorkflowStore
from support.stores.workflow_store import WorkflowStore
from contracts.mission_semantic import SemanticPrincipal, run_intent_basis
from components.mission_manager.semantic_service import MissionSemanticService
from components.mission_manager.semantic_resolver import MissionSemanticResolver
from runtime.planner_input_adapter import planner_input


logger = logging.getLogger(__name__)

_TERMINAL_RUN_STATUSES = {
    WorkflowStatus.COMPLETED,
    WorkflowStatus.FAILED,
    WorkflowStatus.CANCELLED,
    WorkflowStatus.SUPERSEDED,
}

_LIFECYCLE_MESSAGES = {
    WorkflowProgressPhase.UNDERSTANDING: "任务已接受，正在准备 ACG 规划",
    WorkflowProgressPhase.PLANNING: "正在规划 ACG 执行路径",
    WorkflowProgressPhase.GRAPH_BUILDING: "正在构建 ACG 拓扑",
    WorkflowProgressPhase.EXECUTING: "正在执行 ACG 节点",
    WorkflowProgressPhase.RECOVERY: "正在恢复 ACG 执行",
    WorkflowProgressPhase.REVIEW: "正在等待人工审核",
    WorkflowProgressPhase.COMPLETED: "ACG 工作流执行完成",
    WorkflowProgressPhase.FAILED: "ACG 工作流执行失败",
    WorkflowProgressPhase.CANCELLED: "ACG 工作流已取消",
}

_ERROR_UNSET = object()
ExecutionAdapterFactory = Callable[..., object]

# Planner Runtime Event 允许进入 Trace 的字段白名单（全部为标量安全事实）。
# 计数字段必须由 Runtime 从真实对象计算得出，禁止携带任何模型文本。
_PLANNER_PROGRESS_FIELDS = frozenset({
    "stage", "status", "attempt", "retryCount", "timeoutSeconds", "errorCode",
    "kind", "taskCount", "dependencyCount", "nodeCount", "edgeCount",
    "constraintCount", "requiredCapabilityCount", "expectedArtifactCount",
    "callKey", "retryIndex", "elapsedMs", "idleMs", "receivedChunks", "receivedLength",
    "safeSummary", "delta",
})


def _safe_topology_audit(value: object) -> dict[str, Any]:
    """Project the closed, text-free topology audit schema into Runtime Trace."""
    if not isinstance(value, Mapping):
        return {}
    scalar_keys = {
        "compilerVersion", "producerKind", "catalogSource", "catalogFingerprint",
        "capabilityCoverageMode", "taskCount", "semanticEdgeCount",
        "topologyFingerprint", "status",
    }
    safe = {
        key: value[key] for key in scalar_keys
        if isinstance(value.get(key), (str, int, bool))
    }
    safe["capabilityRequirements"] = [
        {key: item[key] for key in (
            "requirementId", "producerCapability", "consumerCapability", "consumerTaskKey"
        ) if isinstance(item.get(key), str)}
        for item in list(value.get("capabilityRequirements") or [])[:100]
        if isinstance(item, Mapping)
    ]
    safe["selectedBindings"] = [
        {key: item[key] for key in ("requirementId", "producerTaskKey", "consumerTaskKey")
         if isinstance(item.get(key), str)}
        for item in list(value.get("selectedBindings") or [])[:100]
        if isinstance(item, Mapping)
    ]
    search = value.get("bindingSearch")
    safe["bindingSearch"] = {
        key: search[key] for key in ("statesExplored", "backtracks")
        if isinstance(search, Mapping) and isinstance(search.get(key), int)
    }
    repair = value.get("repair")
    safe["repair"] = {
        "attempts": repair.get("attempts", 0)
        if isinstance(repair, Mapping) and isinstance(repair.get("attempts", 0), int) else 0,
        "operationTypes": [
            item for item in list(repair.get("operationTypes") or [])[:20] if isinstance(item, str)
        ] if isinstance(repair, Mapping) else [],
    }
    conflict = value.get("conflict")
    if isinstance(conflict, Mapping):
        safe["conflict"] = {
            "code": conflict.get("code") if isinstance(conflict.get("code"), str) else "",
            "phase": conflict.get("phase") if isinstance(conflict.get("phase"), str) else "",
            "cycleNodes": [item for item in list(conflict.get("cycleNodes") or [])[:100] if isinstance(item, str)],
            "cycleEdges": [
                {key: item[key] for key in ("sourceKey", "targetKey", "origin", "mutationPolicy")
                 if isinstance(item.get(key), str)}
                for item in list(conflict.get("cycleEdges") or [])[:100] if isinstance(item, Mapping)
            ],
            "requirementIds": [
                item for item in list(conflict.get("requirementIds") or [])[:100] if isinstance(item, str)
            ],
            "bindingRejections": [
                {
                    **{key: item[key] for key in ("requirementId", "producerTaskKey", "reason")
                       if isinstance(item.get(key), str)},
                    "path": [part for part in list(item.get("path") or [])[:100] if isinstance(part, str)],
                }
                for item in list(conflict.get("bindingRejections") or [])[:100]
                if isinstance(item, Mapping)
            ],
        }
    else:
        safe["conflict"] = None
    return safe


class ExecutionRuntime(CollaboratorAccess):
    """唯一 Execution Runtime 执行内核，串联规划、调度、节点执行、审核与恢复。"""

    def __init__(
        self,
        *,
        agent_registry: Optional[AgentRegistry] = None,
        workflow_registry: Optional[WorkflowRegistry] = None,
        workflow_store: Optional[WorkflowStore] = None,
        trace_store: Optional[TraceStore] = None,
        checkpoint_store: Optional[object] = None,
        execution_value_store: ExecutionValueStore | None = None,
        content_manifest_store: ContentManifestStore | None = None,
        memory_store: object | None = None,
        provenance_store: SQLiteProvenanceStore | None = None,
        decision_store: DecisionStore | None = None,
        tool_runtime: object | None = None,
        review_manager: Optional[ReviewManager] = None,
        evaluator: Optional[WorkflowEvaluator] = None,
        mission_manager: Optional[MissionManager] = None,
        mission_semantic_service: MissionSemanticService | None = None,
        allow_legacy_mission_intent: bool = False,
        semantic_principal_provider: Callable[[], SemanticPrincipal | None] | None = None,
        execution_adapter_factories: Optional[Mapping[str, ExecutionAdapterFactory]] = None,
        run_lock_manager: Optional[RunLockManager] = None,
        recovery_recipe_registry: Optional[object] = None,
        capability_catalog: CapabilityCatalog | None = None,
        resource_plane: ResourcePlane | None = None,
        resource_binder: ResourceBinder | None = None,
        evolution_service: EvolutionService | None = None,
        model_registry: ModelCompatibilityRegistry | None = None,
        plugin_manifests: tuple = (),
        identity_lifecycle: AcgIdentityLifecyclePort | None = None,
        require_planner_identity: bool = False,
        scheduler_wait_timeout: float = 300.0,
        model_max_concurrency: int = 4,
        model_min_interval_seconds: float = 0.0,
        resource_execution_adapters: Optional[Mapping[str, ResourceExecutionAdapter]] = None,
        planning_commit_store: object | None = None,
    ):
        if scheduler_wait_timeout <= 0:
            raise ValueError("scheduler_wait_timeout must be positive")
        if model_max_concurrency < 1:
            raise ValueError("model_max_concurrency must be at least 1")
        if model_min_interval_seconds < 0:
            raise ValueError("model_min_interval_seconds must not be negative")
        resolved_agent_registry = agent_registry or AgentRegistry()
        resolved_capability_catalog = capability_catalog or build_default_capability_catalog()
        resolved_resource_plane = resource_plane or ResourcePlane()
        resolved_resource_binder = resource_binder or ResourceBinder(
            resolved_resource_plane
        )
        if resolved_resource_binder.plane is not resolved_resource_plane:
            raise ValueError("ResourceBinder must delegate to the injected ResourcePlane")
        # 共享协作者上下文：facade 与全部已提取服务按引用共享同一实例，属性
        # 写入即时可见，取代 PR-8C.2 的派发前逐项重对齐（测试在构造后替换
        # store、身份生命周期或调度参数时经由属性 setter 落进本上下文）。
        self.ports = RuntimeCollaborators(
            workflow_store=workflow_store or MemoryWorkflowStore(),
            trace_store=trace_store or TraceStore(),
            # 融合 ACG 使用独立 SQLite 检查点与正文引用仓库。检查点只保存 State
            # 引用；输出和 ContextPack 正文保存在另一文件，进程重启后仍可安全地
            # 继续审核流程。
            checkpoint_store=checkpoint_store or ACGCheckpointStore(),
            execution_value_store=execution_value_store or SQLiteExecutionValueStore(
                db_path=os.getenv("AGENTOS_EXECUTION_VALUE_DB", "data/execution_values.sqlite3")
            ),
            # L0/L3/L5 共用的内容寻址存储只保存 Manifest 与不可变 Fragment；它是
            # 当前 ExecutionRuntime 的一个持久化端口，不构成第二套 Runtime 或 Memory。
            content_manifest_store=content_manifest_store or SQLiteContentManifestStore(
                os.getenv("AGENTOS_CONTENT_MANIFEST_DB", "data/content_manifests.sqlite3")
            ),
            memory_store=memory_store or SQLiteMemoryStore(
                db_path=os.getenv("AGENTOS_EXECUTION_MEMORY_DB", "data/execution_memory.sqlite3")
            ),
            # 血缘账本与 checkpoint、正文仓库分文件保存。每次构建节点运行器前都会
            # 先重建并验证同 run 哈希链；损坏账本不会被静默绕过。
            provenance_store=provenance_store or SQLiteProvenanceStore(
                db_path=os.getenv("AGENTOS_PROVENANCE_DB", "data/provenance.sqlite3")
            ),
            # 审计决定独立于 Trace、checkpoint 和输出正文保存。恢复时引用必须从
            # 这里重新验证 run/step 归属，不能信任检查点或节点提交中的字符串。
            decision_store=decision_store or SQLiteDecisionStore(
                db_path=os.getenv("AGENTOS_AUDIT_DB", "data/audit_decisions.sqlite3")
            ),
            reliable_communication_store=SQLiteReliableCommunicationStore(
                os.getenv("AGENTOS_COMMUNICATION_DB", "data/communication.sqlite3")
            ),
            capability_catalog=resolved_capability_catalog,
            agent_registry=resolved_agent_registry,
            resource_plane=resolved_resource_plane,
            resource_binder=resolved_resource_binder,
            scheduler_wait_timeout=float(scheduler_wait_timeout),
            resource_execution_adapters=dict(resource_execution_adapters or {}),
            tool_runtime=tool_runtime,
            model_registry=model_registry or ModelCompatibilityRegistry(),
            identity_lifecycle=identity_lifecycle,
            # Composition installs this optional resolver. Persisted Mission/Run
            # inputs keep stable refs; bounded text is added only to model-bound
            # copies. Application composition sets default_model_binding after
            # model setup parsing; it is read only while a run is prepared and
            # copied into frozen bindings.
            attachment_context_builder=None,
            model_runtime=None,
            default_model_binding=None,
            # 测试可临时设置该私有钩子，模拟进程在一个已提交边界后消失。它不属于
            # 构造参数、环境变量或公开 contracts，生产运行时始终保持 ``None``。
            fault_hook=None,
        )
        self.workflow_registry = workflow_registry or WorkflowRegistry()
        self.model_max_concurrency = int(model_max_concurrency)
        self.model_min_interval_seconds = float(model_min_interval_seconds)
        self.evolution_service = evolution_service or EvolutionService()
        self.plugin_manifests = tuple(plugin_manifests)
        self.require_planner_identity = require_planner_identity
        self.mission_semantic_service = mission_semantic_service
        if mission_semantic_service is not None and mission_semantic_service.store is not self.workflow_store:
            raise ValueError("Mission semantics must use the injected WorkflowStore")
        self.allow_legacy_mission_intent = allow_legacy_mission_intent
        self.semantic_principal_provider = semantic_principal_provider
        self.attachment_service = None
        self.orphan_cleaner = ExecutionOrphanCleaner(value_store=self.execution_value_store)
        self.review_manager = review_manager or ReviewManager(self.trace_store)
        self.evaluator = evaluator or WorkflowEvaluator()
        self.state_machine = StateMachine()
        self.mission_manager = mission_manager or MissionManager(
            workflow_store=self.workflow_store,
            workflow_registry=self.workflow_registry,
            state_machine=self.state_machine,
            trace_store=self.trace_store,
        )
        self.runtime_binding_service = RuntimeBindingService(
            agent_registry=self.agent_registry,
            resource_plane=self.resource_plane,
            resource_execution_adapters=self.resource_execution_adapters,
        )
        self.acg_state_persistence = ACGStatePersistenceService(
            collaborators=self.ports,
            after_checkpoint_hook=lambda: self._inject_fault("after_checkpoint"),
        )
        self.semantic_revision_service = SemanticRevisionService(
            collaborators=self.ports,
            load_mission=self.mission_manager.get_mission,
            load_workflow=self._workflow_for_run,
            sync_run_steps=self._sync_run_steps_to_acg,
            validate_blueprint_agents=(
                self.runtime_binding_service.validate_blueprint_agents
            ),
            replacement_lifecycle_message=_LIFECYCLE_MESSAGES[
                WorkflowProgressPhase.UNDERSTANDING
            ],
        )
        # 审核边界：ACG 审核决定校验、批准/拒绝迁移与延迟记忆提交已迁入
        # ReviewService；Run 锁与批准后的续跑仍由本 facade 协调。
        self.review_service = ReviewService(
            collaborators=self.ports,
            state_machine=self.state_machine,
            set_run_lifecycle=self._set_run_lifecycle,
            mark_failed=self.mission_manager.mark_failed,
            validate_state_references=self._validate_acg_state_references,
        )
        # 恢复应用边界：retry / rebind / checkpoint resume 校验与失败投影已迁入
        # RuntimeRecoveryCoordinator；锁、执行槽与语义修订权威不在其中。
        self.runtime_recovery_coordinator = RuntimeRecoveryCoordinator(
            collaborators=self.ports,
            state_machine=self.state_machine,
            lifecycle_messages=_LIFECYCLE_MESSAGES,
            load_workflow=self._workflow_for_run,
            prepare_successor_run=self.prepare_run,
            mark_retrying=self.mission_manager.mark_retrying,
            mark_failed=lambda mission_id, run_id: self.mission_manager.mark_failed_for_run(mission_id, run_id=run_id),
            set_run_lifecycle=self._set_run_lifecycle,
            publish_run_terminal_event=self._publish_run_terminal_event,
            flush_identity_outbox=self._flush_identity_outbox,
        )
        # 执行边界：ACG stream loop、READY 调度与事件投影已迁入独立服务；锁、
        # 执行槽与 public 入口仍由本 facade 持有。协作者经共享上下文按引用读取。
        self.acg_execution_service = ACGExecutionService(
            load_mission=self.mission_manager.get_mission,
            load_workflow=self._workflow_for_run,
            state_machine=self.state_machine,
            state_persistence=self.acg_state_persistence,
            collaborators=self.ports,
            model_max_concurrency=self.model_max_concurrency,
            model_min_interval_seconds=self.model_min_interval_seconds,
            record_execution_failure=self.runtime_recovery_coordinator.record_execution_failure,
            terminal_run_statuses=frozenset(_TERMINAL_RUN_STATUSES),
            lifecycle_messages=_LIFECYCLE_MESSAGES,
            cancellation_event=self._cancellation_event,
            cancellation_requested=self._run_cancellation_requested,
            flush_identity_outbox=self._flush_identity_outbox,
            set_run_lifecycle=self._set_run_lifecycle,
            publish_run_terminal_event=self._publish_run_terminal_event,
            fail_run_safely=self.fail_run_safely,
            safe_error_message=self._safe_error_message,
            mark_running=self.mission_manager.mark_running,
            mark_running_for_new_run=self.mission_manager.mark_running_for_new_run,
            mark_completed=self.mission_manager.mark_completed,
            mark_waiting_review=self.mission_manager.mark_waiting_review,
            observe_boundary=lambda run, state, reason: self.runtime_planning_coordinator.boundary(run, state, reason),
        )
        self.runtime_planning_coordinator = RuntimePlanningCoordinator(
            collaborators=self.ports,
            load_goal=lambda mission_id: self.mission_manager.get_mission(mission_id).title,
            planner_for_run=self._planning_engine_for_run,
            validate_references=self._validate_acg_state_references,
            apply_decision=self._apply_runtime_planning_decision,
            guarded_save=self._save_runtime_planning_round,
            decision_gate=self._gate_planning_commit_decision,
            pending_commit_wait=self._resume_pending_commit_wait,
        )
        self.runtime_planning_application = RuntimePlanningApplication(
            collaborators=self.ports, state_persistence=self.acg_state_persistence,
            recovery=self.runtime_recovery_coordinator, binding=self.runtime_binding_service,
            semantic_revision=self.semantic_revision_service, mission_manager=self.mission_manager,
            set_lifecycle=self._set_run_lifecycle, flush_identity=self._flush_identity_outbox,
        )
        from runtime.planning_wait import RuntimePlanningWaitService
        self.runtime_planning_wait_service = RuntimePlanningWaitService(
            collaborators=self.ports, state_machine=self.state_machine,
            validate_references=self._validate_acg_state_references,
            flush_identity=self._flush_identity_outbox,
        )
        self.run_lock_manager = run_lock_manager or GLOBAL_RUN_LOCK_MANAGER
        # 每个 run 同时只允许一个活跃执行体：并发 start/resume/审核恢复在入口处
        # 原子认领执行槽，重复入口立即失败，而不是对同一批未提交步骤双跑。
        self._execution_slot_guard = threading.Lock()
        self._active_execution_slots: set[str] = set()
        self._execution_fences = {}
        # 协作式取消信号：cancel() 写入，_execute_acg 的调度边界读取并清理。
        self._run_cancel_guard = threading.Lock()
        self._run_cancel_events: dict[str, threading.Event] = {}
        self.planning_commit_authority = None
        self.graph_materialization_authority = None
        self.graph_activation_authority = None
        self.graph_handoff_authority = None
        self.execution_permit_authority = None
        self.execution_dispatch_enabled = False
        self.execution_dispatch_store = None
        if planning_commit_store is not None:
            self.enable_planning_commit(planning_commit_store)
        self.recovery_recipe_registry = recovery_recipe_registry
        self._runtime_adapters: dict[str, object] = {}
        self.execution_adapter_factories: dict[str, ExecutionAdapterFactory] = {
            self._normalize_runtime_engine(engine): factory
            for engine, factory in (execution_adapter_factories or {}).items()
        }
        # 认知规划引擎（懒构造）。app 层可通过 set_intent_llm 注入真实 LLM，
        # 让意图解析走 DeepSeek；未注入时规划器用启发式回退。
        self._planning_engine = None
        self._intent_llm = None

    @property
    def _model_runtime(self):
        """结构化模型运行时的晚绑定存储；读写直通共享协作者上下文。"""
        return self.ports.model_runtime

    @_model_runtime.setter
    def _model_runtime(self, value) -> None:
        self.ports.model_runtime = value

    @property
    def plugin_scope_resolver(self) -> PluginScopeResolver:
        """返回当前依赖注册表构造的插件范围解析器，不修改已冻结运行范围。"""
        return PluginScopeResolver(
            capability_catalog=self.capability_catalog,
            agent_registry=self.agent_registry,
            workflow_registry=self.workflow_registry,
            manifests=self.plugin_manifests,
        )

    def set_intent_llm(self, intent_llm) -> None:
        """注入意图解析 LLM（app 层在装配时调用）。重置已构造的规划引擎。"""
        self._intent_llm = intent_llm
        self._planning_engine = None

    def set_model_runtime(self, model_runtime) -> None:
        """注入结构化模型运行时，并统一置于超时、重试与限流保护边界内。"""
        self._model_runtime = (
            model_runtime
            if isinstance(model_runtime, GuardedModelRuntime)
            else GuardedModelRuntime(delegate=model_runtime, retries=1)
        )

    def register_model_adapter(self, adapter: ModelProviderAdapter) -> None:
        """登记应用层创建的模型适配器，不接收密钥、SDK 或网络配置。"""
        self.model_registry.register(adapter)

    @property
    def planning_engine(self):
        """延迟构造规划引擎并返回缓存实例；注入 LLM 后会由设置方法失效重建。"""
        if self._planning_engine is None:
            from components.planner.service import PlanningEngine

            self._planning_engine = PlanningEngine(
                workflow_registry=self.workflow_registry,
                agent_registry=self.agent_registry,
                capability_catalog=self.capability_catalog,
                intent_llm=self._intent_llm,
            )
        return self._planning_engine

    def register_execution_adapter(self, runtime_engine: str, factory: ExecutionAdapterFactory) -> None:
        """登记非 ACG 运行引擎适配器；空标识或覆盖策略由调用方显式负责。"""
        engine = self._normalize_runtime_engine(runtime_engine)
        if engine == "acg":
            raise ValueError(f"{engine} runtime engine is built into AgentOS Core")
        self.execution_adapter_factories[engine] = factory

    def create_mission(
        self,
        title: str,
        domain: str = "general",
        intent: str = "general",
        input: Optional[dict] = None,
        security_level: str = "internal",
        priority: str = "normal",
        *,
        role_type: Optional[str] = None,
        task_type: Optional[str] = None,
        workflow_id: Optional[str] = None,
        enabled_plugin_ids: Optional[list[str]] = None,
        defer_identity_projection: bool = False,
        creation_fingerprint: str | None = None,
        creation_key: str | None = None,
    ) -> RuntimeMissionRecord:
        """校验请求、解析插件范围并创建任务；合同或插件异常会向调用方明确传播。"""
        task_domain = (role_type or domain or "general").strip()
        task_intent = (task_type or intent or "general").strip()
        resolved_plugins = self.plugin_scope_resolver.resolve_enabled_plugin_ids(
            enabled_plugin_ids,
            workflow_id=workflow_id,
            domain=task_domain,
            intent=task_intent,
        )
        scope = self.plugin_scope_resolver.build_scope(resolved_plugins)
        task = self.mission_manager.create_mission(
            title=title,
            domain=domain,
            intent=intent,
            input=input,
            security_level=security_level,
            priority=priority,
            role_type=role_type,
            task_type=task_type,
            workflow_id=workflow_id,
            enabled_plugin_ids=enabled_plugin_ids,
            allowed_workflow_ids=scope.workflow_ids,
            mission_id=(self.identity_lifecycle.new_mission_id() if self.identity_lifecycle else None),
            creation_fingerprint=creation_fingerprint,
            creation_key=creation_key,
        )
        if (
            self.identity_lifecycle is not None
            and task.recommended_workflow
        ):
            if defer_identity_projection:
                # The async mission endpoint still needs the canonical Mission
                # row before prepare_run() allocates a Run id.  Apply only this
                # single projection here; defer the full outbox reconciliation.
                self.identity_lifecycle.on_mission_created(task)
            else:
                recommended = self.workflow_registry.get(task.recommended_workflow)
                if recommended.effective_runtime_engine == "acg":
                    self._flush_identity_outbox()
        return task

    async def start(
        self,
        mission_id: str,
        workflow_id: Optional[str] = None,
        review_mode: str = "auto",
        enabled_plugin_ids: Optional[list[str]] = None,
    ) -> RuntimeRunRecord:
        """为任务选择工作流并启动运行；持久化和同运行互斥由内部运行锁协调。"""
        _, run = self.prepare_run(
            mission_id=mission_id,
            workflow_id=workflow_id,
            review_mode=review_mode,
            enabled_plugin_ids=enabled_plugin_ids,
        )
        return await self.execute_prepared_run(run.run_id)

    def prepare_run(
        self,
        mission_id: str,
        workflow_id: Optional[str] = None,
        review_mode: str = "auto",
        *,
        idempotency_key: Optional[str] = None,
        idempotency_fingerprint: Optional[str] = None,
        enabled_plugin_ids: Optional[list[str]] = None,
        defer_acg_planning: bool = False,
        input_override: Optional[dict] = None,
        parent_run_id: Optional[str] = None,
        rerun_reason: Optional[str] = None,
        persist_run: bool = True,
        execution_scope_override: RunExecutionScope | None = None,
        semantic_principal: SemanticPrincipal | None = None,
        inherit_parent_basis: bool = False,
        mission_revision_decision: dict | None = None,
    ) -> tuple[RuntimeMissionRecord, RuntimeRunRecord]:
        """Freeze authorized Mission input before synchronous or deferred planning."""
        if self.planning_commit_authority is not None:
            defer_acg_planning = True
        if self.mission_semantic_service is not None:
            if semantic_principal is None and self.semantic_principal_provider is not None:
                semantic_principal = self.semantic_principal_provider()
            if semantic_principal is None:
                raise PermissionError("trusted semantic principal is required to prepare a Run")
            self.mission_semantic_service.require_read_access(semantic_principal, mission_id)
        if idempotency_key:
            existing = self.workflow_store.find_run_by_idempotency_key(idempotency_key)
            if existing is not None:
                if existing.mission_id != mission_id:
                    raise ValueError("idempotency key belongs to another Mission")
                if existing.idempotency_fingerprint != idempotency_fingerprint:
                    raise ValueError("idempotency key conflicts with the workflow start request")
                return self.mission_manager.get_mission(existing.mission_id), existing

        task = self.mission_manager.get_mission(mission_id)
        if task.record_state is not MissionRecordState.ACTIVE:
            raise ValueError("mission must be active before preparing a new run")
        if parent_run_id:
            parent_run = self.workflow_store.get_run(parent_run_id)
            if parent_run.mission_id != mission_id:
                raise ValueError("parent run must belong to the same mission")
        requested_plugins = (
            enabled_plugin_ids
            if enabled_plugin_ids is not None
            else task.enabled_plugin_ids
        )
        resolved_plugins = self.plugin_scope_resolver.resolve_enabled_plugin_ids(
            requested_plugins,
            workflow_id=workflow_id or task.recommended_workflow,
            domain=task.domain,
            intent=task.intent,
        )
        scope = self.plugin_scope_resolver.build_scope(resolved_plugins)
        if execution_scope_override is not None:
            self.plugin_scope_resolver.validate_snapshot(execution_scope_override)
            scope = execution_scope_override.model_copy(deep=True)
        workflow = self._resolve_workflow(
            task,
            workflow_id,
            allowed_workflow_ids=scope.workflow_ids,
        )
        is_acg = workflow.effective_runtime_engine == "acg"
        if is_acg and self.require_planner_identity and self.identity_lifecycle is None:
            raise ValueError(
                "production ACG execution requires the identity lifecycle adapter"
            )
        if self.identity_lifecycle is not None and is_acg and not defer_acg_planning:
            # A task may have been created against a legacy/default workflow and
            # explicitly rebound to ACG only when the run is prepared.
            self.workflow_store.save_mission(task)
            self._flush_identity_outbox()
        run_input = dict(task.input)
        if input_override is not None:
            run_input.update(input_override)
        workspace_authority = getattr(self, 'workspace_authority', None)
        if workspace_authority is not None:
            if parent_run_id:
                parent_workspace_run = self.workflow_store.get_run(parent_run_id)
                workspace_authority.resolve(parent_workspace_run)
                if 'workspaceBinding' in parent_workspace_run.input:
                    run_input['workspaceBinding'] = deepcopy(parent_workspace_run.input['workspaceBinding'])
                else:
                    # Legacy Python Runs have no directory snapshot; a new Run
                    # freezes the authenticated user's current selection.
                    workspace_authority.freeze(run_input)
            else:
                workspace_authority.freeze(run_input)
        basis = None
        if inherit_parent_basis:
            if not parent_run_id:
                raise ValueError("basis inheritance requires a parent Run")
            parent = self.workflow_store.get_run(parent_run_id)
            if parent.mission_id != mission_id:
                raise ValueError("basis parent belongs to another Mission")
            basis = run_intent_basis(parent)
        elif self.mission_semantic_service is not None:
            view = MissionSemanticResolver.resolve(
                self.mission_semantic_service.get_effective_snapshot(semantic_principal, mission_id)
            )
            basis = MissionSemanticResolver.freeze(view, legacy_input=run_input,
                legacy_title=task.title, allow_legacy=self.allow_legacy_mission_intent)
        if basis is not None and basis.source_type == "SEMANTIC" and run_input.get("acgBlueprint"):
            if not inherit_parent_basis or any(run_input.get(k) != (
                    parent.acg_blueprint if k == "acgBlueprint" else parent.execution_state.get(k))
                    for k in ("acgBlueprint", "taskPlan", "taskBindings")):
                raise ValueError("explicit semantic plans require an unchanged trusted parent package")
        if mission_revision_decision is not None:
            from contracts.mission_revision import MissionRevisionConflict
            if (basis is None or basis.source_type != "SEMANTIC" or
                    basis.source_revision != mission_revision_decision["targetRevision"]):
                raise MissionRevisionConflict("REVISION_CONFLICT")
        if run_input.get("taskAcceptance") is None:
            run_input.pop("taskAcceptance", None)
        if "taskAcceptance" in run_input:
            from contracts.task_acceptance import TaskAcceptanceSpec
            if not is_acg:
                raise ValueError("task acceptance requires the ACG Runtime Loop")
            run_input["taskAcceptance"] = TaskAcceptanceSpec.model_validate(
                run_input["taskAcceptance"]
            ).model_dump(by_alias=True, mode="json")
        capability_profile = normalize_capability_profile(run_input.get("capabilityProfile"))
        run_input["capabilityProfile"] = capability_profile
        planning_diversity = normalize_planning_diversity(
            run_input.get("planningDiversity")
        )
        planning_seed = normalize_planning_seed(run_input.get("planningSeed"))
        if planning_diversity != "stable" and planning_seed is None:
            planning_seed = secrets.randbits(53)
        run_input["planningDiversity"] = planning_diversity
        if planning_seed is not None:
            run_input["planningSeed"] = planning_seed
        run = RuntimeRunRecord(
            **(
                {"runId": self.identity_lifecycle.new_run_id(task.mission_id)}
                if self.identity_lifecycle is not None and is_acg
                else {}
            ),
            missionId=task.mission_id,
            workflowId=workflow.workflow_id,
            domain=workflow.domain,
            runtimeEngine=workflow.effective_runtime_engine,
            implementationId=workflow.effective_implementation_id,
            reviewMode=review_mode,
            input=run_input,
            lifecyclePhase=WorkflowProgressPhase.UNDERSTANDING,
            lifecycleMessage=_LIFECYCLE_MESSAGES[WorkflowProgressPhase.UNDERSTANDING],
            idempotencyKey=idempotency_key,
            idempotencyFingerprint=idempotency_fingerprint,
            currentStepId=None if is_acg else workflow.first_step_id(),
            steps=(
                []
                if is_acg
                else [WorkflowStep.from_definition(step) for step in workflow.steps]
            ),
            enabledPluginIds=list(scope.enabled_plugin_ids),
            resolvedEnabledPluginIds=list(scope.enabled_plugin_ids),
            pluginSnapshot=list(scope.plugin_snapshots),
            capabilityCatalogRevision=scope.capability_catalog_revision,
            planningDiversity=planning_diversity,
            planningSeed=planning_seed,
            plannerAlgorithmVersion=PLANNER_ALGORITHM_VERSION,
            executionScope=scope,
            legacyPluginScope=False,
            executionState={
                **({"missionRevisionDecision": mission_revision_decision} if mission_revision_decision else {}),
                **({"missionIntentBasis": basis.model_dump(by_alias=True, mode="json")} if basis is not None else {}),
                **({"taskAcceptance": deepcopy(run_input["taskAcceptance"])} if "taskAcceptance" in run_input else {}),
                **({"engineMigration": "langgraph_pending"} if is_acg else {}),
                **({"parentRunId": parent_run_id, "sourceRunId": parent_run_id} if parent_run_id else {}),
                **({"rerunReason": rerun_reason} if rerun_reason else {}),
                "pluginScopeResolution": (
                    "legacy_compatibility" if requested_plugins is None else "explicit"
                ),
                "visibleCapabilityCount": len(scope.capability_ids),
                "scopeExcludedAgentCount": max(
                    0, len(tuple(self.agent_registry.all())) - len(scope.agent_ids)
                ),
                "planningDiversity": planning_diversity,
                "requestedCapabilityProfile": capability_profile,
                "planningSeed": planning_seed,
                "plannerAlgorithmVersion": PLANNER_ALGORITHM_VERSION,
            },
        )
        if (workflow.domain or task.domain).strip().lower() == "general":
            active_evolution = self.evolution_service.store.active()
            run.execution_state["evolutionPolicyVersion"] = active_evolution.version
            run.execution_state["evolutionPolicy"] = dict(active_evolution.policy)
        if is_acg and defer_acg_planning:
            run.execution_state["planningDeferred"] = True
            if self.planning_commit_authority is not None:
                run.execution_state["planningCommitRequired"] = True
        elif is_acg:
            self._materialize_acg_run(task=task, run=run, workflow=workflow, scope=scope)
        self.trace_store.append(
            run=run,
            event_type=TraceEventType.TASK_STATUS_CHANGED,
            observation="Plugin execution scope resolved",
            payload={
                "resolvedEnabledPluginIds": list(scope.enabled_plugin_ids),
                "pluginSnapshot": [
                    item.model_dump(by_alias=True, mode="json")
                    for item in scope.plugin_snapshots
                ],
                "capabilityCatalogRevision": scope.capability_catalog_revision,
                "visibleCapabilityCount": len(scope.capability_ids),
                "scopeExcludedAgentCount": run.execution_state[
                    "scopeExcludedAgentCount"
                ],
                "resolutionPolicy": run.execution_state[
                    "pluginScopeResolution"
                ],
            },
        )
        if persist_run:
            if idempotency_key:
                run = self.workflow_store.save_prepared_run_once(run)
            else:
                self.workflow_store.save_run(run)
        if (
            persist_run
            and
            self.identity_lifecycle is not None
            and is_acg
            and not defer_acg_planning
        ):
            self._flush_identity_outbox()
        logger.info(
            "run_prepared",
            extra={
                "missionId": task.mission_id,
                "runId": run.run_id,
                "workflowId": workflow.workflow_id,
                "phase": run.lifecycle_phase.value,
            },
        )
        return task, run

    def prepare_node_rerun(self, source_run_id: str, step_id: str, **kwargs) -> RuntimeRunRecord:
        """Create a successor with the selected dependency cut invalidated."""
        with self.run_lock_manager.lock_for(source_run_id):
            return self.runtime_recovery_coordinator.prepare_single_step_retry(
                source_run_id, step_id, restart_from_step=True, **kwargs,
            )

    def prepare_single_step_retry(
        self,
        source_run_id: str,
        step_id: str,
        *,
        reason: str = "operator_requested",
        expected_runtime_revision: int | None = None,
        idempotency_key: str | None = None,
        idempotency_fingerprint: str | None = None,
        reuse_source_run: bool = False,
    ) -> RuntimeRunRecord:
        """Prepare a successor Run that resumes from a failed ACG step.

        Run 锁由本入口持有；继任 Run 的应用逻辑（状态种子、引用复用、投影账
        目回填）在 RuntimeRecoveryCoordinator 中实现。锁外幂等快路径由锁内的
        同条件复查覆盖，语义与迁移前一致。
        """
        with self.run_lock_manager.lock_for(source_run_id):
            return self.runtime_recovery_coordinator.prepare_single_step_retry(
                source_run_id,
                step_id,
                reason=reason,
                expected_runtime_revision=expected_runtime_revision,
                idempotency_key=idempotency_key,
                idempotency_fingerprint=idempotency_fingerprint,
                reuse_source_run=reuse_source_run,
            )

    def _materialize_acg_run(
        self,
        *,
        task: RuntimeMissionRecord,
        run: RuntimeRunRecord,
        workflow: WorkflowDefinition,
        scope: RunExecutionScope,
    ) -> None:
        """Run the existing L1-L3 plan/build/compile path for one persisted Run."""
        if run.execution_state.get("planningCommitRequired"):
            if self.planning_commit_authority is None:
                raise ValueError("Planning Commit authority is required for this Run")
            receipt = self.planning_commit_authority.accept_initial(run.run_id)
            if receipt.status == "REJECTED":
                raise ValueError(f"Planning Commit rejected: {receipt.code.value}")
            return
        frozen_task_acceptance(run)
        provided_explicit = run.input.get("acgBlueprint") or run.acg_blueprint or None
        explicit_blueprint = isinstance(provided_explicit, dict) and bool(provided_explicit.get("nodes"))
        # 显式 Blueprint 兼容入口（必须同时提供 taskPlan/bindings）没有 Planner
        # 运行，绝不能伪造 planner started/parsed/compiled/completed 事件。
        blueprint, task_plan, task_bindings = self._build_acg_blueprint(
            task,
            run,
            workflow,
        )
        if task_plan is not None:
            basis = run_intent_basis(run)
            if basis is not None:
                if explicit_blueprint and basis.source_type == "SEMANTIC" and task_plan.metadata.get("missionIntentBasisRef") != basis.reference():
                    raise ValueError("explicit TaskPlan is not bound to the Run's Mission basis")
                task_plan = task_plan.model_copy(deep=True,
                    update={"metadata": {**task_plan.metadata, "missionIntentBasisRef": basis.reference()}})
            if self.identity_lifecycle is not None:
                resolve_snapshot = getattr(self.identity_lifecycle, "resolve_task_plan_snapshot", None)
                if callable(resolve_snapshot):
                    task_plan = resolve_snapshot(task_plan)
            validate_bound_acg_semantics(
                task_plan, blueprint, task_bindings, require_exact=True,
            )
        self.runtime_binding_service.validate_blueprint_agents(
            blueprint,
            domain=workflow.domain or task.domain,
            scope=scope,
        )
        self._sync_run_steps_to_acg(run, blueprint)
        compiled_package = ACGGraphCompiler().compile_package(blueprint, run_id=run.run_id)
        if task_plan is not None and not explicit_blueprint:
            # 计数取自编译产物 CompiledACGPackage（已过滤 retired 与资源节点），
            # 而非编译输入 Blueprint；compiler 未来插入节点时这里自动跟随最终图。
            self._append_planner_event(run, {
                "kind": "graph_compiled",
                "nodeCount": len(compiled_package.nodes),
                "edgeCount": len(compiled_package.edges),
            })
        self.runtime_binding_service.prepare(
            run=run,
            workflow=workflow,
            scope=scope,
            binding_manifest=compiled_package.binding_manifest,
        )
        run.acg_blueprint = blueprint.model_dump(by_alias=True, mode="json")
        run.execution_state.update(
            {
                "workflowVersion": workflow.version,
                "graphId": blueprint.graph_id,
                "sourceBlueprintVersion": blueprint.version,
                "compiledACGPackage": compiled_package.model_dump(
                    by_alias=True, mode="json"
                ),
                "compiledPackageId": compiled_package.package_id,
                "compiledPackageChecksum": compiled_package.checksum,
                "compiledPackageVersion": compiled_package.package_version,
                "compiledPackageBlueprintHash": compiled_package.blueprint_hash,
                **(
                    {
                        "taskPlanVersion": task_plan.plan_version,
                        "taskPlan": task_plan.model_dump(by_alias=True, mode="json"),
                        "taskBindings": [
                            item.model_dump(by_alias=True, mode="json")
                            for item in task_bindings
                        ],
                    }
                    if task_plan is not None
                    else {}
                ),
            }
        )
        if self.identity_lifecycle is not None and task_plan is None:
            raise ValueError("identity-enabled ACG execution requires Planner output")
        if run.execution_state.get("taskAcceptance") is not None and task_plan is None:
            raise ValueError("task acceptance requires a persisted TaskPlan")
        run.execution_state.pop("planningDeferred", None)
        self.runtime_planning_coordinator.initialize(run)
        if task_plan is not None and not explicit_blueprint:
            self._append_planner_event(run, {"kind": "completed"})

    def _materialize_deferred_acg_run(self, run_id: str) -> RuntimeRunRecord:
        run = self.workflow_store.get_run(run_id)
        if not run.execution_state.get("planningDeferred"):
            return run
        self._raise_if_run_cancelled(run_id)
        task = self.mission_manager.get_mission(run.mission_id)
        workflow = self._workflow_for_run(run)
        scope = run.execution_scope
        if scope is None:
            raise ValueError("deferred ACG planning requires a frozen execution scope")
        self._materialize_acg_run(task=task, run=run, workflow=workflow, scope=scope)
        if run.execution_state.get("planningCommitRequired"):
            # Acceptance persisted only ledger/outbox. Never save the worker's
            # pre-planning Run snapshot over later operator/lifecycle changes.
            return self.workflow_store.get_run(run_id)
        # Planning runs in a worker thread. Re-check and commit under the same
        # short run lock used by cancel(), otherwise a stale planner snapshot
        # can overwrite CANCELLED and hand the run back to the executor.
        with self.run_lock_manager.lock_for(run_id):
            latest = self.workflow_store.get_run(run_id)
            if latest.status in _TERMINAL_RUN_STATUSES or self._run_cancellation_requested(run_id):
                return latest
            self.workflow_store.save_run(run)
        if self.identity_lifecycle is not None:
            self._flush_identity_outbox()
        return run

    async def execute_prepared_run(self, run_id: str) -> RuntimeRunRecord:
        """执行已持久化运行并保持终态不回退；插件范围失效时安全标记失败后继续抛错。"""

        run = self.workflow_store.get_run(run_id)
        if self._normalize_runtime_engine(run.runtime_engine) == "acg":
            if run.execution_state.get("planningCommitRequired") and self.planning_commit_authority is None:
                return run
            if run.status in _TERMINAL_RUN_STATUSES:
                return run
            if run.status == WorkflowStatus.WAITING_REVIEW:
                return run
            if (run.execution_state.get("executionPermitId")
                    and self.execution_permit_authority is not None):
                run = self.reconcile_execution_checkpoint(run_id)
            if run.execution_state.get("planningDeferred"):
                self._cancellation_event(run.run_id)
                run = self._set_run_lifecycle(
                    run,
                    status=WorkflowStatus.PLANNING,
                    phase=WorkflowProgressPhase.PLANNING,
                    message=_LIFECYCLE_MESSAGES[WorkflowProgressPhase.PLANNING],
                    set_started_at=True,
                )
                self.workflow_store.save_run(run)
                try:
                    run = await asyncio.to_thread(
                        self._materialize_deferred_acg_run,
                        run.run_id,
                    )
                except ExecutionRunCancelled:
                    self._discard_run_cancellation(run.run_id)
                    return self.workflow_store.get_run(run.run_id)
                except BaseException:
                    self._discard_run_cancellation(run.run_id)
                    raise
                if run.status in _TERMINAL_RUN_STATUSES or self._run_cancellation_requested(run.run_id):
                    latest = self.workflow_store.get_run(run.run_id)
                    self._discard_run_cancellation(run.run_id)
                    return latest
                if run.execution_state.get("planningDeferred"):
                    return run  # accepted planning fact; no graph has been materialized
            retry_state = (
                acg_execution_state_from_run(run)
                if (
                    isinstance(run.execution_state.get("singleStepRetry"), dict)
                    or isinstance(run.execution_state.get("checkpointResume"), dict)
                    or isinstance(run.execution_state.get("inPlaceRetry"), dict)
                    or isinstance(run.execution_state.get("planningLoop"), dict)
                )
                else None
            )
            permit_projection = (run.execution_state.get("graphActivation") or {}).get("executionPermit")
            if isinstance(permit_projection, dict):
                checkpoint_id = run.execution_state.get("checkpointId")
                if not isinstance(checkpoint_id, str) or checkpoint_id != permit_projection.get("checkpointId"):
                    # Once execution has advanced, the Run may reference a later
                    # checkpoint; the immutable permit remains bound to the
                    # promoted initial checkpoint and generation in every state.
                    if not isinstance(checkpoint_id, str):
                        raise ValueError("permitted Run has no explicit recovery checkpoint")
                payload = self.checkpoint_store.load(run_id=run.run_id, checkpoint_id=checkpoint_id)
                if payload is None:
                    raise ValueError("permitted Run checkpoint is missing")
                retry_state = ACGExecutionState.model_validate(payload)
                if (retry_state.execution_permit_id != run.execution_state.get("executionPermitId")
                        or retry_state.execution_generation != run.execution_state.get("executionGeneration")):
                    raise ValueError("permitted Run checkpoint belongs to another execution generation")
            return await self._execute_acg(run, state=retry_state)
        if run.status in _TERMINAL_RUN_STATUSES:
            return run

        task = self.mission_manager.get_mission(run.mission_id)
        try:
            workflow = self._workflow_for_run(run)
        except PluginScopeError as exc:
            await self.fail_run_safely(
                run.run_id,
                error_code=exc.code,
                error_message=exc.detail,
            )
            raise
        started = monotonic()
        run = self._set_run_lifecycle(
            run,
            status=WorkflowStatus.RUNNING,
            phase=WorkflowProgressPhase.PLANNING,
            message=_LIFECYCLE_MESSAGES[WorkflowProgressPhase.PLANNING],
            set_started_at=True,
        )
        try:
            self.mission_manager.mark_running(task)
            adapter = self._workflow_adapter(workflow)
            return await adapter.start(task=task, run=run, workflow=workflow)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self.fail_run_safely(
                run.run_id,
                error_code="workflow_execution_failed",
                error_message=self._safe_error_message(exc),
            )
            logger.exception(
                "run_execution_failed",
                extra={"missionId": run.mission_id, "runId": run.run_id, "elapsedMs": int((monotonic() - started) * 1000)},
            )
            raise

    async def _execute_acg(
        self,
        run: RuntimeRunRecord,
        *,
        state: ACGExecutionState | None = None,
        command: ExecutionResumeCommand | None = None,
    ) -> RuntimeRunRecord:
        """ACG 执行入口：认领单执行槽并管理取消信号生命周期。

        并发重复入口（如同时 resume 同一检查点）在此被确定性拒绝；执行体由
        ``ACGExecutionService.execute`` 承载。
        """
        if run.status in _TERMINAL_RUN_STATUSES:
            return run
        if run.execution_state.get("planningCommitRequired") and self.planning_commit_authority is None:
            return run
        self._claim_acg_execution(run)
        while True:
            executed_run_id = run.run_id
            try:
                result = await self.acg_execution_service.execute(run, state=state, command=command)
            finally:
                self._release_execution_slot(executed_run_id)
                self._discard_run_cancellation(executed_run_id)
            successor_id = result.execution_state.get("supersededByRunId")
            if result.status == WorkflowStatus.SUPERSEDED and successor_id and isinstance(result.execution_state.get("planningLoop"), dict):
                run = self.workflow_store.get_run(successor_id)
            elif result.status == WorkflowStatus.RETRYING and isinstance(result.execution_state.get("planningLoop"), dict):
                run = result
            else:
                return result
            self._claim_acg_execution(run)
            state = acg_execution_state_from_run(run)
            command = None

    def _claim_acg_execution(self, run: RuntimeRunRecord) -> None:
        """Fence every initial/retry/successor execution before claiming a slot."""
        # Serialize the durable execution fence and slot claim against activation.
        # A head is authoritative even if its optional Run projection was lost.
        from contextlib import ExitStack
        from support.run_execution_fence import acquire_run_fence
        with self.run_lock_manager.lock_for(run.run_id), ExitStack() as lifetime:
            from support.stores.graph_activation_store import validate_activation_run
            from support.stores.memory_workflow_store import MemoryWorkflowStore
            if isinstance(self.workflow_store, MemoryWorkflowStore):
                # This legacy backend has no durable activation capability. It
                # cannot be used to resume an activation projection or authority.
                latest = self.workflow_store.get_run(run.run_id)
                if self.graph_activation_authority is not None or "graphActivation" in latest.execution_state:
                    raise ValueError("durable activation evidence unavailable in the memory backend")
            else:
                # Hold the same OS fence as activation BEFORE reading the Head,
                # and retain it through the full executor lifetime. A snapshot
                # write rejection after an external call is too late a fence.
                lifetime.enter_context(acquire_run_fence(self.workflow_store.db_path, run.run_id))
                with self.workflow_store._connect() as conn:
                    conn.row_factory = sqlite3.Row
                    conn.execute("BEGIN")
                    row = conn.execute("SELECT payload FROM runs WHERE run_id=?", (run.run_id,)).fetchone()
                    latest = RuntimeRunRecord.model_validate_json(row["payload"])
                    head = validate_activation_run(conn, latest)
                    if head is not None:
                        if self.execution_permit_authority is None:
                            raise ValueError("activated but paused; no execution permit authority is attached")
                        self.execution_permit_authority.assert_dispatchable(latest)
                        if self.execution_dispatch_enabled:
                            dispatch = self.execution_dispatch_store
                            if dispatch is None or dispatch.db_path != self.workflow_store.db_path.resolve():
                                raise ValueError("Dispatch admission store is unavailable or belongs to another ledger")
                            principal = self.semantic_principal_provider() if self.semantic_principal_provider else None
                            dispatch.assert_admitted(conn, latest, principal)
                        # Covers every execution entry, including legacy
                        # checkpoint resume and Review, before claiming a slot.
                        from runtime.permit_recovery import assert_settled_operations
                        assert_settled_operations(self, latest)
                        supplied_permit = (run.execution_state.get("graphActivation") or {}).get("executionPermit")
                        current_permit = (latest.execution_state.get("graphActivation") or {}).get("executionPermit")
                        if supplied_permit != current_permit:
                            raise ExecutionStateChanged("execution permit changed while the executor was starting")
            if (isinstance(latest.acg_blueprint, dict) and isinstance(run.acg_blueprint, dict)
                    and latest.acg_blueprint.get("version") != run.acg_blueprint.get("version")):
                raise ExecutionStateChanged("run graph version changed while the executor was starting")
            frozen_task_acceptance(run)
            if not self._claim_execution_slot(run.run_id):
                raise ValueError(f"run {run.run_id} already has an active execution")
            with self._execution_slot_guard:
                self._execution_fences[run.run_id] = lifetime.pop_all()

    def _save_runtime_planning_round(self, run: RuntimeRunRecord) -> None:
        """Model calls run outside the lock; stale/cancelled decisions cannot commit."""
        with self.run_lock_manager.lock_for(run.run_id):
            self._assert_runtime_planning_current(run)
            if self.planning_commit_authority is not None:
                run.execution_state["planningCommitRequired"] = True
            run.runtime_revision += 1
            run.updated_at = utc_now()
            self.workflow_store.save_run(run)

    def enable_planning_commit(self, store) -> None:
        """Explicitly attach an already-upgraded ledger; never run schema DDL."""
        from runtime.planning_commit import RuntimePlanningCommitAuthority
        self.planning_commit_authority = RuntimePlanningCommitAuthority(runtime=self, store=store)

    def enable_graph_materialization(self, store) -> None:
        """Explicit server assembly only; never initialize or migrate a database."""
        from runtime.graph_materialization import GraphMaterializationAuthority
        self.graph_materialization_authority = GraphMaterializationAuthority(self, store)

    def enable_graph_activation(self, store) -> None:
        """Explicit server assembly only; never initialize or migrate a database."""
        from runtime.graph_activation import GraphActivationAuthority
        self.graph_activation_authority = GraphActivationAuthority(self, store)

    def enable_graph_handoff(self, store, staged_checkpoint_store) -> None:
        """Attach explicitly upgraded handoff stores; never issue a permit."""
        from runtime.graph_handoff import GraphHandoffAuthority
        self.graph_handoff_authority = GraphHandoffAuthority(self, store, staged_checkpoint_store)

    def reconcile_execution_checkpoint(self, run_id):
        """Acknowledge only a proven settled checkpoint; never execute here."""
        if self.execution_permit_authority is None:
            raise ValueError("execution Permit authority is required for reconciliation")
        from runtime.permit_recovery import reconcile_checkpoint
        return reconcile_checkpoint(self.execution_permit_authority, run_id)

    def enable_execution_permit(self, store) -> None:
        """Attach an explicitly upgraded permit ledger; no DDL or auto-issuance."""
        from runtime.execution_permit import ExecutionPermitAuthority
        self.execution_permit_authority = ExecutionPermitAuthority(self, store)

    def issue_execution_permit(self, handoff_id, *, idempotency_key):
        """Promote a verified staged checkpoint and issue one explicit graph permit."""
        if self.execution_permit_authority is None:
            from runtime.execution_permit import rejected
            return rejected("AUTHORITY_DENIED", "execution permit authority unavailable")
        return self.execution_permit_authority.issue(handoff_id, idempotency_key=idempotency_key)

    def prepare_graph_handoff(self, activation_id, *, idempotency_key):
        """Prepare a staged execution state; no recovery head or Run mutation."""
        if self.graph_handoff_authority is None:
            from runtime.graph_handoff import rejected
            return rejected("AUTHORITY_DENIED", "graph handoff authority unavailable")
        return self.graph_handoff_authority.prepare(activation_id, idempotency_key=idempotency_key)

    def prepare_graph_activation(self, materialization_id, *, idempotency_key):
        """Persist one verified activation preparation; never switch the graph."""
        if self.graph_activation_authority is None:
            from runtime.graph_activation import rejected
            from contracts.planning_commit import PlanningCommitRejectionCode
            return rejected(PlanningCommitRejectionCode.AUTHORITY_DENIED, "graph activation authority unavailable")
        return self.graph_activation_authority.prepare(materialization_id, idempotency_key=idempotency_key)

    def commit_graph_activation(self, materialization_id, *, idempotency_key):
        """Atomically switch the formal GraphVersion head and Run projection.

        The activated graph stays paused: no execution permit is issued here
        and every scheduling entry point keeps refusing the Run.
        """
        if self.graph_activation_authority is None:
            from runtime.graph_activation import rejected
            from contracts.planning_commit import PlanningCommitRejectionCode
            return rejected(PlanningCommitRejectionCode.AUTHORITY_DENIED, "graph activation authority unavailable")
        return self.graph_activation_authority.commit(materialization_id, idempotency_key=idempotency_key)

    def materialize_graph_revision(self, commit_id, *, idempotency_key):
        """Persist an inactive package; no graph activation or execution."""
        if self.graph_materialization_authority is None:
            from runtime.graph_materialization import rejected
            from contracts.planning_commit import PlanningCommitRejectionCode
            return rejected(PlanningCommitRejectionCode.AUTHORITY_DENIED, "materialization authority unavailable")
        return self.graph_materialization_authority.materialize(commit_id, idempotency_key=idempotency_key,
                                                               source_kind="graph_revision")

    def materialize_initial_commit(self, commit_id, *, idempotency_key):
        """Explicit host entry; the same materialization authority owns both sources."""
        from contracts.planning_commit import PlanningCommitRejectionCode
        if self.graph_materialization_authority is None:
            from runtime.graph_materialization import rejected
            return rejected(PlanningCommitRejectionCode.AUTHORITY_DENIED, "materialization authority unavailable")
        return self.graph_materialization_authority.materialize(commit_id, idempotency_key=idempotency_key,
                                                               source_kind="initial_plan")

    def accept_graph_revision(self, run_id, source_commit_id, *, idempotency_key):
        """Explicit server-side acceptance; never materialize or apply a graph."""
        if self.planning_commit_authority is None:
            from contracts.planning_commit import PlanningCommitRejection, PlanningCommitRejectionCode
            return PlanningCommitRejection(code=PlanningCommitRejectionCode.AUTHORITY_DENIED,
                                           reason="Planning Commit authority is unavailable")
        return self.planning_commit_authority.accept_graph_revision(
            run_id, source_commit_id, idempotency_key=idempotency_key)

    def _mark_planning_commit_required(self, run) -> None:
        """Orchestration fence, outside the Commit service; caller holds Run lock."""
        if run.execution_state.get("planningCommitRequired"):
            return
        principal = self.semantic_principal_provider() if self.semantic_principal_provider else None
        if self.mission_semantic_service is None or principal is None:
            raise PermissionError("trusted planning authority is required")
        self.mission_semantic_service.require_write_access(principal, run.mission_id)
        if run.active_step_ids or any(s.status in {StepStatus.RUNNING, StepStatus.RETRYING} for s in run.steps):
            raise ValueError("planning mode cannot change while work is active")
        self._assert_runtime_planning_current(run)
        run.execution_state["planningCommitRequired"] = True
        run.runtime_revision += 1
        run.updated_at = utc_now()
        self.workflow_store.save_run(run)

    def require_planning_commit(self, run_id) -> None:
        """Explicitly opt an existing quiescent Run into fail-closed acceptance."""
        if self.planning_commit_authority is None:
            raise ValueError("Planning Commit authority is required")
        with self.run_lock_manager.lock_for(run_id):
            self._mark_planning_commit_required(self.workflow_store.get_run(run_id))

    async def _gate_planning_commit_decision(self, run, observation, decision):
        """Persist only wait after acceptance, so restart cannot adopt a revision."""
        if decision.action != "revise":
            return decision
        if self.planning_commit_authority is None and not run.execution_state.get("planningCommitRequired"):
            return decision
        from contracts.runtime_planning import RuntimePlanningDecision
        async with self.run_lock_manager.lock_for(run.run_id):
            self._assert_runtime_planning_current(run)
            if self.planning_commit_authority is None:
                reason = "Planning Commit authority unavailable; revision remains unaccepted"
            else:
                try:
                    self._mark_planning_commit_required(run)
                    self.runtime_planning_coordinator.validate_decision(observation, decision)
                    receipt = self.planning_commit_authority.accept_patch_locked(run.run_id, decision.task_plan_patch,
                        proposal_id="runtime:" + observation.fingerprint(),
                        idempotency_key="runtime-planning:" + run.run_id + ":" + observation.fingerprint())
                    reason = (f"Planning Commit {receipt.commit_id} accepted; awaiting materialization"
                              if receipt.status != "REJECTED" else f"Planning Commit rejected: {receipt.code.value}")
                except (ValueError, KeyError, PermissionError) as exc:
                    reason = f"Planning Commit rejected: {type(exc).__name__}"
        return RuntimePlanningDecision(observationId=observation.fingerprint(), action="wait", reason=reason)

    async def _resume_pending_commit_wait(self, run, state, loop):
        """Finish a durable acceptance barrier before refreshing volatile observations."""
        current = loop.current
        authority = self.planning_commit_authority
        if (authority is None or current is None or current.status not in {"observed", "decided"}
                or (current.decision is not None and (current.decision.action != "wait"
                    or current.decision.wait_for is not None or current.decision.question is not None))
                or not run.execution_state.get("planningCommitRequired")):
            return None
        record = authority.store.get_by_idempotency_key("runtime-planning:" + run.run_id + ":" + current.observation_id)
        if (record is None or record.mission_id != run.mission_id
                or record.proposal_type != "plan_revision"
                or record.sources.observation_id != current.observation_id
                or record.proposal_id != authority.proposal_identity(run.run_id, "runtime:" + current.observation_id)):
            return None
        self._validate_acg_state_references(run=run, state=state)
        from contracts.runtime_planning import RuntimePlanningDecision
        decision = current.decision or RuntimePlanningDecision(observationId=current.observation_id,
            action="wait", reason=f"Planning Commit {record.commit_id} accepted; awaiting materialization")
        applied = loop.model_copy(update={"current": current.model_copy(update={"status": "applied", "decision": decision})})
        async with self.run_lock_manager.lock_for(run.run_id):
            # Completing a plain wait neither accepts new facts nor executes work.
            # Keep the independent operator inbox unconsumed for the next review;
            # its arrival must not indefinitely block this crash-recovery barrier.
            self._assert_runtime_planning_current(run, allow_unconsumed_operator_input=True)
            return self.runtime_planning_application.apply(run, state, current.observation, decision, applied)

    def _assert_runtime_planning_current(self, run: RuntimeRunRecord, *, allow_unconsumed_operator_input=False) -> None:
        latest = self.workflow_store.get_run(run.run_id)
        if latest.status in _TERMINAL_RUN_STATUSES or self._run_cancellation_requested(run.run_id):
            raise ExecutionRunCancelled("runtime planning stopped by terminal lifecycle")
        if latest.runtime_revision != run.runtime_revision:
            raise ExecutionStateChanged("runtime changed while Planner was deciding")
        known = {(i.get("sourceRunId"), i.get("operationId")) for i in (run.execution_state.get("planningLoop") or {}).get("userInputs", [])}
        if (not allow_unconsumed_operator_input
                and any((i["sourceRunId"], i["operationId"]) not in known for i in self.workflow_store.list_planning_inputs(run.run_id))):
            raise ExecutionStateChanged("operator input arrived while Planner was deciding")

    async def _apply_runtime_planning_decision(self, run, state, observation, decision, loop) -> str:
        """Retain lifecycle locking; deterministic application lives in its service."""
        if decision.action == "revise" and (self.planning_commit_authority is not None
                or run.execution_state.get("planningCommitRequired")):
            decision = await self._gate_planning_commit_decision(run, observation, decision)
            if loop.current is not None:
                loop = loop.model_copy(update={"current": loop.current.model_copy(update={"decision": decision})})
        async with self.run_lock_manager.lock_for(run.run_id):
            self._assert_runtime_planning_current(run)
            return self.runtime_planning_application.apply(run, state, observation, decision, loop)

    def _project_acg_event(
        self, run: RuntimeRunRecord, state: ACGExecutionState, event: dict
    ) -> None:
        """委托执行服务投影单个图事件；保留既有调用点的稳定接缝。"""
        self.acg_execution_service._project_event(run, state, event)

    def _validate_acg_state_references(
        self,
        *,
        run: RuntimeRunRecord,
        state: ACGExecutionState,
        ledger: ProvenanceLedger | None = None,
    ) -> None:
        """委托执行服务校验引用归属；审核恢复路径与本入口共用同一实现。"""
        self.acg_execution_service.validate_state_references(
            run=run, state=state, ledger=ledger
        )

    def _flush_identity_outbox(self, *, raise_on_failure: bool = True) -> None:
        if self.identity_lifecycle is None:
            return
        from runtime.v2.reconciliation import IdentityProjectionReconciler

        report = IdentityProjectionReconciler(self.identity_lifecycle).project_pending_events(
            self.workflow_store,
            limit=200,
        )
        if report.failures and raise_on_failure:
            raise RuntimeError("identity inbox consumption failed: " + "; ".join(report.failures))
        if report.failures:
            # Startup reconciliation must never block service availability:
            # failed events stay persisted for repair instead of crashing the
            # process into a restart loop (a single dead letter previously
            # took the whole Chat surface to HTTP 503).
            logger.error(
                "identity_outbox_flush_failures",
                extra={
                    "failures": report.failures[:10],
                    "deadLetterCount": report.dead_letter_count,
                },
            )

    def _inject_fault(self, stage: str) -> None:
        """调用测试专用中断钩子；正常执行没有附加分支或持久化副作用。"""
        if self._fault_hook is not None:
            self._fault_hook(stage)

    def _append_planner_event(self, run: RuntimeRunRecord, event: Mapping[str, Any]) -> None:
        """Append one planner Runtime Event as an auditable Trace entry.

        The payload whitelist is the security boundary: only scalar planning
        facts pass through, so prompt/model text can never ride along. Durable
        planner lifecycle events carry ``planningProgress`` for legacy
        projections; high-frequency model activity is transient-only.
        """
        planner_event_type = str(event.get("eventType") or "")
        payload = {
            key: value for key, value in event.items()
            if key in _PLANNER_PROGRESS_FIELDS and isinstance(value, (str, int, float, bool))
        }
        topology_audit = event.get("topologyAudit")
        if isinstance(topology_audit, Mapping):
            payload["topologyAudit"] = _safe_topology_audit(topology_audit)
        if planner_event_type == "planner.draft.updated":
            payload["nodes"] = [
                {
                    key: value
                    for key, value in item.items()
                    if key in {"key", "title", "capabilityId", "status", "rationale"}
                    and isinstance(value, str)
                }
                for item in list(event.get("nodes") or [])[:100]
                if isinstance(item, Mapping)
            ]
            payload["edges"] = [
                {
                    key: value
                    for key, value in item.items()
                    if key in {"sourceKey", "targetKey", "relationType"}
                    and isinstance(value, str)
                }
                for item in list(event.get("edges") or [])[:300]
                if isinstance(item, Mapping)
            ]
        if planner_event_type == "planner.plan.parsed" or event.get("status") == "plan_parsed":
            payload["nodes"] = [
                {
                    key: value
                    for key, value in item.items()
                    if key in {"key", "parentKey", "title", "objective", "logicalRole"}
                    and (value is None or isinstance(value, str))
                } | {
                    key: [str(nested)[:500] for nested in value[:50]]
                    for key, value in item.items()
                    if key in {"capabilityRequirements", "acceptanceCriteria", "producedArtifacts"}
                    and isinstance(value, list)
                }
                for item in list(event.get("nodes") or [])[:100]
                if isinstance(item, Mapping)
            ]
            payload["relations"] = [
                {
                    key: value
                    for key, value in item.items()
                    if key in {"sourceKey", "targetKey", "relationType"}
                    and isinstance(value, str)
                }
                for item in list(event.get("relations") or [])[:300]
                if isinstance(item, Mapping)
            ]
        if planner_event_type not in {
            "planner.started", "planner.stage.started", "planner.stage.retry",
            "planner.model.started", "planner.model.first_token",
            "planner.model.activity", "planner.model.output.delta", "planner.model.completed",
            "planner.draft.updated",
            "planner.stage.completed", "planner.profile.resolved",
            "planner.plan.parsed", "planner.graph.compiled", "planner.completed",
            "planner.failed",
        }:
            planner_event_type = {
                "started": "planner.started",
                "stage_started": "planner.stage.started",
                "stage_completed": "planner.stage.completed",
                "retry": "planner.stage.retry",
                "profile_resolved": "planner.profile.resolved",
                "plan_parsed": "planner.plan.parsed",
                "graph_compiled": "planner.graph.compiled",
                "completed": "planner.completed",
                "failed": "planner.failed",
            }.get(str(payload.get("kind")), "")
        persist_trace = bool(event.get("persistTrace", True))
        if planner_event_type:
            # Mirror planner lifecycle/activity onto the existing transient broker.
            # The planning phase is run-scoped, so node/attempt identity remains null.
            self._raise_if_run_cancelled(run.run_id)
            from contracts.runtime_events import RuntimeEvent
            from runtime.live_events import runtime_event_broker
            runtime_event_broker.publish_from_thread(
                run.run_id,
                RuntimeEvent(
                    eventType=planner_event_type,
                    runId=run.run_id,
                    nodeId=None,
                    attemptId=None,
                    sequence=0,
                    payload=payload,
                ),
            )
        if not persist_trace:
            return
        kind = str(payload.get("kind") or {
            "planner.started": "started",
            "planner.stage.started": "stage_started",
            "planner.stage.retry": "retry",
            "planner.stage.completed": "stage_completed",
            "planner.profile.resolved": "profile_resolved",
            "planner.plan.parsed": "plan_parsed",
            "planner.graph.compiled": "graph_compiled",
            "planner.completed": "completed",
            "planner.failed": "failed",
        }.get(planner_event_type, "progress"))
        stage = payload.get("stage")
        status = payload.get("status")
        observation = "Planner " + kind
        if stage:
            observation += f" [{stage}]"
        if status:
            observation += f" {status}"
        # Planning runs in a worker thread. Re-check under the same short run
        # lock used by cancel(), so a cancelled run never gets planner events
        # (or a stale snapshot save) committed over its terminal state.
        with self.run_lock_manager.lock_for(run.run_id):
            self._raise_if_run_cancelled(run.run_id)
            self.trace_store.append(
                run=run,
                event_type=TraceEventType.TASK_STATUS_CHANGED,
                observation=observation,
                payload={"planningProgress": True, "category": "planner", **payload},
            )
            self.workflow_store.save_run(run)

    @staticmethod
    def _topology_failure_audit(exc: BaseException) -> dict[str, Any]:
        current: BaseException | None = exc
        while current is not None:
            audit = getattr(current, "audit", None)
            if isinstance(audit, dict):
                return dict(audit)
            metadata = getattr(current, "metadata", None)
            if isinstance(metadata, Mapping):
                audit = metadata.get("topologyCompilation")
                if isinstance(audit, dict):
                    return dict(audit)
            current = current.__cause__
        return {}

    def _build_acg_blueprint(
        self,
        task: RuntimeMissionRecord,
        run: RuntimeRunRecord,
        workflow: WorkflowDefinition,
    ) -> tuple[
        RuntimeBlueprintSpec,
        TaskPlan | None,
        tuple[TaskImplementationBinding, ...],
    ]:
        """Resolve one complete ACG production package.

        Identity-enabled production accepts either an explicit Blueprint plus
        TaskPlan/bindings, or Planner output. The final workflow promotion branch
        is reserved for the identity-free Execution Runtime execution-kernel harness and does
        not manufacture semantic identities from WorkflowStep definitions.
        """
        provided = run.input.get("acgBlueprint") or (run.acg_blueprint if run.acg_blueprint else None)
        if isinstance(provided, dict) and provided.get("nodes"):
            blueprint = RuntimeBlueprintSpec.model_validate(provided)
            if not blueprint.mission_id:
                blueprint = blueprint.model_copy(deep=True, update={"mission_id": task.mission_id})
            raw_plan = run.input.get("taskPlan")
            raw_bindings = run.input.get("taskBindings")
            if not isinstance(raw_plan, dict) or not isinstance(raw_bindings, list):
                raise ValueError(
                    "explicit ACG Blueprint requires taskPlan and taskBindings"
                )
            task_plan = TaskPlan.model_validate(raw_plan)
            task_bindings = tuple(
                TaskImplementationBinding.model_validate(item)
                for item in raw_bindings
            )
            if task_plan.mission_id != task.mission_id:
                raise ValueError("TaskPlan missionId does not match RuntimeMissionRecord")
            return blueprint, task_plan, task_bindings

        planning_mode = str(run.input.get("planningMode") or "").strip().lower()
        force_dynamic = (
            workflow.is_native_bootstrap
            or bool(run.input.get("forceDynamicPlanning"))
            or planning_mode == "dynamic"
        )
        use_planner = (
            self.require_planner_identity
            or run_intent_basis(run) is not None
            or self.identity_lifecycle is not None
            or force_dynamic
            or bool(run.input.get("usePlanner"))
            or not workflow.steps
        )
        if use_planner:
            basis = run_intent_basis(run)
            intent_text = str(
                run.input.get("userIntent")
                or run.input.get("intent")
                or task.title
                or workflow.description
            )
            if basis is not None:
                intent_text = basis.objective
            planning_input = planner_input(basis, run.input) if basis is not None else deepcopy(run.input)
            if self.attachment_context_builder is not None:
                planning_input = self.attachment_context_builder.enrich(planning_input)
            if basis is not None:
                planning_input = planner_input(basis, planning_input)
            planning_engine = self._planning_engine_for_run(run)

            def planning_progress(event: dict[str, Any]) -> None:
                # Planner 阶段回调统一建模为带 kind 的 Runtime Event；stage/status
                # 原样保留，旧 Run 的 legacy 投影继续可用。
                kind_by_status = {
                    "started": "stage_started",
                    "completed": "stage_completed",
                    "retrying": "retry",
                    "profile_resolved": "profile_resolved",
                    "plan_parsed": "plan_parsed",
                }
                payload = dict(event)
                if not payload.get("eventType"):
                    payload["kind"] = str(
                        payload.get("kind")
                        or kind_by_status.get(str(payload.get("status")), "stage_updated")
                    )
                self._append_planner_event(run, payload)

            self._append_planner_event(run, {"kind": "started"})
            existing_semantic_tasks = self._existing_semantic_task_catalog(task.mission_id)
            try:
                plan = planning_engine.plan(
                    mission_id=task.mission_id,
                    intent=intent_text,
                    domain=workflow.domain or task.domain,
                    task_type=task.intent or workflow.intent,
                    force_dynamic=force_dynamic,
                    thinking_mode=str(run.input.get("thinkingMode") or "").strip() or None,
                    reasoning_effort=str(run.input.get("reasoningEffort") or "").strip() or None,
                    # 仅显式 deterministicIntent 才禁用 v2 语义模型；强制动态规划
                    # 不能再隐式退回固定能力链。
                    deterministic_intent=bool(run.input.get("deterministicIntent")),
                    planning_diversity=run.planning_diversity,
                    planning_seed=run.planning_seed,
                    capability_catalog_revision=run.capability_catalog_revision,
                    required_capabilities=workflow.required_capabilities,
                    task_input=planning_input,
                    existing_semantic_tasks=existing_semantic_tasks,
                    capability_profile=str(run.input.get("capabilityProfile") or "auto"),
                    run_id=run.run_id,
                    progress_callback=planning_progress,
                )
            except Exception as exc:
                # 只落稳定错误码与异常类型名；异常消息可能携带 prompt 或模型
                # 输出片段，禁止进入 Trace。
                failure_audit = self._topology_failure_audit(exc)
                self._append_planner_event(run, {
                    "kind": "failed",
                    "errorCode": transport_error_code(exc) or type(exc).__name__,
                    "safeSummary": f"{type(exc).__name__} during planning",
                    **({"topologyAudit": failure_audit} if failure_audit else {}),
                })
                raise
            # 规划成功也不代表可以继续：取消发生在最后一次事件之后时，
            # 在提交 run 状态更新前再复查一次（取自 mission-cancellation 的取消边界）。
            self._raise_if_run_cancelled(run.run_id)
            run.planning_diversity = plan.planning_diversity
            run.planning_seed = plan.planning_seed
            run.planner_algorithm_version = plan.planner_algorithm_version
            run.planning_candidate_count = max(1, plan.candidate_count)
            run.selected_planning_variant_id = plan.selected_variant_id
            run.execution_state.update(
                {
                    "planningDiversity": plan.planning_diversity,
                    "planningSeed": plan.planning_seed,
                    "plannerAlgorithmVersion": plan.planner_algorithm_version,
                    "planningCandidateCount": plan.candidate_count,
                    "selectedPlanningVariantId": plan.selected_variant_id,
                    "selectedCapabilities": list(plan.selected_capabilities),
                    "selectedBindings": list(plan.selected_bindings),
                    "planningSelectionReasons": list(plan.selection_reasons),
                    "requestedCapabilityProfile": plan.requested_capability_profile,
                    "effectiveCapabilityProfile": plan.effective_capability_profile,
                    "capabilityProfileReason": plan.capability_profile_reason,
                    "topologyAudit": dict(plan.topology_audit),
                }
            )
            self.trace_store.append(
                run=run,
                event_type=TraceEventType.TASK_STATUS_CHANGED,
                observation=f"Planner produced ACG via {plan.strategy}",
                payload=plan.to_decision()
                | {
                    "resolvedEnabledPluginIds": list(run.enabled_plugin_ids),
                    "capabilityCatalogRevision": run.capability_catalog_revision,
                    "visibleCapabilityCount": (
                        len(run.execution_scope.capability_ids)
                        if run.execution_scope is not None
                        else len(self.capability_catalog.available())
                    ),
                    "scopeExcludedAgentCount": int(
                        run.execution_state.get("scopeExcludedAgentCount", 0)
                    ),
                },
            )
            if plan.stochastic_fallback:
                self.trace_store.append(
                    run=run,
                    event_type=TraceEventType.STOCHASTIC_PLANNING_FALLBACK,
                    observation="No stochastic candidate passed validation; stable planning used",
                    payload=plan.to_decision(),
                )
            blueprint = plan.blueprint
            if workflow.review_capability:
                review_nodes = [
                    node
                    for node in blueprint.step_nodes()
                    if node.capability == workflow.review_capability
                ]
                if len(review_nodes) != 1:
                    raise ValueError(
                        "workflow review capability must resolve to exactly one ACG step: "
                        f"{workflow.review_capability}"
                    )
                review_nodes[0].review_required = True
                review_nodes[0].metadata["reviewBarrier"] = True
                blueprint.metadata["reviewCapability"] = workflow.review_capability
            return blueprint, plan.task_plan, plan.task_bindings

        blueprint = promote_workflow_to_acg(workflow, mission_id=task.mission_id)
        return blueprint, None, ()

    def _existing_semantic_task_catalog(self, mission_id: str) -> tuple[dict[str, str], ...]:
        """Read the latest V2 planning snapshot as a stable-key catalog.

        The catalog is identity metadata only.  It lets a later Run reuse an existing
        logical key for the same role/capability while leaving all semantic content in the
        new Run-specific TaskPlan snapshot.
        """
        lifecycle = self.identity_lifecycle
        repositories = getattr(lifecycle, "repositories", None)
        if repositories is None:
            return ()
        catalog: list[dict[str, str]] = []
        latest_plan = repositories.task_plans.latest(mission_id)
        if latest_plan is not None:
            catalog.extend(
                {
                    "key": node.key,
                    "capabilityId": node.capability_requirements[0] if node.capability_requirements else "",
                    "logicalRole": node.logical_role,
                }
                for node in latest_plan.nodes
            )
        for task in repositories.semantic_tasks.list_for_mission(mission_id):
            if not task.semantic_task_key or any(item["key"] == task.semantic_task_key for item in catalog):
                continue
            catalog.append({"key": task.semantic_task_key, "capabilityId": "", "logicalRole": "task"})
        return tuple(catalog)

    def _sync_run_steps_to_acg(
        self,
        run: RuntimeRunRecord,
        blueprint: RuntimeBlueprintSpec,
    ) -> None:
        """让 RuntimeRunRecord 的步骤列表与最终 ACG 蓝图保持一致。"""
        existing = {step.step_id: step for step in run.steps}
        agents_by_step: dict[str, list] = {}
        for binding in blueprint.resource_plan.bindings:
            agents_by_step.setdefault(binding.step_id, []).append(binding)
        synced: list[WorkflowStep] = []
        for node in blueprint.step_nodes():
            agents = agents_by_step.get(node.node_id, [])
            if len(agents) != 1:
                raise ValueError(
                    f"ACG step {node.node_id} requires exactly one AgentBindingSpec"
                )
            agent_name = agents[0].planned_agent_id
            # Blueprint 是规划期唯一真源。这里把记忆策略复制到本次运行步骤，后续
            # 即使蓝图对象被修改，也不能反向改变已创建 run 的读取、写入和预算边界。
            node_input = dict(node.input_spec)
            if run.input.get("reasoningEffort"):
                node_input["reasoningEffort"] = run.input["reasoningEffort"]
                node_input["reasoningPolicyReason"] = "run_explicit"
            elif node.metadata.get("reasoningEffort"):
                node_input["reasoningEffort"] = node.metadata["reasoningEffort"]
                node_input["reasoningPolicyReason"] = node.metadata.get(
                    "reasoningPolicyReason", "planner_policy"
                )
            memory_policy = node.metadata.get("memoryPolicy")
            if memory_policy is not None:
                if not isinstance(memory_policy, dict):
                    raise ValueError(f"ACG step {node.node_id} memoryPolicy must be an object")
                memory_policy = dict(memory_policy)
                evolved_budget = (run.execution_state.get("evolutionPolicy") or {}).get(
                    "budget_adjustment:memory_token_budget"
                )
                if evolved_budget is not None:
                    if (
                        not isinstance(evolved_budget, (int, float))
                        or isinstance(evolved_budget, bool)
                        or evolved_budget <= 0
                    ):
                        raise ValueError("active evolution memory token budget must be positive")
                    memory_policy["tokenBudget"] = int(evolved_budget)
                    run.execution_state.setdefault("appliedEvolutionPolicy", {})[
                        "memoryTokenBudget"
                    ] = int(evolved_budget)
                # 在 prepare_run 冻结前立即校验并标准化策略。这样错误配置不会等到
                # 节点已经调用 Agent 后才暴露；保存到运行的快照始终采用读写分离格式。
                normalized = ACGNodeRunner._memory_policy({"memoryPolicy": memory_policy})
                node_input["memoryPolicy"] = {
                    "policyId": normalized["policyId"],
                    "read": normalized["read"],
                    "readTypes": [item.value for item in normalized["readTypes"]],
                    "write": normalized["write"],
                    "writeType": (
                        normalized["writeType"].value
                        if normalized["writeType"] is not None
                        else None
                    ),
                    "limit": normalized["limit"],
                    "tokenBudget": normalized["tokenBudget"],
                    "requireAudit": normalized["requireAudit"],
                }
            step = existing.get(node.node_id)
            if step is None:
                step = WorkflowStep(
                    stepId=node.node_id,
                    name=node.name or node.node_id,
                    agentName=agent_name,
                    capability=node.capability,
                    goal=node.goal,
                    acceptanceCriteria=list(node.acceptance_criteria),
                    sourceRefs=list(node.source_refs),
                    logicalRole=node.logical_role,
                    input=node_input,
                    outputSpec=dict(node.output_spec),
                    reviewRequired=node.review_required,
                    maxRetries=node.retry_limit,
                    timeout=node.timeout,
                    priority=node.priority,
                )
            else:
                step.name = node.name or step.name
                step.agent_name = agent_name
                step.capability = node.capability
                step.goal = node.goal
                step.acceptance_criteria = list(node.acceptance_criteria)
                step.source_refs = list(node.source_refs)
                step.logical_role = node.logical_role
                step.input = node_input
                step.output_spec = dict(node.output_spec)
                step.requires_review = node.review_required
                step.max_retries = node.retry_limit
                step.timeout = node.timeout
                step.priority = node.priority
            synced.append(step)

        run.steps = synced
        step_ids = {step.step_id for step in synced}
        if run.current_step_id not in step_ids:
            run.current_step_id = synced[0].step_id if synced else None

    def _transition_run_if_needed(self, run: RuntimeRunRecord, status: WorkflowStatus) -> None:
        if run.status != status:
            self._transition_run(run, status)

    def _claim_execution_slot(self, run_id: str) -> bool:
        """原子认领运行级执行槽；该 run 已有执行体在场时返回 ``False``。"""
        with self._execution_slot_guard:
            if run_id in self._active_execution_slots:
                return False
            self._active_execution_slots.add(run_id)
            return True

    def _release_execution_slot(self, run_id: str) -> None:
        with self._execution_slot_guard:
            self._active_execution_slots.discard(run_id)
            fence = self._execution_fences.pop(run_id, None)
        if fence is not None:
            fence.close()

    def _signal_run_cancellation(self, run_id: str) -> None:
        """写入协作式取消信号；执行侧在下一次调度边界感知并停止推进。"""
        with self._run_cancel_guard:
            event = self._run_cancel_events.get(run_id)
            if event is None:
                event = threading.Event()
                self._run_cancel_events[run_id] = event
            event.set()

    def _cancellation_event(self, run_id: str) -> threading.Event:
        """取回（或惰性创建）当前运行的取消信号，供执行主循环持有引用轮询。"""
        with self._run_cancel_guard:
            event = self._run_cancel_events.get(run_id)
            if event is None:
                event = threading.Event()
                self._run_cancel_events[run_id] = event
            return event

    def _run_cancellation_requested(self, run_id: str) -> bool:
        with self._run_cancel_guard:
            event = self._run_cancel_events.get(run_id)
            return bool(event is not None and event.is_set())

    def _raise_if_run_cancelled(self, run_id: str) -> None:
        """在规划/物化边界读取持久化终态，阻止取消后的旧快照继续推进。"""
        if self._run_cancellation_requested(run_id):
            raise ExecutionRunCancelled(f"run {run_id} cancelled")
        try:
            run = self.workflow_store.get_run(run_id)
        except KeyError:
            return
        if run.status is WorkflowStatus.CANCELLED:
            raise ExecutionRunCancelled(f"run {run_id} cancelled")

    def _discard_run_cancellation(self, run_id: str) -> None:
        with self._run_cancel_guard:
            self._run_cancel_events.pop(run_id, None)

    @staticmethod
    def _publish_run_terminal_event(
        run: RuntimeRunRecord,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Publish only safe run lifecycle scalars to the existing live broker."""
        from contracts.runtime_events import RuntimeEvent
        from runtime.live_events import runtime_event_broker

        runtime_event_broker.publish_from_thread(
            run.run_id,
            RuntimeEvent(
                eventType=event_type,
                runId=run.run_id,
                nodeId=None,
                attemptId=None,
                sequence=0,
                payload={
                    key: value for key, value in (payload or {}).items()
                    if isinstance(value, (str, int, float, bool))
                },
            ),
        )

    def get_status(self, run_id: str) -> RuntimeRunRecord:
        """读取指定运行的最新状态投影；不存在时由存储层抛出 ``KeyError``。"""
        return self.workflow_store.get_run(run_id)

    def get_status_cached(self, run_id: str) -> RuntimeRunRecord:
        """``get_status`` 的只读快路径；存储层支持时走内容寻址缓存。"""
        get_run_cached = getattr(self.workflow_store, "get_run_cached", None)
        if get_run_cached is None:
            return self.workflow_store.get_run(run_id)
        return get_run_cached(run_id)

    async def update_run_lifecycle(
        self,
        run_id: str,
        *,
        status: WorkflowStatus | None = None,
        phase: WorkflowProgressPhase | None = None,
        message: str | None = None,
        error: object = _ERROR_UNSET,
        set_started_at: bool = False,
    ) -> RuntimeRunRecord:
        """重新读取、校验并持久化生命周期字段，返回最新投影；终态非法迁移会被拒绝。"""

        run = self.workflow_store.get_run(run_id)
        return self._set_run_lifecycle(
            run,
            status=status,
            phase=phase,
            message=message,
            error=error,
            set_started_at=set_started_at,
        )

    def _set_run_lifecycle(
        self,
        run: RuntimeRunRecord,
        *,
        status: WorkflowStatus | None = None,
        phase: WorkflowProgressPhase | None = None,
        message: str | None = None,
        error: object = _ERROR_UNSET,
        set_started_at: bool = False,
    ) -> RuntimeRunRecord:
        try:
            persisted = self.workflow_store.get_run(run.run_id)
        except KeyError:
            persisted = run
        if persisted.status in _TERMINAL_RUN_STATUSES and persisted.status != run.status:
            run = persisted
        if run.status in _TERMINAL_RUN_STATUSES:
            terminal_phase = WorkflowProgressPhase(run.status.value)
            if status not in {None, run.status} or phase not in {None, terminal_phase}:
                return run

        target_status = status or run.status
        terminal_phase_by_status = {
            WorkflowStatus.COMPLETED: WorkflowProgressPhase.COMPLETED,
            WorkflowStatus.FAILED: WorkflowProgressPhase.FAILED,
            WorkflowStatus.CANCELLED: WorkflowProgressPhase.CANCELLED,
        }
        target_phase = terminal_phase_by_status.get(target_status, phase)
        target_message = message
        if target_phase is not None and target_message is None:
            target_message = _LIFECYCLE_MESSAGES[target_phase]

        changed = False
        if target_status != run.status:
            run.status = self.state_machine.transition(run.status, target_status)
            changed = True
        if target_phase is not None and target_phase != run.lifecycle_phase:
            run.lifecycle_phase = target_phase
            changed = True
        if target_message is not None and target_message != run.lifecycle_message:
            run.lifecycle_message = target_message
            changed = True
        if set_started_at and run.started_at is None:
            run.started_at = utc_now()
            changed = True
        if error is not _ERROR_UNSET and error != run.error:
            run.error = error  # type: ignore[assignment]
            changed = True
        if changed:
            run.updated_at = utc_now()
            self.workflow_store.save_run(run)
        return run

    async def fail_run_safely(
        self,
        run_id: str,
        *,
        error_code: str,
        error_message: str,
        error_metadata: Mapping[str, Any] | None = None,
    ) -> RuntimeRunRecord:
        """Delegate terminal failure convergence to the recovery boundary."""
        return self.runtime_recovery_coordinator.fail_run_safely(
            run_id,
            error_code=error_code,
            error_message=error_message,
            error_metadata=error_metadata,
        )

    async def close_orphaned_runs(self, *, limit: int = 200) -> list[str]:
        """Delegate restart recovery while retaining the public facade API."""
        await self._recover_pending_planning_transitions(limit=limit)
        return self.runtime_recovery_coordinator.close_orphaned_runs(limit=limit)

    async def prepare_planning_wakeups(self, *, page_size: int = 200, now=None) -> list[str]:
        """Reconcile stored waits with current authorities; never call a model.

        Use the existing paged Run query so older waits cannot be starved by
        the latest N active Runs. Collect ids before changing query membership.
        """
        if not 1 <= page_size <= 500:
            raise ValueError("planning wakeup page_size must be between 1 and 500")
        candidates, page = [], 1
        while True:
            result = self.workflow_store.list_runs(statuses=(WorkflowStatus.WAITING_REVIEW, WorkflowStatus.RETRYING),
                page=page, page_size=page_size)
            candidates.extend(r.run_id for r in result.items if
                (r.execution_state.get("planningLoop") or {}).get("waiting")
                or (r.execution_state.get("planningLoop") or {}).get("userInputPending")
                or self.workflow_store.list_planning_inputs(r.run_id))
            if page * page_size >= result.total:
                break
            page += 1
            await asyncio.sleep(0)
        if any(((self.workflow_store.get_run(run_id).execution_state.get("planningLoop") or {})
                .get("waiting") or {}).get("condition", {}).get("kind") == "requirement_available"
                for run_id in candidates):
            self.runtime_binding_service.refresh_embedded_runtime()
        ready = []
        for run_id in candidates:
            async with self.run_lock_manager.lock_for(run_id):
                with self._execution_slot_guard:
                    active = run_id in self._active_execution_slots
                if active:
                    continue
                try:
                    run = self.workflow_store.get_run(run_id)
                    if self.runtime_planning_wait_service.prepare(run, now=now):
                        ready.append(run_id)
                except (ValueError, KeyError):
                    # Corrupt wait metadata must neither execute nor block other waits.
                    logger.exception("Planner wait reconciliation rejected", extra={"runId": run_id})
        return ready

    async def _recover_pending_planning_transitions(self, *, limit: int) -> None:
        """Replay durable decisions interrupted between authority applications."""
        from contracts.runtime_planning import RuntimePlanningState
        for run in self.workflow_store.list_all_runs(limit=limit):
            raw = run.execution_state.get("planningLoop")
            if not isinstance(raw, dict):
                continue
            loop = RuntimePlanningState.model_validate(raw)
            current = loop.current
            if current is None or current.decision is None or current.status != "applied":
                continue
            if run.status == WorkflowStatus.FAILED and current.decision.action == "recover":
                key = f"planner:{current.observation_id}"
                if key in (run.execution_state.get("inPlaceRetryRequests") or {}):
                    continue
                self.prepare_single_step_retry(
                    run.run_id, current.observation.failed_step_ids[0], reason="runtime_planner",
                    idempotency_key=key, idempotency_fingerprint=current.observation_id,
                    reuse_source_run=True,
                )
            elif run.status == WorkflowStatus.WAITING_REVIEW and current.decision.action == "revise" and (run.execution_state.get("reviewPayload") or {}).get("subjectType") == "planner":
                await self._apply_runtime_planning_decision(
                    run, acg_execution_state_from_run(run), current.observation,
                    current.decision, loop,
                )


    @staticmethod
    def _safe_error_message(exc: BaseException) -> str:
        current: BaseException | None = exc
        seen: set[int] = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            code = str(
                getattr(current, "cause_code", None)
                or getattr(current, "code", None)
                or ""
            ).upper()
            if code == "MODEL_CONNECTION_INTERRUPTED":
                return "模型服务连接中断，系统已完成一次重试，请稍后重新运行。"
            if code == "MODEL_TIMEOUT":
                return "模型服务响应超时，系统已完成一次重试，请稍后重新运行。"
            current = current.__cause__ or current.__context__
        message = str(exc).strip()
        return (message or type(exc).__name__)[:500]

    def resolve_workflow_id(self, workflow_id: str | None) -> str | None:
        """规范化可选工作流标识；非空值会经注册表校验，不存在时抛出错误。"""
        if not workflow_id:
            return workflow_id
        return self.workflow_registry.get(workflow_id).workflow_id

    def list_checkpoints(self, run_id: str) -> list[Checkpoint]:
        """读取运行关联检查点列表，不改变运行或检查点状态。"""
        return list(self.workflow_store.get_run(run_id).checkpoints)

    def clean_execution_orphans(self, *, run_id: str, older_than: datetime):
        """延迟清理当前运行未被提交、State、检查点或审核意图保护的执行正文。

        调用方必须显式给出带时区的保留阈值，避免默认立即删除。整个收集和删除过程
        持有当前 run 锁，因此恢复、审核和清理不会交错地删除仍准备提交的引用。Trace
        只记录扫描、保护和删除计数，不能包含 output、ContextPack 或记忆正文。
        """
        with self.run_lock_manager.lock_for(run_id):
            run = self.workflow_store.get_run(run_id)
            protected_refs = self._protected_execution_references(run)
            stats = self.orphan_cleaner.clean(
                run_id=run_id,
                protected_refs=protected_refs,
                older_than=older_than,
            )
            self.trace_store.append(
                run,
                TraceEventType.TASK_STATUS_CHANGED,
                observation="Expired execution values cleaned",
                payload={
                    "kind": "execution_value_cleanup",
                    "scanned": stats.scanned,
                    "protected": stats.protected,
                    "deleted": stats.deleted,
                },
            )
            self.workflow_store.save_run(run)
            return stats

    def _protected_execution_references(self, run: RuntimeRunRecord) -> set[str]:
        """从所有可恢复入口提取已知正文引用，不递归读取或复制任何正文。"""
        references: set[str] = set()
        self._collect_value_references(run.execution_state, references)
        self._collect_value_references(run.output, references)
        for commit in self.execution_value_store.list_node_commits(run_id=run.run_id):
            self._collect_value_references(commit, references)
        checkpoint_states = getattr(self.checkpoint_store, "list_states", None)
        if callable(checkpoint_states):
            for state in checkpoint_states(run_id=run.run_id):
                self._collect_value_references(state, references)
        for checkpoint in run.checkpoints:
            self._collect_value_references(checkpoint.state_snapshot, references)
            self._collect_value_references(checkpoint.output_snapshot, references)
        return references

    @staticmethod
    def _collect_value_references(payload: object, references: set[str]) -> None:
        """从已定义的引用字段收集标识，不能把任意字符串误当成可保护的引用。"""
        if not isinstance(payload, dict):
            return
        for field_name in ("outputRef", "contextRef", "graphPatchRef"):
            value = payload.get(field_name)
            if isinstance(value, str) and value:
                references.add(value)
        for field_name in ("outputRefs", "contextRefs", "graphPatchRefs"):
            values = payload.get(field_name)
            if isinstance(values, dict):
                references.update(
                    value for value in values.values() if isinstance(value, str) and value
                )
            elif isinstance(values, list):
                references.update(value for value in values if isinstance(value, str) and value)
        review_payload = payload.get("reviewPayload")
        if isinstance(review_payload, dict):
            pending_memory = review_payload.get("pendingMemory")
            if isinstance(pending_memory, dict):
                output_ref = pending_memory.get("outputRef")
                if isinstance(output_ref, str) and output_ref:
                    references.add(output_ref)
        pending_memory = payload.get("pendingMemory")
        if isinstance(pending_memory, dict):
            output_ref = pending_memory.get("outputRef")
            if isinstance(output_ref, str) and output_ref:
                references.add(output_ref)

    def list_reviews(self, run_id: str) -> list[ReviewRecord]:
        """读取运行审核记录列表，不执行审核决策或状态迁移。"""
        return self.review_manager.list(self.workflow_store.get_run(run_id))

    def propose_evolution_from_run(
        self, run_id: str
    ) -> tuple[Trajectory, TrajectoryEvaluation, EvolutionProposal]:
        """从一个真实完成运行投影轨迹并生成待人工审核的演化提案。"""
        run = self.workflow_store.get_run(run_id)
        if run.status is not WorkflowStatus.COMPLETED:
            raise ValueError("only a completed workflow run can produce an evolution proposal")
        ledger = self.provenance_store.load_ledger(run_id=run.run_id, mission_id=run.mission_id)
        return self.evolution_service.propose_from_run(
            run,
            provenance_events=ledger.trace_events(),
        )

    def approve_evolution_proposal(
        self, proposal_id: str, *, approved_by: str
    ) -> EvolutionPolicyVersion:
        """审核一个已持久化提案并以 CAS 创建新的 General 策略版本。"""
        if not approved_by.strip():
            raise ValueError("evolution proposal reviewer is required")
        proposal = self.evolution_service.store.get_proposal(proposal_id)
        return self.evolution_service.approve(proposal, approved_by=approved_by.strip())

    def evaluate_runs(
        self,
        *,
        status: WorkflowStatus | str | None = None,
        domain: str | None = None,
        workflow_id: str | None = None,
        source: str | None = None,
    ) -> EvaluationRun:
        """按可选状态、域和来源过滤运行并生成评估汇总，复杂度受存储查询结果规模限制。"""
        workflow_id = self.resolve_workflow_id(workflow_id)
        page = self.workflow_store.list_runs(
            status=status,
            domain=domain,
            workflow_id=workflow_id,
            source=source,
            page=1,
            page_size=10_000,
        )
        return self.evaluator.evaluate(
            page.items,
            domain=domain,
            workflow_id=workflow_id,
            source=source,
        )

    async def apply_review(self, decision: ReviewDecision) -> RuntimeRunRecord:
        """在运行锁内校验并应用审核决定；过期、冲突或终态运行抛出 ``ReviewConflictError``。"""
        initial_run = self.workflow_store.get_run(decision.run_id)
        if self._normalize_runtime_engine(initial_run.runtime_engine) == "acg":
            # facade 持锁派发 ReviewService；批准路径交还恢复输入后由本层
            # 调用 ACGExecutionService 续跑（Review → Execution 的唯一接缝）。
            async with self.run_lock_manager.lock_for(decision.run_id):
                current = self.workflow_store.get_run(decision.run_id)
                if current.execution_state.get('planningCommitRequired'):
                    principal = self.semantic_principal_provider() if self.semantic_principal_provider else None
                    if principal is None or self.mission_semantic_service is None:
                        raise PermissionError('formal review requires trusted write authority')
                    # Check before ReviewService writes audit/deferred memory,
                    # including idempotent replay. Native claim checks again.
                    self.mission_semantic_service.require_write_access(principal, current.mission_id)
                    decision = decision.model_copy(update={'reviewer': principal.actor_id})
                outcome = self.review_service.apply_acg(decision)
            if outcome.resume_state is None:
                # Rejection is a durable lifecycle boundary too. Publish it
                # before a later explicit in-place retry observes Identity.
                if initial_run.execution_state.get("executionPermitId"):
                    self._flush_identity_outbox()
                return outcome.run
            return await self._execute_acg(
                outcome.run,
                state=outcome.resume_state,
                command=ExecutionResumeCommand(
                    runId=outcome.run.run_id,
                    payload={"decision": decision.decision.value, "operationId": decision.operation_id},
                ),
            )
        async with self.run_lock_manager.lock_for(decision.run_id):
            run = self.workflow_store.get_run(decision.run_id)
            existing = self.review_service.find_review_operation(run, decision.operation_id)
            if existing is not None:
                if (
                    existing.get("stepId") == decision.step_id
                    and existing.get("decision") == decision.decision.value
                ):
                    return run
                raise ReviewConflictError("review operation id was already used for a different decision")

            if run.status in _TERMINAL_RUN_STATUSES:
                raise ReviewConflictError("workflow run is already terminal")
            if run.status != WorkflowStatus.WAITING_REVIEW:
                raise ReviewConflictError("workflow run is no longer waiting for review")
            step = run.get_step(decision.step_id)
            if step.status != StepStatus.WAITING_REVIEW:
                raise ReviewConflictError("workflow step is no longer waiting for review")
            if (
                decision.expected_run_updated_at is not None
                and run.updated_at != decision.expected_run_updated_at
            ):
                raise ReviewConflictError("workflow run revision changed")
            if (
                decision.expected_step_status is not None
                and step.status != decision.expected_step_status
            ):
                raise ReviewConflictError("workflow step state changed")

        workflow = self._workflow_for_run(run)
        adapter = self._workflow_adapter(workflow)
        return await adapter.apply_review(decision)

    async def apply_semantic_patch(
        self, request: SemanticPatchRequest
    ) -> GraphPatchResult | PlanningCommitReceipt:
        """Accept an opt-in candidate, or use the existing replacement-Run lane."""
        async with self.run_lock_manager.lock_for(request.run_id):
            run = self.workflow_store.get_run(request.run_id)
            if self.planning_commit_authority is not None or run.execution_state.get("planningCommitRequired"):
                if self.planning_commit_authority is None:
                    raise ValueError("Planning Commit authority is required for this Run")
                self._mark_planning_commit_required(run)
                return self.planning_commit_authority.accept_patch_locked(run.run_id, request.task_plan_patch,
                    proposal_id=request.patch_id, idempotency_key=request.idempotency_key,
                    graph_id=request.graph_id, graph_version=request.base_graph_version)
            service = self.semantic_revision_service
            prepared = service.prepare(
                request=request,
                run=run,
            )
            if isinstance(prepared, GraphPatchResult):
                return prepared

            self.runtime_binding_service.prepare(
                run=prepared.replacement_run,
                workflow=prepared.workflow,
                scope=prepared.scope,
                binding_manifest=prepared.compiled_package.binding_manifest,
            )
            result = service.commit(prepared)
            self._flush_identity_outbox()
            return result


    async def rebind_step(self, *, run_id: str, step_id: str, reason: str) -> str:
        """Select a healthy alternate Agent inside the run's frozen scope.

        Run 锁由本入口持有；concrete binding 的应用逻辑在
        RuntimeRecoveryCoordinator 中实现，TaskPlan / graphVersion 不受影响。
        """
        async with self.run_lock_manager.lock_for(run_id):
            run = self.workflow_store.get_run(run_id)
            return self.runtime_recovery_coordinator.rebind_step(
                run=run, step_id=step_id, reason=reason
            )

    async def resume_from_checkpoint(self, *, run_id: str, checkpoint_id: str) -> RuntimeRunRecord:
        """从同版本检查点恢复 ACG 运行；范围、图或工作流版本不匹配时明确拒绝。"""
        run, state = self.runtime_recovery_coordinator.load_resume_input(
            run_id=run_id, checkpoint_id=checkpoint_id
        )
        return await self._execute_acg(
            run,
            state=state,
            command=ExecutionResumeCommand(runId=run_id),
        )

    def cancel(self, run_id: str, *, expected_runtime_revision: int | None = None) -> RuntimeRunRecord:
        """在运行锁内取消可继续步骤并持久化终态；已终态的迁移规则由状态机校验。"""
        with self.run_lock_manager.lock_for(run_id):
            latest = self.workflow_store.get_run(run_id)
            if expected_runtime_revision is not None and latest.runtime_revision != expected_runtime_revision:
                raise ValueError('Run changed after cancellation was prepared')
            if latest.status is WorkflowStatus.CANCELLED:
                return latest  # Internal duplicate cancellation must not rewrite historical Trace.
            if latest.status in _TERMINAL_RUN_STATUSES:
                raise InvalidStateTransition('terminal Run cannot be cancelled')
            # 先写协作式取消信号，再落终态：执行中的图会在下一个调度边界停止
            # 推进，而不是继续跑完后继步骤后与已持久化的终态互踩。
            self._signal_run_cancellation(run_id)
            run = latest.model_copy(deep=True)
            self._transition_run(run, WorkflowStatus.CANCELLED)
            self.mission_manager.mark_cancelled(run.mission_id)
            self.trace_store.append(
                run=run,
                event_type=TraceEventType.RUN_CANCELLED,
                observation="Workflow cancelled.",
            )
            self.workflow_store.save_run(run)
            if (
                self.identity_lifecycle is not None
                and self._normalize_runtime_engine(run.runtime_engine) == "acg"
            ):
                self._flush_identity_outbox()
            self._publish_run_terminal_event(run, "run.cancelled")
            return run

    def _resolve_workflow(
        self,
        task: RuntimeMissionRecord,
        workflow_id: Optional[str],
        *,
        allowed_workflow_ids: tuple[str, ...] | None = None,
    ) -> WorkflowDefinition:
        return self.mission_manager.bind_workflow(
            task,
            workflow_id=workflow_id,
            allowed_workflow_ids=allowed_workflow_ids,
        )

    def _planning_engine_for_run(self, run: RuntimeRunRecord):
        if run.execution_scope is None and not self._react_planning_active():
            return self.planning_engine
        from components.planner.service import PlanningEngine

        if run.execution_scope is None:
            engine = PlanningEngine(
                workflow_registry=self.workflow_registry,
                agent_registry=self.agent_registry,
                capability_catalog=self.capability_catalog,
                intent_llm=self._intent_llm,
            )
        else:
            engine = PlanningEngine(
                workflow_registry=self.plugin_scope_resolver.scoped_workflows(
                    run.execution_scope
                ),
                agent_registry=self.plugin_scope_resolver.scoped_agents(
                    run.execution_scope
                ),
                capability_catalog=self.plugin_scope_resolver.scoped_catalog(
                    run.execution_scope
                ),
                intent_llm=self._intent_llm,
            )
        return self._attach_react_loop(engine, run)

    def _react_planning_active(self) -> bool:
        """PR-S01-02 opt-in：环境开关打开且注入了意图 LLM 才激活 ReAct 循环。"""
        from components.planner.react_loop import react_planning_enabled

        return react_planning_enabled() and self._intent_llm is not None

    def _attach_react_loop(self, engine, run: RuntimeRunRecord):
        if not self._react_planning_active():
            return engine
        from components.planner.react_loop import BoundedReActPlanningLoop
        from components.planner.unified_actions import PlannerActionGateway

        def react_audit(payload: dict) -> None:
            # 与 planning_loop._save 同款 Runtime Event；负载由循环侧保证
            # 有界脱敏（拒绝码/目标/指纹），不携带提案原文或模型推理文本。
            self.trace_store.append(
                run,
                TraceEventType.RUNTIME_EVENT_CLASSIFIED,
                observation=f"ReAct planner {str(payload.get('runtimeEvent') or 'event')}",
                payload=payload,
            )

        gateway = PlannerActionGateway(
            workflow_store=self.workflow_store,
            capability_catalog=engine.capability_catalog,
            audit_sink=react_audit,
            cancellation_requested=self._run_cancellation_requested,
        )
        from components.planner.htn import HTNMethodSelector, build_native_htn_catalog, htn_planning_enabled

        if htn_planning_enabled():
            gateway.htn_selector = HTNMethodSelector(
                catalog=build_native_htn_catalog(), capability_catalog=engine.capability_catalog)
        from components.planner.horizon import AdaptiveHorizonSelector, horizon_planning_enabled

        if horizon_planning_enabled():
            gateway.horizon_selector = AdaptiveHorizonSelector(engine.capability_catalog)
        engine.react_loop = BoundedReActPlanningLoop(
            llm=self._intent_llm, gateway=gateway, audit_sink=react_audit
        )
        return engine

    def _workflow_for_run(self, run: RuntimeRunRecord) -> WorkflowDefinition:
        if run.execution_scope is None:
            if run.legacy_plugin_scope:
                raise PluginScopeError(
                    "LEGACY_PLUGIN_SNAPSHOT_MISSING",
                    f"run {run.run_id} has no frozen plugin scope",
                )
            return self.workflow_registry.get(run.workflow_id)
        self.plugin_scope_resolver.validate_snapshot(run.execution_scope)
        return self.workflow_registry.get(
            run.workflow_id,
            allowed_workflow_ids=run.execution_scope.workflow_ids,
        )

    def _workflow_adapter(self, workflow: WorkflowDefinition):
        runtime_engine = workflow.effective_runtime_engine
        implementation_id = workflow.effective_implementation_id
        adapter_key = f"{runtime_engine}:{implementation_id}"
        adapter = self._runtime_adapters.get(adapter_key)
        if adapter is None:
            if runtime_engine == "acg":
                raise ExecutionEngineMigratingError()
            else:
                factory = self.execution_adapter_factories.get(runtime_engine)
                if factory is None:
                    raise ValueError(f"Unsupported workflow runtime engine: {runtime_engine}")
                adapter = factory(
                    runtime=self,
                    workflow=workflow,
                    implementation_id=implementation_id,
                )
            self._runtime_adapters[adapter_key] = adapter
        return adapter

    @staticmethod
    def _normalize_runtime_engine(runtime_engine: str) -> str:
        return (runtime_engine or "").strip().lower()

    def _mark_step_failed(
        self,
        run: RuntimeRunRecord,
        task: RuntimeMissionRecord,
        step: WorkflowStep,
        exc: Exception,
    ) -> None:
        step.error = str(exc)
        if step.retry_count < step.max_retries:
            step.retry_count += 1
            self._transition_step(step, StepStatus.RETRYING)
            self._transition_run(run, WorkflowStatus.RETRYING)
            self.mission_manager.mark_retrying(task)
        else:
            self._transition_step(step, StepStatus.FAILED)
            self._transition_run(run, WorkflowStatus.FAILED)
            self.mission_manager.mark_failed(task)
        run.current_step_id = step.step_id
        run.error = str(exc)
        run.updated_at = utc_now()
        self.trace_store.append(
            run=run,
            event_type=TraceEventType.STEP_FAILED,
            step_id=step.step_id,
            agent_name=step.agent_name,
            observation=str(exc),
        )
        self.trace_store.append(
            run=run,
            event_type=TraceEventType.RUN_FAILED,
            step_id=step.step_id,
            observation=str(exc),
        )
        self.workflow_store.save_run(run)

    def _transition_run(self, run: RuntimeRunRecord, status: WorkflowStatus) -> None:
        try:
            persisted = self.workflow_store.get_run(run.run_id)
        except KeyError:
            persisted = run
        if persisted.status in _TERMINAL_RUN_STATUSES and persisted.status != run.status:
            for field_name in RuntimeRunRecord.model_fields:
                setattr(run, field_name, deepcopy(getattr(persisted, field_name)))
            return
        run.status = self.state_machine.transition(run.status, status)
        phase_by_status = {
            WorkflowStatus.WAITING_REVIEW: WorkflowProgressPhase.REVIEW,
            WorkflowStatus.RETRYING: WorkflowProgressPhase.RECOVERY,
            WorkflowStatus.COMPLETED: WorkflowProgressPhase.COMPLETED,
            WorkflowStatus.FAILED: WorkflowProgressPhase.FAILED,
            WorkflowStatus.CANCELLED: WorkflowProgressPhase.CANCELLED,
        }
        phase = phase_by_status.get(status)
        if phase is None and status == WorkflowStatus.RUNNING:
            if run.lifecycle_phase not in {
                WorkflowProgressPhase.PLANNING,
                WorkflowProgressPhase.GRAPH_BUILDING,
            }:
                phase = WorkflowProgressPhase.EXECUTING
        if phase is not None:
            run.lifecycle_phase = phase
            run.lifecycle_message = _LIFECYCLE_MESSAGES[phase]
        if status == WorkflowStatus.RUNNING:
            run.started_at = run.started_at or utc_now()
        run.updated_at = utc_now()

    def _transition_step(self, step: WorkflowStep, status: StepStatus) -> None:
        step.status = self.state_machine.transition(step.status, status)
        if status == StepStatus.RUNNING:
            step.started_at = step.started_at or utc_now()
        if status == StepStatus.COMPLETED:
            step.completed_at = step.completed_at or utc_now()


def build_default_runtime() -> ExecutionRuntime:
    """按环境变量装配默认运行时并登记原生与已安装插件；缺少数据库路径时抛出错误。"""
    agent_registry = AgentRegistry()
    workflow_registry = WorkflowRegistry()

    db_path = os.getenv("AGENTOS_WORKFLOW_DB_PATH", "").strip()
    workflow_store: WorkflowStore
    if not db_path:
        raise RuntimeError("Workflow database path is required outside test mode.")
    workflow_store = SQLiteWorkflowStore(db_path)

    runtime = ExecutionRuntime(
        agent_registry=agent_registry,
        workflow_registry=workflow_registry,
        workflow_store=workflow_store,
        model_max_concurrency=int(os.getenv("AGENTOS_MODEL_MAX_CONCURRENCY", "4")),
        model_min_interval_seconds=float(
            os.getenv("AGENTOS_MODEL_MIN_INTERVAL_SECONDS", "0")
        ),
    )
    register_native_runtime(
        agent_registry=runtime.agent_registry,
        workflow_registry=runtime.workflow_registry,
    )
    runtime.plugin_manifests = register_installed_packs(
        agent_registry=runtime.agent_registry,
        workflow_registry=runtime.workflow_registry,
        capability_catalog=runtime.capability_catalog,
    )
    return runtime


# 兼容既有 API 与第三方导入；新代码使用 ExecutionRuntime 明确唯一执行内核。

__all__ = ["ExecutionRuntime", "ExecutionRunCancelled", "ReviewConflictError", "build_default_runtime"]
