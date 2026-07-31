"""Seeded, auditable variation of otherwise deterministic ACG plans."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import random
from typing import Literal

from agentos.core.planning.capabilities import CapabilityCatalog
from agentos.core.planning.cognitive_router import (
    CapabilityBinding,
    CognitiveRouter,
    CollaborationNetwork,
)
from agentos.core.planning.profile import TaskSemanticProfile


PlanningDiversity = Literal["stable", "balanced", "exploratory"]
PLANNER_ALGORITHM_VERSION = "controlled-stochastic-v1"
_CANDIDATE_COUNTS: dict[PlanningDiversity, int] = {
    "stable": 1,
    "balanced": 4,
    "exploratory": 8,
}


def normalize_planning_diversity(value: str | None) -> PlanningDiversity:
    normalized = str(value or "stable").strip().lower()
    if normalized not in _CANDIDATE_COUNTS:
        raise ValueError(
            "planningDiversity must be one of: stable, balanced, exploratory"
        )
    return normalized  # type: ignore[return-value]


def normalize_planning_seed(value: object | None) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError("planningSeed must be a non-negative integer")
    try:
        seed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("planningSeed must be a non-negative integer") from exc
    if seed < 0 or seed > 2**53 - 1:
        raise ValueError("planningSeed must be between 0 and 9007199254740991")
    return seed


@dataclass(frozen=True)
class PlanningVariant:
    """One deterministic builder input selected from a seeded candidate set."""

    variant_id: str
    network: CollaborationNetwork
    optional_dependencies: tuple[tuple[str, tuple[str, ...]], ...] = ()
    enable_parallel_controls: bool = True
    selection_reasons: tuple[str, ...] = ()

    def optional_for(self, capability_id: str) -> tuple[str, ...]:
        return dict(self.optional_dependencies).get(capability_id, ())

    def canonical_payload(self) -> dict:
        return {
            "bindings": [
                {
                    "capability": binding.capability,
                    "agentName": binding.agent_name,
                }
                for binding in self.network.bindings
            ],
            "optionalDependencies": {
                capability_id: list(dependencies)
                for capability_id, dependencies in self.optional_dependencies
            },
            "enableParallelControls": self.enable_parallel_controls,
        }


@dataclass
class PlanningVariantSet:
    variants: list[PlanningVariant] = field(default_factory=list)
    requested_count: int = 1


class PlanningVariantGenerator:
    """Generate valid-by-construction alternatives without editing graph objects."""

    def __init__(
        self,
        *,
        capability_catalog: CapabilityCatalog,
        cognitive_router: CognitiveRouter,
    ) -> None:
        self.capability_catalog = capability_catalog
        self.cognitive_router = cognitive_router

    def generate(
        self,
        *,
        profile: TaskSemanticProfile,
        domain: str,
        diversity: PlanningDiversity,
        seed: int | None,
    ) -> PlanningVariantSet:
        count = _CANDIDATE_COUNTS[diversity]
        if diversity == "stable":
            return PlanningVariantSet(
                variants=[self._build_variant(profile, domain=domain)],
                requested_count=count,
            )
        if seed is None:
            raise ValueError("planningSeed is required for stochastic planning")

        randomizer = random.Random(seed)
        variants: list[PlanningVariant] = []
        seen: set[str] = set()
        for _ in range(count):
            variant = self._build_variant(
                profile,
                domain=domain,
                randomizer=randomizer,
                diversity=diversity,
            )
            if variant.variant_id in seen:
                continue
            seen.add(variant.variant_id)
            variants.append(variant)
        return PlanningVariantSet(variants=variants, requested_count=count)

    def _build_variant(
        self,
        profile: TaskSemanticProfile,
        *,
        domain: str,
        randomizer: random.Random | None = None,
        diversity: PlanningDiversity = "stable",
    ) -> PlanningVariant:
        bindings: list[CapabilityBinding] = []
        reasons: list[str] = []
        for capability_id in profile.required_capabilities:
            descriptor = self.capability_catalog.get(capability_id)
            candidates = self.cognitive_router.candidates_for(descriptor, domain=domain)
            if not candidates:
                continue
            chosen = candidates[0]
            if randomizer is not None and len(candidates) > 1:
                pool_size = 2 if diversity == "balanced" else len(candidates)
                pool = candidates[:pool_size]
                weights = [max(0.01, candidate.score) for candidate in pool]
                chosen = randomizer.choices(pool, weights=weights, k=1)[0]
                reasons.append(
                    f"{capability_id}: selected {chosen.agent_name} from {len(pool)} scoped bindings"
                )
            bindings.append(chosen)

        selected = set(profile.required_capabilities)
        optional_dependencies: list[tuple[str, tuple[str, ...]]] = []
        inclusion_probability = 1.0
        if diversity == "balanced":
            inclusion_probability = 0.7
        elif diversity == "exploratory":
            inclusion_probability = 0.45
        for capability_id in profile.required_capabilities:
            descriptor = self.capability_catalog.get(capability_id)
            available = [
                dependency
                for dependency in descriptor.optional_dependencies
                if dependency in selected
            ]
            included = tuple(
                dependency
                for dependency in available
                if randomizer is None or randomizer.random() < inclusion_probability
            )
            optional_dependencies.append((capability_id, included))
            if randomizer is not None and available:
                reasons.append(
                    f"{capability_id}: retained {len(included)}/{len(available)} optional dependencies"
                )

        enable_parallel_controls = True
        if randomizer is not None:
            threshold = 0.75 if diversity == "balanced" else 0.5
            enable_parallel_controls = randomizer.random() < threshold
            reasons.append(
                "parallel control nodes enabled"
                if enable_parallel_controls
                else "independent ready nodes left without explicit parallel controls"
            )

        network = CollaborationNetwork(
            bindings=bindings,
            entropy_budget=profile.entropy_budget,
            unresolved_capabilities=[
                capability_id
                for capability_id in profile.required_capabilities
                if capability_id not in {binding.capability for binding in bindings}
            ],
        )
        network.estimated_entropy = (
            max(0, len(network.agent_names) - 1)
            * self.cognitive_router.entropy_per_edge
        )
        payload = {
            "bindings": [
                [binding.capability, binding.agent_name] for binding in bindings
            ],
            "optionalDependencies": optional_dependencies,
            "enableParallelControls": enable_parallel_controls,
        }
        digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()[:16]
        return PlanningVariant(
            variant_id=f"variant_{digest}",
            network=network,
            optional_dependencies=tuple(optional_dependencies),
            enable_parallel_controls=enable_parallel_controls,
            selection_reasons=tuple(reasons),
        )


__all__ = [
    "PLANNER_ALGORITHM_VERSION",
    "PlanningDiversity",
    "PlanningVariant",
    "PlanningVariantGenerator",
    "PlanningVariantSet",
    "normalize_planning_diversity",
    "normalize_planning_seed",
]
