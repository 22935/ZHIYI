"""Facade 与已提取 runtime services 共享的类型化晚绑定协作者上下文。

PR-8C.3 之前，facade 在每次派发前把可变协作者逐项重对齐到服务属性
（约 24 项赋值），新增服务会把该数字继续放大。现在 facade 构造唯一一个
``RuntimeCollaborators`` 实例并按引用共享给全部服务：facade 侧属性写入
直接落到共享上下文，服务侧属性读取在调用时取最新值，派发前的重对齐
整体消失，也不存在任何被悄悄缓存的过期协作者。

本模块是叶子模块：只依赖 components / contracts / adapters / support，
禁止引用 ``runtime.workflow_runtime`` 或任何服务实现。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from adapters.model_compatibility import ModelCompatibilityRegistry
from adapters.resource_execution import ResourceExecutionAdapter
from components.auditor.decision_store import DecisionStore
from components.auditor.governance.trace import TraceStore
from components.communicator import SQLiteReliableCommunicationStore
from components.communicator.provenance_store import SQLiteProvenanceStore
from components.content import ContentManifestStore
from components.executor import ExecutionValueStore
from components.recovery.checkpoint import ACGCheckpointStore
from components.resource.application.resource_plane import ResourcePlane
from components.resource.scheduler.binder import ResourceBinder
from contracts.acg_lifecycle import AcgIdentityLifecyclePort
from service.agents import AgentRegistry
from support.acg.capabilities import CapabilityCatalog
from support.stores.workflow_store import WorkflowStore


@dataclass
class RuntimeCollaborators:
    """由 facade 持有并按引用共享给服务的可变协作者集合（全部为类型化字段）。

    构造后允许被替换的项（store、身份生命周期、调度参数等）都在这里；
    ``state_machine``、并发限流等一经构造即冻结的注入不进入本上下文。
    """

    workflow_store: WorkflowStore
    checkpoint_store: ACGCheckpointStore
    trace_store: TraceStore
    execution_value_store: ExecutionValueStore
    memory_store: object
    provenance_store: SQLiteProvenanceStore
    decision_store: DecisionStore
    content_manifest_store: ContentManifestStore
    reliable_communication_store: SQLiteReliableCommunicationStore
    capability_catalog: CapabilityCatalog
    agent_registry: AgentRegistry
    resource_plane: ResourcePlane
    resource_binder: ResourceBinder
    scheduler_wait_timeout: float
    resource_execution_adapters: dict[str, ResourceExecutionAdapter]
    tool_runtime: object | None
    model_registry: ModelCompatibilityRegistry
    identity_lifecycle: AcgIdentityLifecyclePort | None
    attachment_context_builder: object | None
    model_runtime: object | None
    default_model_binding: dict[str, str] | None
    fault_hook: Callable[[str], None] | None
    execution_permit_authority: object | None = None


class CollaboratorAccess:
    """按共享上下文读写的协作者属性端口。

    facade 与各服务继承本类并持有同一个 ``ports`` 实例：facade 是唯一的
    组合写入方（测试与应用装配在构造后替换 store 等协作者时经由属性
    setter 落进上下文），服务侧每次读取都取到当前值。
    """

    ports: RuntimeCollaborators

    @property
    def execution_permit_authority(self):
        return self.ports.execution_permit_authority

    @execution_permit_authority.setter
    def execution_permit_authority(self, value):
        self.ports.execution_permit_authority = value

    @property
    def workflow_store(self) -> WorkflowStore:
        return self.ports.workflow_store

    @workflow_store.setter
    def workflow_store(self, value: WorkflowStore) -> None:
        self.ports.workflow_store = value

    @property
    def checkpoint_store(self) -> ACGCheckpointStore:
        return self.ports.checkpoint_store

    @checkpoint_store.setter
    def checkpoint_store(self, value: ACGCheckpointStore) -> None:
        self.ports.checkpoint_store = value

    @property
    def trace_store(self) -> TraceStore:
        return self.ports.trace_store

    @trace_store.setter
    def trace_store(self, value: TraceStore) -> None:
        self.ports.trace_store = value

    @property
    def execution_value_store(self) -> ExecutionValueStore:
        return self.ports.execution_value_store

    @execution_value_store.setter
    def execution_value_store(self, value: ExecutionValueStore) -> None:
        self.ports.execution_value_store = value

    @property
    def memory_store(self) -> object:
        return self.ports.memory_store

    @memory_store.setter
    def memory_store(self, value: object) -> None:
        self.ports.memory_store = value

    @property
    def provenance_store(self) -> SQLiteProvenanceStore:
        return self.ports.provenance_store

    @provenance_store.setter
    def provenance_store(self, value: SQLiteProvenanceStore) -> None:
        self.ports.provenance_store = value

    @property
    def decision_store(self) -> DecisionStore:
        return self.ports.decision_store

    @decision_store.setter
    def decision_store(self, value: DecisionStore) -> None:
        self.ports.decision_store = value

    @property
    def content_manifest_store(self) -> ContentManifestStore:
        return self.ports.content_manifest_store

    @content_manifest_store.setter
    def content_manifest_store(self, value: ContentManifestStore) -> None:
        self.ports.content_manifest_store = value

    @property
    def reliable_communication_store(self) -> SQLiteReliableCommunicationStore:
        return self.ports.reliable_communication_store

    @reliable_communication_store.setter
    def reliable_communication_store(
        self, value: SQLiteReliableCommunicationStore
    ) -> None:
        self.ports.reliable_communication_store = value

    @property
    def capability_catalog(self) -> CapabilityCatalog:
        return self.ports.capability_catalog

    @capability_catalog.setter
    def capability_catalog(self, value: CapabilityCatalog) -> None:
        self.ports.capability_catalog = value

    @property
    def agent_registry(self) -> AgentRegistry:
        return self.ports.agent_registry

    @agent_registry.setter
    def agent_registry(self, value: AgentRegistry) -> None:
        self.ports.agent_registry = value

    @property
    def resource_plane(self) -> ResourcePlane:
        return self.ports.resource_plane

    @resource_plane.setter
    def resource_plane(self, value: ResourcePlane) -> None:
        self.ports.resource_plane = value

    @property
    def resource_binder(self) -> ResourceBinder:
        return self.ports.resource_binder

    @resource_binder.setter
    def resource_binder(self, value: ResourceBinder) -> None:
        self.ports.resource_binder = value

    @property
    def scheduler_wait_timeout(self) -> float:
        return self.ports.scheduler_wait_timeout

    @scheduler_wait_timeout.setter
    def scheduler_wait_timeout(self, value: float) -> None:
        self.ports.scheduler_wait_timeout = value

    @property
    def resource_execution_adapters(
        self,
    ) -> dict[str, ResourceExecutionAdapter]:
        return self.ports.resource_execution_adapters

    @resource_execution_adapters.setter
    def resource_execution_adapters(
        self, value: dict[str, ResourceExecutionAdapter]
    ) -> None:
        self.ports.resource_execution_adapters = value

    @property
    def tool_runtime(self) -> object | None:
        return self.ports.tool_runtime

    @tool_runtime.setter
    def tool_runtime(self, value: object | None) -> None:
        self.ports.tool_runtime = value

    @property
    def model_registry(self) -> ModelCompatibilityRegistry:
        return self.ports.model_registry

    @model_registry.setter
    def model_registry(self, value: ModelCompatibilityRegistry) -> None:
        self.ports.model_registry = value

    @property
    def identity_lifecycle(self) -> AcgIdentityLifecyclePort | None:
        return self.ports.identity_lifecycle

    @identity_lifecycle.setter
    def identity_lifecycle(self, value: AcgIdentityLifecyclePort | None) -> None:
        self.ports.identity_lifecycle = value

    @property
    def attachment_context_builder(self) -> object | None:
        return self.ports.attachment_context_builder

    @attachment_context_builder.setter
    def attachment_context_builder(self, value: object | None) -> None:
        self.ports.attachment_context_builder = value

    @property
    def model_runtime(self) -> object | None:
        return self.ports.model_runtime

    @model_runtime.setter
    def model_runtime(self, value: object | None) -> None:
        self.ports.model_runtime = value

    @property
    def default_model_binding(self) -> dict[str, str] | None:
        return self.ports.default_model_binding

    @default_model_binding.setter
    def default_model_binding(self, value: dict[str, str] | None) -> None:
        self.ports.default_model_binding = value

    @property
    def _fault_hook(self) -> Callable[[str], None] | None:
        return self.ports.fault_hook

    @_fault_hook.setter
    def _fault_hook(self, value: Callable[[str], None] | None) -> None:
        self.ports.fault_hook = value


__all__ = ["CollaboratorAccess", "RuntimeCollaborators"]
