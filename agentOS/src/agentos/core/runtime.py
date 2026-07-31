"""AgentOS Core 的正式运行时文件，延续原 core.workflow_runtime 的实现并承载任务、工作流、审核和恢复入口。"""


from __future__ import annotations

import asyncio
from copy import deepcopy
import logging
import os
import secrets
from time import monotonic
from typing import Mapping, Optional

from agentos.agents import AgentRegistry
from agentos.core.acg import (
    ACGBlueprint,
    promote_workflow_to_acg,
)
from agentos.core.execution import ACGWorkflowAdapter, ExecutionAdapterFactory
from agentos.core.execution.projection import refresh_run_execution_projection
from agentos.core.governance.checkpoint import CheckpointStore, checkpoint_trace_payload
from agentos.core.governance.evaluation import WorkflowEvaluator
from agentos.core.workflow.orchestrator import Orchestrator
from agentos.core.workflow.registry import WorkflowRegistry
from agentos.core.governance.review import ReviewManager
from agentos.core.workflow.state_machine import StateMachine
from agentos.core.workflow.task_manager import TaskManager
from agentos.core.governance.trace import TraceStore
from agentos.core.models.types import (
    AgentTask,
    Checkpoint,
    EvaluationRun,
    ReviewDecision,
    ReviewDecisionType,
    ReviewRecord,
    StepStatus,
    TraceEventType,
    WorkflowDefinition,
    WorkflowRun,
    WorkflowStatus,
    WorkflowStep,
    RunExecutionScope,
    utc_now,
)
from agentos.core.models.enums import WorkflowProgressPhase
from agentos.core.recovery.controller import RuntimeController
from agentos.core.recovery.errors import RuntimeGraphError
from agentos.core.recovery.events import RuntimeEventClassifier
from agentos.core.recovery.policy import RuntimeEventPolicy
from agentos.core.recovery.proposal import (
    CandidateResolver,
    DeterministicProposalFactory,
    RuntimeGraphPatchCompiler,
)
from agentos.core.recovery.recipes import RecoveryRecipeRegistry
from agentos.core.run_locks import GLOBAL_RUN_LOCK_MANAGER, RunLockManager
from agentos.core.runtime_graph import RuntimeGraph
from agentos.core.planning.default_catalog import build_default_capability_catalog
from agentos.core.planning.capabilities import CapabilityCatalog
from agentos.core.planning.variants import (
    PLANNER_ALGORITHM_VERSION,
    normalize_planning_diversity,
    normalize_planning_seed,
)
from agentos.core.plugin_scope import PluginScopeError, PluginScopeResolver
from agentos.packs.registry import register_installed_packs
from agentos.core.native import register_native_runtime
from agentos.stores.memory_workflow_store import MemoryWorkflowStore
from agentos.stores.sqlite_workflow_store import SQLiteWorkflowStore
from agentos.stores.workflow_store import WorkflowStore


logger = logging.getLogger(__name__)

