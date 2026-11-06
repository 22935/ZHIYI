"""PR-8C.3 提取边界的架构与特征化测试。

覆盖：
- 新增服务的 import 边界（不依赖 facade / Execution / 相互之间 / Planner）；
- facade 残留审计（review / recovery 实现调用不留在 workflow_runtime.py）；
- Run 锁 authority（ReviewService 与 RuntimeRecoveryCoordinator 不得加锁）；
- Review 幂等（C）、期望版本/步骤状态冲突（D）的迁移前后行为保持；
- 执行失败投影（FailureEvent → recoveryOutcome proposed）的持久化形状。
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

from runtime.workflow_runtime import ExecutionRuntime, ReviewConflictError as FacadeReviewConflictError
from runtime.review import ReviewConflictError as ServiceReviewConflictError
from components.auditor import SQLiteDecisionStore
from components.executor.value_store import SQLiteExecutionValueStore
from components.memory.store import SQLiteMemoryStore
from components.recovery.checkpoint import ACGCheckpointStore
from components.mission_manager.store import WorkflowRegistry
from contracts.workflow import (
    ReviewDecision,
    ReviewDecisionType,
    StepStatus,
    TraceEventType,
    WorkflowDefinition,
    WorkflowStepDefinition,
    WorkflowStatus,
)
from service.agents import AgentRegistry
from service.agents.base import AgentOutput, AgentProfile, BaseAgent
from support.stores.memory_workflow_store import MemoryWorkflowStore

RUNTIME_SOURCE = Path(__file__).resolve().parents[2] / "src" / "runtime"


class _ReviewAgent(BaseAgent):
    """稳定返回高风险结果，让单步 ACG 停在人工审核屏障。"""

    async def run(self, _context):
        return AgentOutput(
            output={"summary": "needs-human-review"},
            summary="needs-human-review",
            riskLevel="high",
        )


class _CrashAgent(BaseAgent):
    """确定性地在节点执行期抛错，用于固定失败投影形状。"""

    async def run(self, _context):
        raise RuntimeError("boom")


def _freeze_single_step_graph(runtime: ExecutionRuntime) -> None:
    """轻量 workflow 提升通道已删除:夹具显式冻结等价的单节点蓝图。"""
    from components.planner.acg_lowerer import ACGLowerer, ACGLoweringInput, ACGLoweringStep
    from contracts.planning import PlannedTask, TaskImplementationBinding, TaskPlan
    from support.acg.planning import ACGResourcePlan, AgentBindingSpec
    from support.acg.schema import ComplexityLevel

    def build(task, run, workflow):
        definition = workflow.steps[0]
        node_id = definition.step_id
        key = f"step:{node_id}"
        plan = TaskPlan(
            missionId=task.mission_id, planVersion=1,
            nodes=(PlannedTask(key=key, title=definition.name, objective=definition.name),),
        )
        lowering = ACGLoweringInput(
            mission_id=task.mission_id,
            objective=workflow.name,
            complexity_level=ComplexityLevel.SIMPLE,
            task_plan=plan,
            steps=(ACGLoweringStep(
                task_key=key, node_id=node_id, name=definition.name,
                goal=definition.name, metadata={"taskPlanKey": key},
            ),),
            implementation_bindings=(TaskImplementationBinding(planNodeKey=key, acgNodeId=node_id),),
            resource_plan=ACGResourcePlan(bindings=(AgentBindingSpec(
                stepId=node_id,
                plannedAgentId=definition.agent_name or node_id,
            ),)),
        )
        return ACGLowerer().lower(lowering), None, ()

    runtime._build_acg_blueprint = build


def _review_runtime(tmp_path: Path) -> ExecutionRuntime:
    agents = AgentRegistry()
    agents.register(_ReviewAgent(AgentProfile(agentName="reviewer", domain="general")))
    workflows = WorkflowRegistry()
    workflows.register(WorkflowDefinition(
        workflowId="audit-extraction", name="audit extraction", domain="general",
        runtimeEngine="acg",
        steps=[WorkflowStepDefinition(stepId="review", name="review", agentName="reviewer")],
    ))
    runtime = ExecutionRuntime(
        agent_registry=agents,
        workflow_registry=workflows,
        workflow_store=MemoryWorkflowStore(),
        checkpoint_store=ACGCheckpointStore(db_path=tmp_path / "checkpoints.sqlite3"),
        execution_value_store=SQLiteExecutionValueStore(db_path=tmp_path / "values.sqlite3"),
        memory_store=SQLiteMemoryStore(db_path=tmp_path / "memory.sqlite3"),
        decision_store=SQLiteDecisionStore(db_path=tmp_path / "decisions.sqlite3"),
    )
    _freeze_single_step_graph(runtime)
    return runtime


def _paused_review_run(runtime: ExecutionRuntime):
    task = runtime.create_mission("audit", workflow_id="audit-extraction")
    _, run = runtime.prepare_run(task.mission_id)
    paused = asyncio.run(runtime.execute_prepared_run(run.run_id))
    assert paused.status is WorkflowStatus.WAITING_REVIEW
    return paused


def _imported(module_file: str) -> tuple[set[str], set[str]]:
    tree = ast.parse((RUNTIME_SOURCE / module_file).read_text(encoding="utf-8"))
    modules: set[str] = set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
    return modules, names


# ---------------------------------------------------------------- architecture


def test_review_service_import_boundary() -> None:
    modules, names = _imported("review.py")
    for forbidden_module in (
        "runtime.workflow_runtime",
        "runtime.acg_execution",
        "runtime.runtime_recovery",
        "runtime.semantic_revision",
        "components.planner",
        "fastapi",
    ):
        assert forbidden_module not in modules
    for forbidden_name in ("ExecutionRuntime", "ACGExecutionService", "FastAPI"):
        assert forbidden_name not in names


def test_recovery_coordinator_import_boundary() -> None:
    modules, names = _imported("runtime_recovery.py")
    for forbidden_module in (
        "runtime.workflow_runtime",
        "runtime.review",
        "runtime.acg_execution",
        "runtime.semantic_revision",
        "components.planner",
        "fastapi",
    ):
        assert forbidden_module not in modules
    # 普通 retry/rebind/resume 不得触碰语义修订面（§九/characterization M）。
    for forbidden_name in (
        "ExecutionRuntime",
        "ReviewService",
        "ACGExecutionService",
        "SemanticRevisionService",
        "SemanticPatchRequest",
        "TaskPlanPatch",
        "GraphPatch",
        "GraphPatchResult",
    ):
        assert forbidden_name not in names


def test_ports_module_is_runtime_leaf() -> None:
    modules, names = _imported("ports.py")
    assert all(not module.startswith("runtime.") for module in modules)
    assert "ExecutionRuntime" not in names


def test_workflow_runtime_facade_residual_audit() -> None:
    source = (RUNTIME_SOURCE / "workflow_runtime.py").read_text(encoding="utf-8")
    for forbidden in (
        "_commit_deferred_memory",
        "_find_review_operation",
        "_apply_acg_review",
        "RecoveryService(",
        "failure_event_from_exception(",
        "BindingRequirement",
        "checkpoint_store.save(",
        "graph.astream(",
        "schedule_ready(",
        "ExecutionBinding(",
        "SemanticGraphPatchService(",
        "_terminalize_active_execution",
        "_normalize_waiting_review_after_restart",
        "_fail_interrupted_run_after_restart",
    ):
        assert forbidden not in source, f"workflow_runtime.py must not retain {forbidden!r}"


def test_review_and_recovery_never_take_run_locks() -> None:
    for module_file in ("review.py", "runtime_recovery.py"):
        tree = ast.parse((RUNTIME_SOURCE / module_file).read_text(encoding="utf-8"))
        attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        modules, imported_names = _imported(module_file)
        assert "lock_for" not in attrs, f"{module_file} must not acquire run locks"
        assert "run_lock_manager" not in names | attrs
        assert "RunLockManager" not in imported_names


def test_review_conflict_error_public_contract_preserved() -> None:
    assert FacadeReviewConflictError is ServiceReviewConflictError


def test_shared_runtime_collaborators_are_late_bound_without_resync(tmp_path) -> None:
    runtime = _review_runtime(tmp_path)
    replacement_store = MemoryWorkflowStore()
    replacement_checkpoints = ACGCheckpointStore(
        db_path=tmp_path / "replacement-checkpoints.sqlite3"
    )

    runtime.workflow_store = replacement_store
    runtime.checkpoint_store = replacement_checkpoints

    services = (
        runtime.acg_execution_service,
        runtime.acg_state_persistence,
        runtime.review_service,
        runtime.runtime_recovery_coordinator,
        runtime.semantic_revision_service,
    )
    assert all(service.workflow_store is replacement_store for service in services)
    assert all(
        service.checkpoint_store is replacement_checkpoints for service in services
    )

    facade_source = (RUNTIME_SOURCE / "workflow_runtime.py").read_text(
        encoding="utf-8"
    )
    assert "service.workflow_store =" not in facade_source
    assert "service.checkpoint_store =" not in facade_source


# ------------------------------------------------------------ characterization


def test_review_operation_idempotency_and_conflict(tmp_path) -> None:
    """C：相同 operation/decision 幂等，不同 decision 冲突。"""
    runtime = _review_runtime(tmp_path)
    paused = _paused_review_run(runtime)

    rejected = asyncio.run(runtime.apply_review(ReviewDecision(
        runId=paused.run_id,
        stepId="review",
        decision=ReviewDecisionType.REJECTED,
        operationId="op-reuse",
    )))
    assert rejected.status is WorkflowStatus.FAILED

    replayed = asyncio.run(runtime.apply_review(ReviewDecision(
        runId=paused.run_id,
        stepId="review",
        decision=ReviewDecisionType.REJECTED,
        operationId="op-reuse",
    )))
    assert replayed.status is WorkflowStatus.FAILED

    with pytest.raises(FacadeReviewConflictError, match="already used"):
        asyncio.run(runtime.apply_review(ReviewDecision(
            runId=paused.run_id,
            stepId="review",
            decision=ReviewDecisionType.APPROVED,
            operationId="op-reuse",
        )))

    # 对照组：无 operationId 的重复提交走状态拒绝，证明上面的冲突来自
    # operation 扫描而非状态检查的顺序巧合。
    with pytest.raises(FacadeReviewConflictError, match="no longer waiting"):
        asyncio.run(runtime.apply_review(ReviewDecision(
            runId=paused.run_id,
            stepId="review",
            decision=ReviewDecisionType.REJECTED,
        )))

    decided = [
        event for event in runtime.get_status(paused.run_id).trace
        if event.event_type is TraceEventType.REVIEW_DECIDED
    ]
    assert len(decided) == 1, "重复提交不得追加第二笔 REVIEW_DECIDED 事件"


def test_review_expected_revision_and_step_status_conflicts(tmp_path) -> None:
    """D：stale expected_run_updated_at / expected_step_status / 主体不匹配均拒绝。"""
    from datetime import timedelta

    runtime = _review_runtime(tmp_path)
    paused = _paused_review_run(runtime)
    snapshot = runtime.get_status(paused.run_id)
    stale_updated_at = snapshot.updated_at - timedelta(microseconds=1)

    with pytest.raises(FacadeReviewConflictError, match="revision changed"):
        asyncio.run(runtime.apply_review(ReviewDecision(
            runId=paused.run_id,
            stepId="review",
            decision=ReviewDecisionType.APPROVED,
            operationId="op-rev",
            expectedRunUpdatedAt=stale_updated_at,
        )))
    with pytest.raises(FacadeReviewConflictError, match="step state changed"):
        asyncio.run(runtime.apply_review(ReviewDecision(
            runId=paused.run_id,
            stepId="review",
            decision=ReviewDecisionType.APPROVED,
            operationId="op-step",
            expectedStepStatus=StepStatus.COMPLETED,
        )))
    with pytest.raises(FacadeReviewConflictError, match="persisted ACG subject"):
        asyncio.run(runtime.apply_review(ReviewDecision(
            runId=paused.run_id,
            stepId="not-the-review-step",
            decision=ReviewDecisionType.APPROVED,
            operationId="op-subject",
        )))


def test_concurrent_duplicate_review_operation_semantics(tmp_path) -> None:
    """§五：并发重复提交同一 operation，第二笔幂等读取已落地结果。"""
    runtime = _review_runtime(tmp_path)
    paused = _paused_review_run(runtime)

    async def submit_twice():
        decision = ReviewDecision(
            runId=paused.run_id,
            stepId="review",
            decision=ReviewDecisionType.REJECTED,
            operationId="op-concurrent",
        )
        return await asyncio.gather(
            runtime.apply_review(decision),
            runtime.apply_review(decision),
            return_exceptions=True,
        )

    first, second = asyncio.run(submit_twice())
    outcomes = [first, second]
    settled = [r for r in outcomes if not isinstance(r, BaseException)]
    assert len(settled) == 2
    assert all(item.status is WorkflowStatus.FAILED for item in settled)
    decided = [
        event for event in runtime.get_status(paused.run_id).trace
        if event.event_type is TraceEventType.REVIEW_DECIDED
    ]
    assert len(decided) == 1, "并发重复提交恰好一笔决定事件"


def test_execution_failure_projects_recovery_outcome(tmp_path) -> None:
    """§二十二：失败检测 → FailureEvent → recoveryOutcome(proposed) → 持久化收敛。"""
    agents = AgentRegistry()
    agents.register(_CrashAgent(AgentProfile(agentName="crasher", domain="general")))
    workflows = WorkflowRegistry()
    workflows.register(WorkflowDefinition(
        workflowId="crash-extraction", name="crash extraction", domain="general",
        runtimeEngine="acg",
        steps=[WorkflowStepDefinition(stepId="crash", name="crash", agentName="crasher")],
    ))
    runtime = ExecutionRuntime(
        agent_registry=agents,
        workflow_registry=workflows,
        workflow_store=MemoryWorkflowStore(),
        checkpoint_store=ACGCheckpointStore(db_path=tmp_path / "checkpoints.sqlite3"),
        execution_value_store=SQLiteExecutionValueStore(db_path=tmp_path / "values.sqlite3"),
        memory_store=SQLiteMemoryStore(db_path=tmp_path / "memory.sqlite3"),
        decision_store=SQLiteDecisionStore(db_path=tmp_path / "decisions.sqlite3"),
    )
    _freeze_single_step_graph(runtime)
    task = runtime.create_mission("crash", workflow_id="crash-extraction")
    _, run = runtime.prepare_run(task.mission_id)

    with pytest.raises(RuntimeError, match="failed=crash"):
        asyncio.run(runtime.execute_prepared_run(run.run_id))

    failed = runtime.get_status(run.run_id)
    assert failed.status is WorkflowStatus.FAILED
    failure_events = failed.execution_state.get("failureEvents")
    assert isinstance(failure_events, list) and failure_events, "FailureEvent 投影必须落库"
    outcome = failed.execution_state.get("recoveryOutcome")
    assert isinstance(outcome, dict)
    assert set(outcome) == {"failureId", "source", "reasonCode", "action", "status"}
    assert outcome["status"] == "proposed", "迁移前行为：建议只持久化不自动执行"
    assert outcome["failureId"] == failure_events[0]["failureId"]
