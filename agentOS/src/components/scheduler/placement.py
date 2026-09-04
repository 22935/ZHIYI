"""端边云资源放置策略的纯计算部分。"""

from __future__ import annotations

from contracts.resource import BindingRequirement, DeploymentTier, ResourceProfile, ResourceSnapshot

from .models import FilterReason


_PRIVACY_RANK = {
    "public": 0,
    "internal": 1,
    "confidential": 2,
    "restricted": 3,
}


def placement_reasons(
    profile: ResourceProfile,
    snapshot: ResourceSnapshot,
    *,
    healthy: bool,
    requirement: BindingRequirement,
) -> list[FilterReason]:
    """按硬约束判断资源是否适合当前步骤，不修改资源状态。"""
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
    if requirement.allowed_deployment_tiers and profile.deployment_tier not in requirement.allowed_deployment_tiers:
        reasons.append(FilterReason.DEPLOYMENT_TIER_MISMATCH)
    if not requirement.allow_remote_execution and profile.deployment_tier is not DeploymentTier.LOCAL:
        reasons.append(FilterReason.REMOTE_EXECUTION_DISABLED)
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
    if requirement.max_latency_ms is not None and (
        snapshot.latency_ms is None or snapshot.latency_ms > requirement.max_latency_ms
    ):
        reasons.append(FilterReason.LATENCY_EXCEEDED)
    if _PRIVACY_RANK.get(profile.privacy_level, -1) < _PRIVACY_RANK.get(requirement.privacy_level, -1):
        reasons.append(FilterReason.PRIVACY_LEVEL_INSUFFICIENT)
    if requirement.required_model_ids and not set(requirement.required_model_ids).issubset(profile.model_ids):
        reasons.append(FilterReason.MODEL_MISMATCH)
    if profile.compute_capacity.gpu_memory_mb < requirement.min_gpu_memory_mb:
        reasons.append(FilterReason.GPU_MEMORY_INSUFFICIENT)
    if profile.deployment_tier is not DeploymentTier.LOCAL and profile.execution_endpoint is None:
        reasons.append(FilterReason.ENDPOINT_MISSING)
    return reasons


def placement_score(
    profile: ResourceProfile,
    snapshot: ResourceSnapshot,
    *,
    reliability: float,
    latency_ms: float | None,
    requirement: BindingRequirement,
) -> tuple[float, dict[str, float]]:
    """计算可解释的软约束分数；硬约束由 ``placement_reasons`` 负责。"""
    capacity = snapshot.available_slots / max(profile.capacity, 1)
    latency = 1.0 if latency_ms is None else 1.0 / (1.0 + latency_ms / 1000.0)
    cost = 1.0 / (1.0 + profile.cost_metadata.get("unit", 0.0))
    preferred = 1.0 if requirement.preferences.get("resourceId") == profile.resource_id else 0.0
    factors = {
        "reliability": reliability,
        "capacity": capacity,
        "idle": 1.0 - snapshot.utilization,
        "latency": latency,
        "cost": cost,
        "preference": preferred,
    }
    score = (
        0.4 * factors["reliability"]
        + 0.25 * factors["capacity"]
        + 0.15 * factors["idle"]
        + 0.1 * factors["latency"]
        + 0.05 * factors["cost"]
        + 0.05 * factors["preference"]
    )
    return round(score, 9), {key: round(value, 9) for key, value in factors.items()}


__all__ = ["placement_reasons", "placement_score"]
