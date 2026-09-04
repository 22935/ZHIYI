"""Deterministic scheduling for nodes already declared READY by the executor."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from components.resource.service import ResourceService
from contracts.resource import (
    BindingRequirement,
    ExecutionBinding,
    ResourceProfile,
    ResourceSnapshot,
    SchedulingRequest,
)

from .binder import can_bind
from .leases import InMemoryLeaseCoordinator, LeaseCoordinator
from .models import CandidateDecision, FilterReason, ReadyNodeSchedulingResult
from .placement import placement_reasons, placement_score
from .scorer import score_candidate


class SchedulerService:
    """Filter, score, bind and lease a READY node without inspecting its DAG."""

    def __init__(
        self,
        *,
        resource_service: ResourceService | None = None,
        coordinator: LeaseCoordinator | None = None,
        lease_ttl: timedelta = timedelta(seconds=60),
    ) -> None:
        self.resource_service = resource_service
        self.coordinator = coordinator or InMemoryLeaseCoordinator()
        self.lease_ttl = lease_ttl

    def choose(
        self,
        request: SchedulingRequest,
        profiles: list[ResourceProfile],
        snapshots: list[ResourceSnapshot],
    ) -> str | None:
        by_id = {snapshot.resource_id: snapshot for snapshot in snapshots}
        candidates = [
            profile
            for profile in profiles
            if profile.resource_id in by_id and can_bind(request, profile)
        ]
        chosen = max(
            candidates,
            key=lambda item: (
                score_candidate(request, by_id[item.resource_id]),
                _reverse_id(item.resource_id),
            ),
            default=None,
        )
        return chosen.resource_id if chosen else None

    def schedule_ready(
        self,
        *,
        run_id: str,
        step_id: str,
        attempt_id: str,
        requirement: BindingRequirement,
        now: datetime | None = None,
    ) -> ReadyNodeSchedulingResult:
        if self.resource_service is None:
            raise RuntimeError("SCHEDULER_UNAVAILABLE: resource service is not configured")
        current = now or datetime.now(timezone.utc)
        evaluations: list[tuple[ResourceProfile, CandidateDecision]] = []
        for profile in self.resource_service.profiles():
            versioned = self.resource_service.snapshot(profile.resource_id)
            health = self.resource_service.health_monitor.health(profile.resource_id, now=current)
            reasons = placement_reasons(
                profile,
                versioned.snapshot,
                healthy=health.healthy,
                requirement=requirement,
            )
            score, score_factors = placement_score(
                profile,
                versioned.snapshot,
                reliability=health.reliability,
                latency_ms=health.latency_ms,
                requirement=requirement,
            )
            if reasons:
                score = None
            evaluations.append(
                (
                    profile,
                    CandidateDecision(
                        resourceId=profile.resource_id,
                        accepted=not reasons,
                        reasons=reasons,
                        score=score,
                    ),
                )
            )
        ordered = sorted(
            evaluations,
            key=lambda item: (
                item[1].score is None,
                -(item[1].score or 0.0),
                item[0].resource_id,
            ),
        )
        decisions = [item[1] for item in ordered]
        for profile, decision in ordered:
            if not decision.accepted:
                continue
            versioned = self.resource_service.snapshot(profile.resource_id)
            lease_id = f"lease:{run_id}:{step_id}:{attempt_id}:{profile.resource_id}"
            lease = self.coordinator.acquire(
                lease_id=lease_id,
                resource_id=profile.resource_id,
                capacity=profile.capacity,
                run_id=run_id,
                step_id=step_id,
                attempt_id=attempt_id,
                slot_count=1,
                ttl=self.lease_ttl,
                now=current,
            )
            if lease is None:
                continue
            confirmed = self.resource_service.snapshot(profile.resource_id)
            if confirmed.version != versioned.version:
                self.coordinator.release(lease.lease_id)
                continue
            health = self.resource_service.health_monitor.health(
                profile.resource_id, now=current
            )
            binding = ExecutionBinding(
                bindingId=f"binding:{run_id}:{step_id}:{attempt_id}",
                runId=run_id,
                stepId=step_id,
                attemptId=attempt_id,
                resourceId=profile.resource_id,
                resourceType=profile.resource_type,
                snapshotVersion=confirmed.version,
                metadata={
                    "score": decision.score,
                    "deploymentTier": profile.deployment_tier.value,
                    "placementReasons": [
                        f"deploymentTier={profile.deployment_tier.value}",
                        f"resourceType={profile.resource_type.value}",
                        f"latencyMs={confirmed.snapshot.latency_ms}",
                    ],
                    "scoreFactors": placement_score(
                        profile,
                        confirmed.snapshot,
                        reliability=health.reliability,
                        latency_ms=health.latency_ms,
                        requirement=requirement,
                    )[1],
                },
            )
            return ReadyNodeSchedulingResult(
                status="allocated",
                binding=binding,
                lease=lease,
                candidates=decisions,
            )
        return ReadyNodeSchedulingResult(
            status="queued",
            candidates=decisions,
            reason="NO_CAPACITY" if any(item.accepted for item in decisions) else "NO_ELIGIBLE_RESOURCE",
        )

    @staticmethod
    def _filter_reasons(profile, snapshot, healthy: bool, requirement: BindingRequirement):
        reasons: list[FilterReason] = []
        if not profile.enabled:
            reasons.append(FilterReason.DISABLED)
        if not healthy:
            reasons.append(FilterReason.UNHEALTHY)
        if not set(requirement.required_capabilities).issubset(profile.capabilities):
            reasons.append(FilterReason.CAPABILITY_MISMATCH)
        if requirement.domain and profile.domains and requirement.domain not in profile.domains and "general" not in profile.domains:
            reasons.append(FilterReason.DOMAIN_MISMATCH)
        if requirement.resource_types and profile.resource_type not in requirement.resource_types:
            reasons.append(FilterReason.RESOURCE_TYPE_MISMATCH)
        if requirement.allowed_resource_ids and profile.resource_id not in requirement.allowed_resource_ids:
            reasons.append(FilterReason.NOT_ALLOWED)
        if profile.resource_id in requirement.excluded_resource_ids:
            reasons.append(FilterReason.EXCLUDED)
        if requirement.data_zone and profile.data_zone != requirement.data_zone:
            reasons.append(FilterReason.DATA_ZONE_MISMATCH)
        if requirement.owner_scope and profile.owner_scope != requirement.owner_scope:
            reasons.append(FilterReason.OWNER_SCOPE_MISMATCH)
        if snapshot.available_slots < 1:
            reasons.append(FilterReason.NO_CAPACITY)
        if requirement.max_cost is not None and profile.cost_metadata.get("unit", 0.0) > requirement.max_cost:
            reasons.append(FilterReason.COST_EXCEEDED)
        return reasons

    @staticmethod
    def _score(profile, snapshot, reliability, latency_ms, requirement) -> float:
        capacity = snapshot.available_slots / max(profile.capacity, 1)
        latency = 1.0 if latency_ms is None else 1.0 / (1.0 + latency_ms / 1000.0)
        cost = 1.0 / (1.0 + profile.cost_metadata.get("unit", 0.0))
        preferred = requirement.preferences.get("resourceId") == profile.resource_id
        return round(
            0.4 * reliability
            + 0.25 * capacity
            + 0.15 * (1.0 - snapshot.utilization)
            + 0.1 * latency
            + 0.05 * cost
            + (0.05 if preferred else 0.0),
            9,
        )

    def release(self, lease_id: str) -> bool:
        return self.coordinator.release(lease_id)


def _reverse_id(value: str) -> tuple[int, ...]:
    """Make max() use the lexicographically smallest id as the stable tie-break."""
    return tuple(-ord(character) for character in value)


__all__ = ["SchedulerService"]
