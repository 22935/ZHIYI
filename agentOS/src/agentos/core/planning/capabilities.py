"""Domain-neutral planning capability contracts and their validated catalog."""

from __future__ import annotations

from collections import OrderedDict
from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field


PlanningRiskLevel = Literal["normal", "elevated", "high", "critical"]
_RISK_LEVEL_ORDER: tuple[PlanningRiskLevel, ...] = (
    "normal",
    "elevated",
    "high",
    "critical",
)


class PlanningCapabilityDescriptor(BaseModel):
    """Stable planning metadata shared by parsing, routing, and graph building."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    capability_id: str = Field(alias="capabilityId")
    display_name: str = Field(alias="displayName")
    aliases: list[str] = Field(default_factory=list)
    description: str = ""
    planning_stage: str = Field(default="analysis", alias="planningStage")
    depends_on: list[str] = Field(default_factory=list, alias="dependsOn")
    optional_dependencies: list[str] = Field(default_factory=list, alias="optionalDependencies")
    input_contract: dict = Field(default_factory=dict, alias="inputContract")
    output_contract: dict = Field(default_factory=dict, alias="outputContract")
    produces_artifact: bool = Field(default=False, alias="producesArtifact")
    requires_evidence: bool = Field(default=False, alias="requiresEvidence")
    writes_memory: bool = Field(default=False, alias="writesMemory")
    requires_review: bool = Field(default=False, alias="requiresReview")
    risk_level_hint: PlanningRiskLevel = Field(default="normal", alias="riskLevelHint")
    parallelizable: bool = True
    domain_hints: list[str] = Field(default_factory=list, alias="domainHints")
    priority: int = 100
    source: Literal["native", "plugin"] = "native"
    plugin_id: str | None = Field(default=None, alias="pluginId")
    plugin_version: str | None = Field(default=None, alias="pluginVersion")
    contribution_id: str | None = Field(default=None, alias="contributionId")


class CapabilityCatalog:
    """Validated, deterministic registry of executable planning capabilities."""

    def __init__(self, descriptors: Iterable[PlanningCapabilityDescriptor] = ()) -> None:
        self._descriptors: OrderedDict[str, PlanningCapabilityDescriptor] = OrderedDict()
        self._aliases: dict[str, str] = {}
        for descriptor in descriptors:
            self.register(descriptor)

    def register(self, descriptor: PlanningCapabilityDescriptor) -> None:
        capability_id = self._normalize(descriptor.capability_id)
        if not capability_id:
            raise ValueError("capabilityId is required")
        if capability_id in self._descriptors:
            raise ValueError(f"duplicate capabilityId: {descriptor.capability_id}")

        normalized = descriptor.model_copy(
            update={
                "capability_id": capability_id,
                "depends_on": [self._normalize(item) for item in descriptor.depends_on],
                "optional_dependencies": [
                    self._normalize(item) for item in descriptor.optional_dependencies
                ],
                "domain_hints": [self._normalize(item) for item in descriptor.domain_hints],
            }
        )
        alias_values = [capability_id, *normalized.aliases]
        for value in alias_values:
            alias = self._normalize(value)
            existing = self._aliases.get(alias)
            if existing is not None and existing != capability_id:
                raise ValueError(f"duplicate capability alias: {value}")

        self._descriptors[capability_id] = normalized
        for value in alias_values:
            self._aliases[self._normalize(value)] = capability_id

    def get(self, capability_id: str) -> PlanningCapabilityDescriptor:
        normalized = self._normalize(capability_id)
        try:
            return self._descriptors[normalized]
        except KeyError as exc:
            raise KeyError(f"planning capability not registered: {capability_id}") from exc

    def resolve(self, value: str) -> PlanningCapabilityDescriptor:
        normalized = self._normalize(value)
        capability_id = self._aliases.get(normalized)
        if capability_id is None:
            raise KeyError(f"planning capability not registered: {value}")
        return self._descriptors[capability_id]

    def available(self, domain_hint: str | None = None) -> tuple[PlanningCapabilityDescriptor, ...]:
        domain = self._normalize(domain_hint or "")
        descriptors = [
            descriptor
            for descriptor in self._descriptors.values()
            if not domain
            or not descriptor.domain_hints
            or domain in descriptor.domain_hints
        ]
        return tuple(sorted(descriptors, key=lambda item: (item.priority, item.capability_id)))

    def scoped(self, capability_ids: Iterable[str]) -> "CapabilityCatalog":
        """Build an isolated catalog view without mutating the global catalog."""

        allowed = {self._normalize(item) for item in capability_ids}
        scoped = CapabilityCatalog(
            descriptor.model_copy(deep=True)
            for capability_id, descriptor in self._descriptors.items()
            if capability_id in allowed
        )
        scoped.validate()
        return scoped

    def validate(self) -> None:
        for descriptor in self._descriptors.values():
            for dependency in [*descriptor.depends_on, *descriptor.optional_dependencies]:
                if dependency not in self._descriptors:
                    raise ValueError(
                        f"capability {descriptor.capability_id} has dangling dependency: {dependency}"
                    )

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(capability_id: str) -> None:
            if capability_id in visiting:
                raise ValueError(f"capability dependency cycle detected at: {capability_id}")
            if capability_id in visited:
                return
            visiting.add(capability_id)
            descriptor = self._descriptors[capability_id]
            for dependency in [*descriptor.depends_on, *descriptor.optional_dependencies]:
                visit(dependency)
            visiting.remove(capability_id)
            visited.add(capability_id)

        for capability_id in self._descriptors:
            visit(capability_id)

    def expand_dependencies(self, capability_ids: Iterable[str]) -> list[str]:
        selected: list[str] = []
        visited: set[str] = set()

        def include(value: str) -> None:
            descriptor = self.resolve(value)
            if descriptor.capability_id in visited:
                return
            for dependency in descriptor.depends_on:
                include(dependency)
            visited.add(descriptor.capability_id)
            selected.append(descriptor.capability_id)

        for capability_id in capability_ids:
            include(capability_id)
        return selected

    @staticmethod
    def _normalize(value: str) -> str:
        return (value or "").strip().lower()


def highest_planning_risk_level(values: Iterable[str]) -> PlanningRiskLevel:
    """Return the highest recognized declarative planning risk level."""

    ranks = {value: index for index, value in enumerate(_RISK_LEVEL_ORDER)}
    normalized = [str(value or "").strip().lower() for value in values]
    return max(
        (value for value in normalized if value in ranks),
        key=ranks.__getitem__,
        default="normal",
    )


__all__ = [
    "CapabilityCatalog",
    "PlanningCapabilityDescriptor",
    "PlanningRiskLevel",
    "highest_planning_risk_level",
]
