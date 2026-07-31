"""Versioned, domain-neutral deterministic recovery recipes."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agentos.core.recovery.events import RuntimeEventType
from agentos.core.recovery.models import SubgraphInsertionMode


class RecoveryNodeTemplate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    logical_name: str = Field(alias="logicalName")
    name: str
    capability: str
    input_spec: dict[str, Any] = Field(default_factory=dict, alias="inputSpec")
    output_spec: dict[str, Any] = Field(default_factory=dict, alias="outputSpec")
    retry_limit: int = Field(default=0, alias="retryLimit", ge=0)
    timeout: int = Field(default=0, ge=0)
    priority: int = 0


class RecoveryRecipe(BaseModel):
    """A bounded capability-only template for INSERT_BEFORE_TARGET."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    recipe_id: str = Field(alias="recipeId")
    version: str
    trigger_event_types: list[RuntimeEventType] = Field(alias="triggerEventTypes")
    trigger_reason_codes: list[str] = Field(default_factory=list, alias="triggerReasonCodes")
    required_capabilities: list[str] = Field(alias="requiredCapabilities")
    insertion_mode: SubgraphInsertionMode = Field(
        default=SubgraphInsertionMode.INSERT_BEFORE_TARGET,
        alias="insertionMode",
    )
    max_applications_per_run: int = Field(default=1, alias="maxApplicationsPerRun", ge=1)
    node_templates: list[RecoveryNodeTemplate] = Field(alias="nodeTemplates", min_length=1)
    edge_templates: list[dict[str, str]] = Field(default_factory=list, alias="edgeTemplates")
    input_mappings: dict[str, Any] = Field(default_factory=dict, alias="inputMappings")
    output_mappings: dict[str, Any] = Field(default_factory=dict, alias="outputMappings")

    def matches(self, event_type: RuntimeEventType, reason_code: str) -> bool:
        reason_codes = {code.upper() for code in self.trigger_reason_codes}
        return event_type in self.trigger_event_types and (
            "*" in reason_codes or reason_code.upper() in reason_codes
        )


class RecoveryRecipeRegistry:
    """In-memory registry injected into WorkflowRuntime; it contains no domain routing."""

    def __init__(self, recipes: list[RecoveryRecipe] | None = None) -> None:
        self._recipes: dict[str, RecoveryRecipe] = {}
        for recipe in recipes or []:
            self.register(recipe)

    def register(self, recipe: RecoveryRecipe) -> None:
        key = self._key(recipe.recipe_id, recipe.version)
        if key in self._recipes:
            raise ValueError(f"recovery recipe already registered: {key}")
        self._recipes[key] = recipe.model_copy(deep=True)

    def get(self, recipe_id: str, version: str | None = None) -> RecoveryRecipe:
        matches = [
            recipe for recipe in self._recipes.values()
            if recipe.recipe_id == recipe_id and (version is None or recipe.version == version)
        ]
        if not matches:
            raise KeyError(f"recovery recipe not found: {recipe_id}@{version or 'latest'}")
        return sorted(matches, key=lambda item: item.version)[-1].model_copy(deep=True)

    def match(self, event_type: RuntimeEventType, reason_code: str) -> RecoveryRecipe | None:
        matches = [
            recipe for recipe in self._recipes.values()
            if recipe.matches(event_type, reason_code)
        ]
        if not matches:
            return None
        return sorted(matches, key=lambda item: (item.recipe_id, item.version))[0].model_copy(deep=True)

    @classmethod
    def with_defaults(cls) -> "RecoveryRecipeRegistry":
        return cls(
            [
                RecoveryRecipe(
                    recipeId="evidence_retrieval_and_validation.v1",
                    version="1",
                    triggerEventTypes=[RuntimeEventType.EVIDENCE_MISSING],
                    triggerReasonCodes=["EVIDENCE_MISSING"],
                    requiredCapabilities=["evidence_retrieval", "evidence_validation"],
                    nodeTemplates=[
                        RecoveryNodeTemplate(
                            logicalName="evidence_retrieval",
                            name="Evidence retrieval",
                            capability="evidence_retrieval",
                        ),
                        RecoveryNodeTemplate(
                            logicalName="evidence_validation",
                            name="Evidence validation",
                            capability="evidence_validation",
                        ),
                    ],
                ),
                RecoveryRecipe(
                    recipeId="contract_repair.v1",
                    version="1",
                    triggerEventTypes=[
                        RuntimeEventType.INPUT_CONTRACT_VIOLATION,
                        RuntimeEventType.OUTPUT_CONTRACT_VIOLATION,
                    ],
                    triggerReasonCodes=["*"],
                    requiredCapabilities=["contract_adapter"],
                    nodeTemplates=[
                        RecoveryNodeTemplate(
                            logicalName="contract_adapter",
                            name="Contract adapter",
                            capability="contract_adapter",
                        )
                    ],
                ),
            ]
        )

    @staticmethod
    def _key(recipe_id: str, version: str) -> str:
        return f"{recipe_id}@{version}"


__all__ = [
    "RecoveryNodeTemplate",
    "RecoveryRecipe",
    "RecoveryRecipeRegistry",
]
