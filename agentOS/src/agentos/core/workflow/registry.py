"""工作流注册表，负责保存、加载和推荐行业 Pack 提供的工作流定义。"""
# TODO 后期需要拓展为加载动态生成的拓扑图和工作流

import json
from pathlib import Path
from typing import Dict, Iterable, Optional

from agentos.core.models.types import WorkflowDefinition


class WorkflowRegistry:
    """保存并推荐行业 Pack 提供的工作流定义。"""

    """初始化类的设计"""
    def __init__(self):
        self._workflows: Dict[str, WorkflowDefinition] = {}
        self._aliases: Dict[str, str] = {}

    def register(self, workflow: WorkflowDefinition) -> None:
        if not workflow.workflow_id:
            raise ValueError("workflow_id is required")
        if not workflow.steps and not workflow.is_native_bootstrap:
            raise ValueError(f"workflow {workflow.workflow_id} must define at least one step")
        if workflow.workflow_id in self._aliases:
            return
        self._workflows[workflow.workflow_id] = workflow
        for alias in workflow.aliases:
            alias = (alias or "").strip()
            if alias and alias != workflow.workflow_id:
                self._aliases[alias] = workflow.workflow_id

    def get(
        self,
        workflow_id: str,
        *,
        allowed_workflow_ids: Iterable[str] | None = None,
    ) -> WorkflowDefinition:
        canonical_id = self._aliases.get(workflow_id, workflow_id)
        try:
            workflow = self._workflows[canonical_id]
        except KeyError as exc:
            raise KeyError(f"workflow not registered: {workflow_id}") from exc
        if (
            allowed_workflow_ids is not None
            and workflow.workflow_id not in set(allowed_workflow_ids)
        ):
            raise KeyError(
                f"WORKFLOW_NOT_AVAILABLE_IN_PLUGIN_SCOPE: {workflow.workflow_id}"
            )
        return workflow

    def all(self) -> tuple[str, ...]:
        return tuple(self._workflows.values())

    def recommend(
        self,
        domain: str,
        intent: str,
        *,
        allowed_workflow_ids: Iterable[str] | None = None,
    ) -> Optional[WorkflowDefinition]:
        normalized_domain = (domain or "").strip().lower()
        normalized_intent = (intent or "").strip().lower()

        allowed = set(allowed_workflow_ids) if allowed_workflow_ids is not None else None
        exact_matches = [
            workflow
            for workflow in self._workflows.values()
            if (allowed is None or workflow.workflow_id in allowed)
            if workflow.domain.lower() == normalized_domain
            and workflow.intent.lower() == normalized_intent
        ]
        native_bootstrap = next(
            (workflow for workflow in exact_matches if workflow.is_native_bootstrap),
            None,
        )
        if native_bootstrap is not None:
            return native_bootstrap
        if exact_matches:
            return exact_matches[0]

        for workflow in self._workflows.values():
            if allowed is not None and workflow.workflow_id not in allowed:
                continue
            if workflow.domain.lower() == normalized_domain:
                return workflow
        return None

    def scoped(self, workflow_ids: Iterable[str]) -> "ScopedWorkflowRegistry":
        return ScopedWorkflowRegistry(self, tuple(workflow_ids))

    def load_file(self, path: Path) -> WorkflowDefinition:
        text = path.read_text(encoding="utf-8")
        try:
            import yaml  # type: ignore

            data = yaml.safe_load(text)
        except ModuleNotFoundError:
            data = json.loads(text)
        workflow = WorkflowDefinition.model_validate(data)
        self.register(workflow)
        return workflow

    def load_directory(self, directory: Path) -> None:
        if not directory.exists():
            return
        for path in sorted(directory.glob("*.yaml")):
            self.load_file(path)


class ScopedWorkflowRegistry:
    """Read-only per-run view over process-wide Workflow definitions."""

    def __init__(self, registry: WorkflowRegistry, workflow_ids: tuple[str, ...]) -> None:
        self._registry = registry
        self._workflow_ids = frozenset(workflow_ids)

    def get(self, workflow_id: str) -> WorkflowDefinition:
        return self._registry.get(
            workflow_id, allowed_workflow_ids=self._workflow_ids
        )

    def all(self) -> tuple[WorkflowDefinition, ...]:
        return tuple(
            workflow
            for workflow in self._registry.all()
            if workflow.workflow_id in self._workflow_ids
        )

    def recommend(self, domain: str, intent: str) -> Optional[WorkflowDefinition]:
        return self._registry.recommend(
            domain, intent, allowed_workflow_ids=self._workflow_ids
        )
