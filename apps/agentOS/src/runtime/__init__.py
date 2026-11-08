"""运行时部件的包边界；业务实现将在后续迁移。"""

__all__: list[str] = []
"""运行时部件的公共入口。

恢复控制器会在运行时初始化之前使用锁模块，因此这里采用惰性导出，避免
``recovery -> runtime.compatibility -> runtime`` 形成包初始化环。
"""

from .bootstrap import bootstrap


_RUNTIME_V2_NAMES = {
    "AcgIdentityLifecycleService",
    "ExecutionContext",
    "IdentityProjectionBridge",
    "IdentityProjectionReconciler",
    "IdentityReconciliationReport",
    "IdentityQueryService",
    "MissionWorkspaceProjection",
    "MissionWorkspaceProjector",
    "WorkspaceDiagnostic",
    "WorkspaceEntry",
    "WorkspaceEntryKind",
    "WorkspaceGraphNode",
    "WorkspaceIdentityQuality",
    "WorkspaceRunSummary",
    "PlannerIdentityBridge",
    "TaskImplementationBinding",
    "TaskPlan",
    "PlannedTask",
    "TaskPlanPatch",
}


def __getattr__(name: str):
    if name in {"ApplicationSetup", "ApplicationSetupError", "ModelSetup"}:
        from .app_setup import ApplicationSetup, ApplicationSetupError, ModelSetup

        return {
            "ApplicationSetup": ApplicationSetup,
            "ApplicationSetupError": ApplicationSetupError,
            "ModelSetup": ModelSetup,
        }[name]
    if name in {"ExecutionRuntime", "build_default_runtime"}:
        from .workflow_runtime import ExecutionRuntime, build_default_runtime

        return {
            "ExecutionRuntime": ExecutionRuntime,
            "build_default_runtime": build_default_runtime,
        }[name]
    if name in _RUNTIME_V2_NAMES:
        from . import (
            context,
            identity_projection,
            planner_bridge,
            queries,
            reconciliation,
            runner,
            workspace,
        )
        from contracts.planning import (
            TaskImplementationBinding,
            TaskPlan,
            PlannedTask,
            TaskPlanPatch,
        )

        mapping = {
            "AcgIdentityLifecycleService": runner.AcgIdentityLifecycleService,
            "ExecutionContext": context.ExecutionContext,
            "IdentityProjectionBridge": identity_projection.IdentityProjectionBridge,
            "IdentityProjectionReconciler": reconciliation.IdentityProjectionReconciler,
            "IdentityReconciliationReport": reconciliation.IdentityReconciliationReport,
            "IdentityQueryService": queries.IdentityQueryService,
            "MissionWorkspaceProjection": workspace.MissionWorkspaceProjection,
            "MissionWorkspaceProjector": workspace.MissionWorkspaceProjector,
            "WorkspaceDiagnostic": workspace.WorkspaceDiagnostic,
            "WorkspaceEntry": workspace.WorkspaceEntry,
            "WorkspaceEntryKind": workspace.WorkspaceEntryKind,
            "WorkspaceGraphNode": workspace.WorkspaceGraphNode,
            "WorkspaceIdentityQuality": workspace.WorkspaceIdentityQuality,
            "WorkspaceRunSummary": workspace.WorkspaceRunSummary,
            "PlannerIdentityBridge": planner_bridge.PlannerIdentityBridge,
            "TaskImplementationBinding": TaskImplementationBinding,
            "TaskPlan": TaskPlan,
            "PlannedTask": PlannedTask,
            "TaskPlanPatch": TaskPlanPatch,
        }
        return mapping[name]
    raise AttributeError(name)


__all__ = [
    "ApplicationSetup",
    "ApplicationSetupError",
    "ModelSetup",
    "ExecutionRuntime",
    "bootstrap",
    "build_default_runtime",
    "AcgIdentityLifecycleService",
    "ExecutionContext",
    "IdentityProjectionBridge",
    "IdentityProjectionReconciler",
    "IdentityReconciliationReport",
    "IdentityQueryService",
    "MissionWorkspaceProjection",
    "MissionWorkspaceProjector",
    "WorkspaceDiagnostic",
    "WorkspaceEntry",
    "WorkspaceEntryKind",
    "WorkspaceGraphNode",
    "WorkspaceIdentityQuality",
    "WorkspaceRunSummary",
    "PlannerIdentityBridge",
    "TaskImplementationBinding",
    "TaskPlan",
    "PlannedTask",
    "TaskPlanPatch",
]