_TERMINAL_RUN_STATUSES = {
    WorkflowStatus.COMPLETED,
    WorkflowStatus.FAILED,
    WorkflowStatus.CANCELLED,
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


class ReviewConflictError(ValueError):
    """The reviewed Run or step changed after the client observed it."""


class WorkflowRuntime:
    """AgentOS Core 的工作流运行时，串联任务、Trace、审核与恢复流程。"""

    def __init__(
        self,
        *,
        agent_registry: Optional[AgentRegistry] = None,
        workflow_registry: Optional[WorkflowRegistry] = None,
        workflow_store: Optional[WorkflowStore] = None,
        trace_store: Optional[TraceStore] = None,
        checkpoint_store: Optional[CheckpointStore] = None,
        review_manager: Optional[ReviewManager] = None,
        evaluator: Optional[WorkflowEvaluator] = None,
        task_manager: Optional[TaskManager] = None,
        execution_adapter_factories: Optional[Mapping[str, ExecutionAdapterFactory]] = None,
        run_lock_manager: Optional[RunLockManager] = None,
        recovery_recipe_registry: Optional[RecoveryRecipeRegistry] = None,
        capability_catalog: CapabilityCatalog | None = None,
        plugin_manifests: tuple = (),
    ):
        self.agent_registry = agent_registry or AgentRegistry()
        self.workflow_registry = workflow_registry or WorkflowRegistry()
        self.capability_catalog = capability_catalog or build_default_capability_catalog()
        self.plugin_manifests = tuple(plugin_manifests)
        self.workflow_store = workflow_store or MemoryWorkflowStore()
        self.trace_store = trace_store or TraceStore()
        self.checkpoint_store = checkpoint_store or CheckpointStore()
        self.review_manager = review_manager or ReviewManager(self.trace_store)
        self.evaluator = evaluator or WorkflowEvaluator()
        self.state_machine = StateMachine()
        self.orchestrator = Orchestrator(self.agent_registry, self.capability_catalog)
        self.task_manager = task_manager or TaskManager(
            workflow_store=self.workflow_store,
            workflow_registry=self.workflow_registry,
            state_machine=self.state_machine,
            trace_store=self.trace_store,
        )
        self.run_lock_manager = run_lock_manager or GLOBAL_RUN_LOCK_MANAGER
        self.runtime_controller = RuntimeController(
            workflow_store=self.workflow_store,
            agent_registry=self.agent_registry,
            checkpoint_store=self.checkpoint_store,
            trace_store=self.trace_store,
            lock_manager=self.run_lock_manager,
        )
        self.recovery_recipe_registry = (
            recovery_recipe_registry or RecoveryRecipeRegistry.with_defaults()
        )
        self.runtime_event_classifier = RuntimeEventClassifier()
        self.runtime_event_policy = RuntimeEventPolicy(self.recovery_recipe_registry)
        self.candidate_resolver = CandidateResolver(self.agent_registry)
        self.proposal_factory = DeterministicProposalFactory()
        self.patch_compiler = RuntimeGraphPatchCompiler()
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
    def plugin_scope_resolver(self) -> PluginScopeResolver:
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
        """Inject the application-owned structured model runtime into ACG agents."""

        self.orchestrator.set_model_runtime(model_runtime)

    @property
    def planning_engine(self):
        if self._planning_engine is None:
            from agentos.core.planning import PlanningEngine

            self._planning_engine = PlanningEngine(
                workflow_registry=self.workflow_registry,
                agent_registry=self.agent_registry,
                capability_catalog=self.capability_catalog,
                intent_llm=self._intent_llm,
            )
        return self._planning_engine

    def register_execution_adapter(self, runtime_engine: str, factory: ExecutionAdapterFactory) -> None:
        engine = self._normalize_runtime_engine(runtime_engine)
        if engine == "acg":
            raise ValueError(f"{engine} runtime engine is built into AgentOS Core")
        self.execution_adapter_factories[engine] = factory

    def create_task(
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
    ) -> AgentTask:
        task_domain = (role_type or domain or "general").strip()
        task_intent = (task_type or intent or "general").strip()
        resolved_plugins = self.plugin_scope_resolver.resolve_enabled_plugin_ids(
            enabled_plugin_ids,
            workflow_id=workflow_id,
            domain=task_domain,
            intent=task_intent,
        )
        scope = self.plugin_scope_resolver.build_scope(resolved_plugins)
        return self.task_manager.create_task(
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
        )

    async def start(
        self,
        task_id: str,
        workflow_id: Optional[str] = None,
        review_mode: str = "auto",
        enabled_plugin_ids: Optional[list[str]] = None,
    ) -> WorkflowRun:
        _, run = self.prepare_run(
            task_id=task_id,
            workflow_id=workflow_id,
            review_mode=review_mode,
            enabled_plugin_ids=enabled_plugin_ids,
        )
        return await self.execute_prepared_run(run.run_id)

    def prepare_run(
        self,
        task_id: str,
        workflow_id: Optional[str] = None,
        review_mode: str = "auto",
        *,
        idempotency_key: Optional[str] = None,
        idempotency_fingerprint: Optional[str] = None,
        enabled_plugin_ids: Optional[list[str]] = None,
    ) -> tuple[AgentTask, WorkflowRun]:
        """Persist a queryable run before planning or node execution starts."""

        if idempotency_key:
            existing = self.workflow_store.find_run_by_idempotency_key(idempotency_key)
            if existing is not None:
                if existing.idempotency_fingerprint != idempotency_fingerprint:
                    raise ValueError("idempotency key conflicts with the workflow start request")
                return self.task_manager.get_task(existing.task_id), existing

        task = self.task_manager.get_task(task_id)
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
        workflow = self._resolve_workflow(
            task,
            workflow_id,
            allowed_workflow_ids=scope.workflow_ids,
        )
        is_acg = workflow.effective_runtime_engine == "acg"
        planning_diversity = normalize_planning_diversity(
            task.input.get("planningDiversity")
        )
        planning_seed = normalize_planning_seed(task.input.get("planningSeed"))
        if planning_diversity != "stable" and planning_seed is None:
            planning_seed = secrets.randbits(53)
        run_input = dict(task.input)
        run_input["planningDiversity"] = planning_diversity
        if planning_seed is not None:
            run_input["planningSeed"] = planning_seed
        run = WorkflowRun(
            taskId=task.task_id,
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
                "pluginScopeResolution": (
                    "legacy_compatibility" if requested_plugins is None else "explicit"
                ),
                "visibleCapabilityCount": len(scope.capability_ids),
                "scopeExcludedAgentCount": max(
                    0, len(tuple(self.agent_registry.all())) - len(scope.agent_ids)
                ),
                "planningDiversity": planning_diversity,
                "planningSeed": planning_seed,
                "plannerAlgorithmVersion": PLANNER_ALGORITHM_VERSION,
            },
        )
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
        self.workflow_store.save_run(run)
        logger.info(
            "run_prepared",
            extra={
                "taskId": task.task_id,
                "runId": run.run_id,
                "workflowId": workflow.workflow_id,
                "phase": run.lifecycle_phase.value,
            },
        )
        return task, run

    async def execute_prepared_run(self, run_id: str) -> WorkflowRun:
        """Execute an already-persisted run while preserving terminal state."""

        run = self.workflow_store.get_run(run_id)
        if run.status in _TERMINAL_RUN_STATUSES:
            return run

        task = self.task_manager.get_task(run.task_id)
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
            self.task_manager.mark_running(task)
            logger.info(
                "run_execution_started",
                extra={
                    "taskId": task.task_id,
                    "runId": run.run_id,
                    "workflowId": workflow.workflow_id,
                    "phase": run.lifecycle_phase.value,
                },
            )
            adapter = self._workflow_adapter(workflow)
            result = await adapter.start(task=task, run=run, workflow=workflow)
            persisted = self.workflow_store.get_run(result.run_id)
            if persisted.status in _TERMINAL_RUN_STATUSES and persisted.status != result.status:
                result = persisted
            logger.info(
                "run_execution_completed",
                extra={
                    "taskId": task.task_id,
                    "runId": result.run_id,
                    "workflowId": workflow.workflow_id,
                    "phase": result.lifecycle_phase.value if result.lifecycle_phase else None,
                    "elapsedMs": int((monotonic() - started) * 1000),
                },
            )
            return result
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
                extra={
                    "taskId": task.task_id,
                    "runId": run.run_id,
                    "workflowId": workflow.workflow_id,
                    "phase": WorkflowProgressPhase.FAILED.value,
                    "elapsedMs": int((monotonic() - started) * 1000),
                    "errorType": type(exc).__name__,
                },
            )
            raise

    async def _start_acg(
        self,
        *,
        task: AgentTask,
        run: WorkflowRun,
        workflow: WorkflowDefinition,
        executor,
    ) -> WorkflowRun:
        """ACG 执行路径入口：构建蓝图并交给就绪集调度执行器。"""
        self.trace_store.append(
            run=run,
            event_type=TraceEventType.TASK_CREATED,
            observation=f"Task created: {task.title}",
            payload=task.model_dump(by_alias=True, mode="json"),
        )
        planning_started = monotonic()
        logger.info(
            "run_planning_started",
            extra={"taskId": task.task_id, "runId": run.run_id, "workflowId": workflow.workflow_id},
        )
        blueprint = await asyncio.to_thread(self._build_acg_blueprint, task, run, workflow)
        run = self._set_run_lifecycle(
            run,
            phase=WorkflowProgressPhase.GRAPH_BUILDING,
            message=_LIFECYCLE_MESSAGES[WorkflowProgressPhase.GRAPH_BUILDING],
        )
        if run.status in _TERMINAL_RUN_STATUSES:
            return run
        logger.info(
            "run_planning_completed",
            extra={
                "taskId": task.task_id,
                "runId": run.run_id,
                "workflowId": workflow.workflow_id,
                "phase": run.lifecycle_phase.value,
                "elapsedMs": int((monotonic() - planning_started) * 1000),
            },
        )
        self._validate_blueprint_agents(
            blueprint,
            domain=workflow.domain or task.domain,
            scope=run.execution_scope,
        )
        run.execution_state["workflowVersion"] = workflow.version
        run.execution_state["graphId"] = blueprint.graph_id
        run.execution_state["sourceBlueprintVersion"] = blueprint.version
        run.execution_state["graphVersion"] = 1
        thinking_mode = str(run.input.get("thinkingMode") or "").strip()
        if thinking_mode:
            run.execution_state["thinkingMode"] = thinking_mode
        self._sync_run_steps_to_acg(run, blueprint)
        run.acg_blueprint = blueprint.model_dump(by_alias=True, mode="json")
        run.updated_at = utc_now()
        self.workflow_store.save_run(run)
        await self.runtime_controller.initialize_from_blueprint(run.run_id, blueprint)
        run = self.workflow_store.get_run(run.run_id)
        run = self._set_run_lifecycle(
            run,
            phase=WorkflowProgressPhase.EXECUTING,
            message=_LIFECYCLE_MESSAGES[WorkflowProgressPhase.EXECUTING],
        )
        if run.status in _TERMINAL_RUN_STATUSES:
            return run
        return await executor.run(task=task, run=run, workflow=workflow, blueprint=blueprint)

    def _validate_blueprint_agents(
        self,
        blueprint: ACGBlueprint,
        *,
        domain: str,
        scope: RunExecutionScope | None = None,
    ) -> None:
        missing: list[str] = []
        for step in blueprint.step_nodes():
            try:
                self.agent_registry.resolve(
                    domain=domain,
                    agent_name=step.agent_name,
                    capability=step.capability,
                    allowed_agent_ids=(scope.agent_ids if scope is not None else None),
                )
            except KeyError:
                missing.append(step.agent_name or step.node_id)
        if missing:
            raise ValueError("ACG references unregistered Agents: " + ", ".join(sorted(set(missing))))

    def _build_acg_blueprint(
        self,
        task: AgentTask,
        run: WorkflowRun,
        workflow: WorkflowDefinition,
    ) -> ACGBlueprint:
        """获取 ACG 蓝图，三级优先级：

        1. 现成蓝图：run.input['acgBlueprint'] 或 run.acg_blueprint（外部/前序产物）。
        2. 认知规划引擎：task.input['usePlanner'] 为真，或工作流未定义 steps，
           则调 PlanningEngine 走“静态优选、动态补位”生成 ACG，并把规划决策入 Trace。
        3. 线性升格：默认把静态工作流定义无损升格（行为等价线性执行）。
        """
        provided = run.input.get("acgBlueprint") or (run.acg_blueprint if run.acg_blueprint else None)
        if isinstance(provided, dict) and provided.get("nodes"):
            blueprint = ACGBlueprint.model_validate(provided)
            if not blueprint.task_id:
                blueprint = blueprint.model_copy(deep=True, update={"task_id": task.task_id})
            return blueprint

        planning_mode = str(run.input.get("planningMode") or "").strip().lower()
        force_dynamic = (
            workflow.is_native_bootstrap
            or bool(run.input.get("forceDynamicPlanning"))
            or planning_mode == "dynamic"
        )
        use_planner = force_dynamic or bool(run.input.get("usePlanner")) or not workflow.steps
        if use_planner:
            intent_text = str(
                run.input.get("userIntent")
                or run.input.get("intent")
                or task.title
                or workflow.description
            )
            planning_engine = self._planning_engine_for_run(run)
            plan = planning_engine.plan(
                task_id=task.task_id,
                intent=intent_text,
                domain=workflow.domain or task.domain,
                task_type=task.intent or workflow.intent,
                force_dynamic=force_dynamic,
                thinking_mode=str(run.input.get("thinkingMode") or "").strip() or None,
                # 强制动态图仍使用本地语义解析以避免模型往返；拓扑多样性由
                # 已持久化 seed 驱动，并且只作用于受约束的规划候选。
                deterministic_intent=force_dynamic,
                planning_diversity=run.planning_diversity,
                planning_seed=run.planning_seed,
                capability_catalog_revision=run.capability_catalog_revision,
            )
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
            return plan.blueprint

        return promote_workflow_to_acg(workflow, task_id=task.task_id)

    def _sync_run_steps_to_acg(self, run: WorkflowRun, blueprint: ACGBlueprint) -> None:
        """让 WorkflowRun 的步骤列表与最终 ACG 蓝图保持一致。"""
        existing = {step.step_id: step for step in run.steps}
        synced: list[WorkflowStep] = []
        for node in blueprint.step_nodes():
            step = existing.get(node.node_id)
            if step is None:
                step = WorkflowStep(
                    stepId=node.node_id,
                    name=node.name or node.node_id,
                    agentName=node.agent_name or node.node_id,
                    capability=node.capability,
                    input=dict(node.input_spec),
                    outputSpec=dict(node.output_spec),
                    reviewRequired=node.review_required,
                    maxRetries=node.retry_limit,
                    timeout=node.timeout,
                    priority=node.priority,
                )
            else:
                step.name = node.name or step.name
                step.agent_name = node.agent_name or step.agent_name
                step.capability = node.capability
                step.input = dict(node.input_spec)
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

    async def _apply_acg_review(self, decision: ReviewDecision, *, executor) -> WorkflowRun:
        if decision.decision == ReviewDecisionType.CANCELLED:
            return self.cancel(decision.run_id)
        should_resume = False
        async with self.run_lock_manager.lock_for(decision.run_id):
            latest = self.workflow_store.get_run(decision.run_id)
            run = latest.model_copy(deep=True)
            task = self.task_manager.get_task(run.task_id)
            workflow = self._workflow_for_run(run)
            graph = run.runtime_graph
            if graph is None:
                raise RuntimeGraphError("RUNTIME_GRAPH_MISSING", "review requires RuntimeGraph")
            node = graph.get_node(decision.step_id)
            if node.status != StepStatus.WAITING_REVIEW:
                raise ReviewConflictError("runtime node is no longer waiting for review")
            self.review_manager.record(run, decision)

            if decision.decision == ReviewDecisionType.APPROVED:
                self.runtime_controller.transition_node_state(node, StepStatus.COMPLETED)
                if node.attempts:
                    node.attempts[-1].status = StepStatus.COMPLETED
                    node.attempts[-1].ended_at = utc_now()
                self._transition_run(run, WorkflowStatus.RUNNING)
                self.task_manager.mark_running(task)
                should_resume = True
            elif decision.decision == ReviewDecisionType.RERUN:
                self.runtime_controller.transition_node_state(node, StepStatus.RETRYING)
                self._transition_run(run, WorkflowStatus.RETRYING)
                self.task_manager.mark_retrying(task)
                should_resume = True
            elif decision.decision == ReviewDecisionType.NEED_MORE_INFO:
                run.error = decision.comment or "Reviewer requested more information."
                self.task_manager.mark_waiting_review(task)
            else:
                self.runtime_controller.transition_node_state(node, StepStatus.FAILED)
                self._transition_run(run, WorkflowStatus.FAILED)
                run.error = decision.comment or "Review rejected workflow step."
                self.task_manager.mark_failed(task)
                self.trace_store.append(
                    run=run, event_type=TraceEventType.RUN_FAILED,
                    step_id=node.node_id, observation=run.error,
                )
            from agentos.core.execution.projection import refresh_run_execution_projection

            refresh_run_execution_projection(run)
            self._create_checkpoint(run, run.get_step(decision.step_id))
            self.workflow_store.save_run(run)
        if not should_resume:
            return run
        blueprint = ACGBlueprint.model_validate(run.acg_blueprint) if run.acg_blueprint else promote_workflow_to_acg(workflow, task_id=task.task_id)
        return await executor.resume(task=task, run=run, workflow=workflow, blueprint=blueprint)

    def _transition_run_if_needed(self, run: WorkflowRun, status: WorkflowStatus) -> None:
        if run.status != status:
            self._transition_run(run, status)

    def get_status(self, run_id: str) -> WorkflowRun:
        return self.workflow_store.get_run(run_id)

    async def update_run_lifecycle(
        self,
        run_id: str,
        *,
        status: WorkflowStatus | None = None,
        phase: WorkflowProgressPhase | None = None,
        message: str | None = None,
        error: object = _ERROR_UNSET,
        set_started_at: bool = False,
    ) -> WorkflowRun:
        """Reload, guard, persist, and return the latest lifecycle snapshot."""

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
        run: WorkflowRun,
        *,
        status: WorkflowStatus | None = None,
        phase: WorkflowProgressPhase | None = None,
        message: str | None = None,
        error: object = _ERROR_UNSET,
        set_started_at: bool = False,
    ) -> WorkflowRun:
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
    ) -> WorkflowRun:
        """Best-effort terminal failure used by managed execution boundaries."""

        run = self.workflow_store.get_run(run_id)
        if run.status in _TERMINAL_RUN_STATUSES:
            return run
        error = {
            "code": error_code,
            "message": error_message[:500],
        }
        self._terminalize_active_execution(run, error["message"])
        run = self._set_run_lifecycle(
            run,
            status=WorkflowStatus.FAILED,
            phase=WorkflowProgressPhase.FAILED,
            message=_LIFECYCLE_MESSAGES[WorkflowProgressPhase.FAILED],
            error=error,
        )
        try:
            self.task_manager.mark_failed(run.task_id)
        except Exception:
            logger.exception(
                "Failed to align task status after run failure",
                extra={"taskId": run.task_id, "runId": run.run_id},
            )
        self.trace_store.append(
            run=run,
            event_type=TraceEventType.RUN_FAILED,
            observation=error["message"],
            payload=error,
        )
        run.updated_at = utc_now()
        self.workflow_store.save_run(run)
        return run

    @staticmethod
    def _terminalize_active_execution(
        run: WorkflowRun,
        error_message: str,
        *,
        include_current_pending: bool = False,
    ) -> None:
        """Close active nodes before a failed Run is validated and persisted."""

        ended_at = utc_now()
        active_statuses = {StepStatus.RUNNING, StepStatus.RETRYING}
        current_step_id = run.current_step_id if include_current_pending else None
        if run.runtime_graph is not None:
            for node in run.runtime_graph.nodes:
                should_fail_node = node.status in active_statuses or bool(
                    current_step_id
                    and node.node_id == current_step_id
                    and node.status == StepStatus.PENDING
                )
                if should_fail_node:
                    node.status = StepStatus.FAILED
                    node.error = error_message
                    node.updated_at = ended_at
                if (
                    node.status == StepStatus.FAILED
                    and node.attempts
                    and node.attempts[-1].status in active_statuses
                ):
                    attempt = node.attempts[-1]
                    attempt.status = StepStatus.FAILED
                    attempt.error = error_message
                    attempt.ended_at = ended_at
            refresh_run_execution_projection(run)
            return

        for step in run.steps:
            if step.status in active_statuses or (
                current_step_id
                and step.step_id == current_step_id
                and step.status == StepStatus.PENDING
            ):
                step.status = StepStatus.FAILED
                step.error = error_message
                step.completed_at = ended_at
        run.active_step_ids = []

    async def close_orphaned_runs(self, *, limit: int = 200) -> list[str]:
        """Close unfinished runs whose in-process executor was lost on restart."""

        closed: list[str] = []
        for run in self.workflow_store.list_non_terminal_runs(limit=limit):
            if run.status == WorkflowStatus.WAITING_REVIEW:
                if self._normalize_waiting_review_after_restart(run):
                    run.updated_at = utc_now()
                    self.workflow_store.save_run(run)
                continue
            if run.status not in {
                WorkflowStatus.PENDING,
                WorkflowStatus.PLANNING,
                WorkflowStatus.RUNNING,
                WorkflowStatus.RETRYING,
            }:
                continue
            self._fail_interrupted_run_after_restart(run)
            closed.append(run.run_id)
            logger.warning(
                "interrupted_run_closed_after_restart",
                extra={
                    "taskId": run.task_id,
                    "runId": run.run_id,
                    "workflowId": run.workflow_id,
                    "phase": run.lifecycle_phase.value if run.lifecycle_phase else None,
                },
            )
        return closed

    @staticmethod
    def _normalize_waiting_review_after_restart(run: WorkflowRun) -> bool:
        """Align both persisted step projections without leaving review state."""

        changed = False
        waiting_ids = {
            step.step_id for step in run.steps if step.status == StepStatus.WAITING_REVIEW
        }
        if run.runtime_graph is not None:
            waiting_ids.update(
                node.node_id
                for node in run.runtime_graph.nodes
                if node.status == StepStatus.WAITING_REVIEW
            )
        if not waiting_ids and run.current_step_id:
            waiting_ids.add(run.current_step_id)
        for step in run.steps:
            if step.step_id in waiting_ids and step.status != StepStatus.WAITING_REVIEW:
                step.status = StepStatus.WAITING_REVIEW
                changed = True
        if run.runtime_graph is not None:
            for node in run.runtime_graph.nodes:
                if node.node_id in waiting_ids and node.status != StepStatus.WAITING_REVIEW:
                    node.status = StepStatus.WAITING_REVIEW
                    node.updated_at = utc_now()
                    changed = True
        if run.lifecycle_phase != WorkflowProgressPhase.REVIEW:
            run.lifecycle_phase = WorkflowProgressPhase.REVIEW
            changed = True
        if run.lifecycle_message != _LIFECYCLE_MESSAGES[WorkflowProgressPhase.REVIEW]:
            run.lifecycle_message = _LIFECYCLE_MESSAGES[WorkflowProgressPhase.REVIEW]
            changed = True
        return changed

    def _fail_interrupted_run_after_restart(self, run: WorkflowRun) -> None:
        """Mutate every run projection first, then persist one consistent snapshot."""

        interruption_message = "任务因服务重启而中断。"
        self._terminalize_active_execution(
            run,
            interruption_message,
            include_current_pending=True,
        )
        run.status = WorkflowStatus.FAILED
        run.lifecycle_phase = WorkflowProgressPhase.FAILED
        run.lifecycle_message = interruption_message
        run.error = {
            "code": "interrupted_after_restart",
            "message": interruption_message,
        }
        try:
            self.task_manager.mark_failed(run.task_id)
        except Exception:
            logger.exception(
                "Failed to align task status after interrupted run",
                extra={"taskId": run.task_id, "runId": run.run_id},
            )
        self.trace_store.append(
            run=run,
            event_type=TraceEventType.RUN_FAILED,
            observation=interruption_message,
            payload=dict(run.error),
        )
        run.updated_at = utc_now()
        self.workflow_store.save_run(run)

    @staticmethod
    def _safe_error_message(exc: BaseException) -> str:
        message = str(exc).strip()
        return (message or type(exc).__name__)[:500]

    def resolve_workflow_id(self, workflow_id: str | None) -> str | None:
        if not workflow_id:
            return workflow_id
        return self.workflow_registry.get(workflow_id).workflow_id

    def list_checkpoints(self, run_id: str) -> list[Checkpoint]:
        return self.checkpoint_store.list(self.workflow_store.get_run(run_id))

    def list_reviews(self, run_id: str) -> list[ReviewRecord]:
        return self.review_manager.list(self.workflow_store.get_run(run_id))

    def evaluate_runs(
        self,
        *,
        status: WorkflowStatus | str | None = None,
        domain: str | None = None,
        workflow_id: str | None = None,
        source: str | None = None,
    ) -> EvaluationRun:
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

    async def apply_review(self, decision: ReviewDecision) -> WorkflowRun:
        async with self.run_lock_manager.lock_for(decision.run_id):
            run = self.workflow_store.get_run(decision.run_id)
            existing = self._find_review_operation(run, decision.operation_id)
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

    @staticmethod
    def _find_review_operation(run: WorkflowRun, operation_id: str | None) -> dict | None:
        if not operation_id:
            return None
        for event in run.trace:
            if event.event_type != TraceEventType.REVIEW_DECIDED:
                continue
            payload = event.payload or {}
            if payload.get("operationId") == operation_id:
                return payload
        return None

    async def resume_from_checkpoint(self, *, run_id: str, checkpoint_id: str) -> WorkflowRun:
        # Explicitly initialize legacy ACG runs before comparing checkpoint graph
        # versions.  No checkpoint field is copied into the run before this check.
        initial_run = self.workflow_store.get_run(run_id)
        initial_workflow = self._workflow_for_run(initial_run)
        if initial_run.runtime_engine != "acg" or initial_workflow.effective_runtime_engine != "acg":
            raise ValueError("Only acg workflow runs can be resumed from checkpoints")
        await self.runtime_controller.load(run_id)
        async with self.run_lock_manager.lock_for(run_id):
            run = self.workflow_store.get_run(run_id)
            task = self.task_manager.get_task(run.task_id)
            workflow = self._workflow_for_run(run)
            checkpoint = self.checkpoint_store.find(run, checkpoint_id)
            snapshot = checkpoint.state_snapshot or {}
            snapshot_scope = snapshot.get("executionScope")
            if snapshot_scope is None:
                raise PluginScopeError(
                    "CHECKPOINT_PLUGIN_SNAPSHOT_MISSING",
                    checkpoint.checkpoint_id,
                )
            restored_scope = RunExecutionScope.model_validate(snapshot_scope)
            if run.execution_scope != restored_scope:
                raise PluginScopeError(
                    "CHECKPOINT_PLUGIN_SCOPE_CONFLICT",
                    checkpoint.checkpoint_id,
                )
            self.plugin_scope_resolver.validate_snapshot(restored_scope)
            snapshot_workflow_version = snapshot.get("workflowVersion")
            if snapshot_workflow_version and snapshot_workflow_version != workflow.version:
                raise ValueError(
                    f"Checkpoint workflow version mismatch: {snapshot_workflow_version} != {workflow.version}"
                )

            current_graph = run.runtime_graph
            assert current_graph is not None
            raw_checkpoint_graph = snapshot.get("runtimeGraph")
            if isinstance(raw_checkpoint_graph, dict):
                checkpoint_graph = RuntimeGraph.model_validate(raw_checkpoint_graph)
            else:
                legacy_blueprint_data = snapshot.get("acgBlueprint") or run.acg_blueprint
                if not legacy_blueprint_data:
                    raise RuntimeGraphError(
                        "CHECKPOINT_RUNTIME_GRAPH_MISSING",
                        "legacy checkpoint has neither RuntimeGraph nor ACG blueprint",
                    )
                checkpoint_graph = RuntimeGraph.from_blueprint(
                    run_id=run_id,
                    blueprint=ACGBlueprint.model_validate(legacy_blueprint_data),
                    agent_registry=self.agent_registry,
                    domain=run.domain,
                )
            if checkpoint_graph.graph_id != current_graph.graph_id:
                raise RuntimeGraphError(
                    "CHECKPOINT_GRAPH_ID_CONFLICT",
                    f"checkpoint {checkpoint_graph.graph_id} != current {current_graph.graph_id}",
                )
            if checkpoint_graph.graph_version != current_graph.graph_version:
                relation = "older" if checkpoint_graph.graph_version < current_graph.graph_version else "newer"
                raise RuntimeGraphError(
                    "CHECKPOINT_GRAPH_VERSION_CONFLICT",
                    f"checkpoint graphVersion {checkpoint_graph.graph_version} is {relation} than current "
                    f"graphVersion {current_graph.graph_version}",
                )

            if "provenance" in snapshot:
                run.provenance = snapshot["provenance"]
            if isinstance(snapshot.get("executionState"), dict):
                run.execution_state = dict(snapshot["executionState"])
            run.runtime_graph = checkpoint_graph.model_copy(deep=True)
            run.execution_state["graphId"] = checkpoint_graph.graph_id
            run.execution_state["graphVersion"] = checkpoint_graph.graph_version
            run.execution_state["sourceBlueprintVersion"] = checkpoint_graph.source_blueprint_version
            if "output" in snapshot:
                run.output = dict(snapshot["output"] or {})
            blueprint = (
                ACGBlueprint.model_validate(run.acg_blueprint)
                if run.acg_blueprint
                else promote_workflow_to_acg(workflow, task_id=task.task_id)
            )

            for node in run.runtime_graph.nodes:
                if node.status in {StepStatus.RUNNING, StepStatus.FAILED}:
                    if node.status == StepStatus.RUNNING and node.attempts:
                        node.attempts[-1].status = StepStatus.FAILED
                        node.attempts[-1].error = "interrupted by checkpoint recovery"
                        node.attempts[-1].ended_at = utc_now()
                    self.runtime_controller.transition_node_state(node, StepStatus.RETRYING)

            from agentos.core.execution.projection import refresh_run_execution_projection

            refresh_run_execution_projection(run)

            self._transition_run(run, WorkflowStatus.RETRYING)
            run.error = None
            run.recovery_count += 1
            self.task_manager.mark_retrying(task)
            self.trace_store.append(
                run=run,
                event_type=TraceEventType.RUN_RECOVERED,
                step_id=checkpoint.step_id,
                observation=f"Recovered from checkpoint: {checkpoint.checkpoint_id}",
                payload=checkpoint_trace_payload(checkpoint),
            )
            self.workflow_store.save_run(run)
        adapter = self._workflow_adapter(workflow)
        assert isinstance(adapter, ACGWorkflowAdapter)
        return await adapter.new_executor().resume(
            task=task,
            run=run,
            workflow=workflow,
            blueprint=blueprint,
        )

    def cancel(self, run_id: str) -> WorkflowRun:
        with self.run_lock_manager.lock_for(run_id):
            latest = self.workflow_store.get_run(run_id)
            run = latest.model_copy(deep=True)
            self._transition_run(run, WorkflowStatus.CANCELLED)
            if run.runtime_graph is not None:
                for node in run.runtime_graph.nodes:
                    if node.status in {
                        StepStatus.PENDING,
                        StepStatus.RUNNING,
                        StepStatus.RETRYING,
                        StepStatus.WAITING_REVIEW,
                    }:
                        self.runtime_controller.transition_node_state(node, StepStatus.CANCELLED)
                        if node.attempts and node.attempts[-1].status == StepStatus.RUNNING:
                            node.attempts[-1].status = StepStatus.CANCELLED
                            node.attempts[-1].ended_at = utc_now()
                from agentos.core.execution.projection import refresh_run_execution_projection

                refresh_run_execution_projection(run)
            self.task_manager.mark_cancelled(run.task_id)
            self.trace_store.append(
                run=run,
                event_type=TraceEventType.RUN_CANCELLED,
                observation="Workflow cancelled.",
            )
            self.workflow_store.save_run(run)
            return run

    def _resolve_workflow(
        self,
        task: AgentTask,
        workflow_id: Optional[str],
        *,
        allowed_workflow_ids: tuple[str, ...] | None = None,
    ) -> WorkflowDefinition:
        return self.task_manager.bind_workflow(
            task,
            workflow_id=workflow_id,
            allowed_workflow_ids=allowed_workflow_ids,
        )

    def _planning_engine_for_run(self, run: WorkflowRun):
        if run.execution_scope is None:
            return self.planning_engine
        from agentos.core.planning import PlanningEngine

        return PlanningEngine(
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

    def _workflow_for_run(self, run: WorkflowRun) -> WorkflowDefinition:
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
                adapter = ACGWorkflowAdapter(self)
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
        run: WorkflowRun,
        task: AgentTask,
        step: WorkflowStep,
        exc: Exception,
    ) -> None:
        step.error = str(exc)
        if step.retry_count < step.max_retries:
            step.retry_count += 1
            self._transition_step(step, StepStatus.RETRYING)
            self._transition_run(run, WorkflowStatus.RETRYING)
            self.task_manager.mark_retrying(task)
        else:
            self._transition_step(step, StepStatus.FAILED)
            self._transition_run(run, WorkflowStatus.FAILED)
            self.task_manager.mark_failed(task)
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

    def _transition_run(self, run: WorkflowRun, status: WorkflowStatus) -> None:
        try:
            persisted = self.workflow_store.get_run(run.run_id)
        except KeyError:
            persisted = run
        if persisted.status in _TERMINAL_RUN_STATUSES and persisted.status != run.status:
            for field_name in WorkflowRun.model_fields:
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

    def _complete_run(self, task: AgentTask, run: WorkflowRun) -> None:
        self._transition_run(run, WorkflowStatus.COMPLETED)
        if run.status != WorkflowStatus.COMPLETED:
            return
        if run.recovery_count:
            run.lifecycle_message = f"ACG 工作流执行完成（含 {run.recovery_count} 次降级恢复）"
        run.current_step_id = None
        run.output = self.orchestrator.compose_final_output(run)
        self.task_manager.mark_completed(task)
        self.trace_store.append(
            run=run,
            event_type=TraceEventType.RUN_COMPLETED,
            observation="Workflow completed.",
            payload=run.output,
        )

    def _create_checkpoint(
        self,
        run: WorkflowRun,
        step: WorkflowStep,
        *,
        step_ids: list[str] | None = None,
    ) -> Checkpoint:
        checkpoint = self.checkpoint_store.create(
            run,
            step.step_id,
            step_ids=step_ids,
        )
        self.trace_store.append(
            run=run,
            event_type=TraceEventType.CHECKPOINT_CREATED,
            step_id=step.step_id,
            observation=f"Checkpoint created: {checkpoint.checkpoint_id}",
            payload=checkpoint_trace_payload(checkpoint),
        )
        return checkpoint


def build_default_runtime() -> WorkflowRuntime:
    agent_registry = AgentRegistry()
    workflow_registry = WorkflowRegistry()

    db_path = os.getenv("AGENTOS_WORKFLOW_DB_PATH", "").strip()
    workflow_store: WorkflowStore
    if not db_path:
        raise RuntimeError("Workflow database path is required outside test mode.")
    workflow_store = SQLiteWorkflowStore(db_path)

    runtime = WorkflowRuntime(
        agent_registry=agent_registry,
        workflow_registry=workflow_registry,
        workflow_store=workflow_store,
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


__all__ = ["WorkflowRuntime", "build_default_runtime"]
