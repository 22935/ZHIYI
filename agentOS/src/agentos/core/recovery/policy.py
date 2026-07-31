"""Deterministic runtime event policy decisions."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from agentos.core.recovery.events import RuntimeEvent, RuntimeEventType
from agentos.core.recovery.recipes import RecoveryRecipeRegistry
from agentos.core.runtime_graph import RuntimeGraph


class EventPolicyAction(str, Enum):
    PROPOSE_PATCH = "PROPOSE_PATCH"
    RETRY_EXISTING = "RETRY_EXISTING"
    IGNORE = "IGNORE"
    REQUEST_HUMAN = "REQUEST_HUMAN"
    FAIL = "FAIL"


class EventPolicyDecision(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    action: EventPolicyAction
    recipe_id: str | None = Field(default=None, alias="recipeId")
    recipe_version: str | None = Field(default=None, alias="recipeVersion")
    target_node_id: str = Field(alias="targetNodeId")
    priority: int = 0
    reason: str = ""
    patch_operation: str | None = Field(default=None, alias="patchOperation")


class RuntimeEventPolicy:
    """Select only registered recipes; it cannot modify RuntimeGraph."""

    _PRIORITY = {
        RuntimeEventType.BINDING_UNAVAILABLE: 500,
        RuntimeEventType.INPUT_CONTRACT_VIOLATION: 400,
        RuntimeEventType.OUTPUT_CONTRACT_VIOLATION: 300,
        RuntimeEventType.EVIDENCE_MISSING: 200,
        RuntimeEventType.LOW_CONFIDENCE: 100,
        RuntimeEventType.STEP_EXECUTION_FAILED: 0,
    }

    def __init__(self, recipe_registry: RecoveryRecipeRegistry) -> None:
        self.recipe_registry = recipe_registry

    def decide(self, event: RuntimeEvent, graph: RuntimeGraph) -> EventPolicyDecision:
        target = event.target_node_id
        priority = self._PRIORITY[event.event_type]
        if event.event_type == RuntimeEventType.BINDING_UNAVAILABLE:
            return EventPolicyDecision(
                action=EventPolicyAction.PROPOSE_PATCH,
                patchOperation="RETRY_ALTERNATE_BINDING",
                targetNodeId=target,
                priority=500,
                reason="current execution binding is unavailable",
            )
        if event.event_type == RuntimeEventType.STEP_EXECUTION_FAILED:
            return EventPolicyDecision(
                action=EventPolicyAction.RETRY_EXISTING,
                targetNodeId=target,
                priority=priority,
                reason="ordinary execution failure uses existing retry policy",
            )
        if event.event_type == RuntimeEventType.LOW_CONFIDENCE:
            return EventPolicyDecision(
                action=EventPolicyAction.IGNORE,
                targetNodeId=target,
                priority=priority,
                reason="IGNORED_NO_RECIPE",
            )
        recipe = self.recipe_registry.match(event.event_type, event.reason_code)
        if recipe is None:
            return EventPolicyDecision(
                action=EventPolicyAction.IGNORE,
                targetNodeId=target,
                priority=priority,
                reason="IGNORED_NO_RECIPE",
            )
        scope = graph.recipe_scope(recipe.recipe_id, target)
        if scope in graph.applied_recipe_scopes:
            return EventPolicyDecision(
                action=EventPolicyAction.REQUEST_HUMAN,
                recipeId=recipe.recipe_id,
                recipeVersion=recipe.version,
                targetNodeId=target,
                priority=priority,
                reason="RECIPE_REAPPLICATION_BLOCKED",
            )
        return EventPolicyDecision(
            action=EventPolicyAction.PROPOSE_PATCH,
            recipeId=recipe.recipe_id,
            recipeVersion=recipe.version,
            targetNodeId=target,
            priority=priority,
            reason=f"registered recipe {recipe.recipe_id}@{recipe.version}",
        )


__all__ = ["EventPolicyAction", "EventPolicyDecision", "RuntimeEventPolicy"]
