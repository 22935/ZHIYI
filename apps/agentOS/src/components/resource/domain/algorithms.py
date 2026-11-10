"""资源健康与候选筛选所需的纯计算函数。"""

from __future__ import annotations

from contracts.resource import RuntimeProfile, RuntimeSnapshot

from .models import RuntimeHealth


def exponential_moving_average(previous: float | None, observation: float, alpha: float) -> float:
    """计算 EMA；首次观测直接采用样本，避免虚构历史数据。"""
    if not 0.0 < alpha <= 1.0:
        raise ValueError("alpha must be in (0, 1]")
    if previous is None:
        return observation
    return alpha * observation + (1.0 - alpha) * previous


def ema(previous: float | None, observation: float, alpha: float) -> float:
    """``exponential_moving_average`` 的简短别名，便于策略代码表达。"""
    return exponential_moving_average(previous, observation, alpha)


def health_score(health: RuntimeHealth, utilization: float) -> float:
    """把可靠性、时延和负载压缩为可稳定排序的健康分数。"""
    if not health.healthy:
        return 0.0
    # 未采集时延时不额外扣分，避免因遥测缺失把可用资源直接排到末位。
    latency_penalty = 1.0 if health.latency_ms is None else 1.0 / (1.0 + health.latency_ms / 1000.0)
    return health.reliability * latency_penalty * (1.0 - utilization)


def is_runtime_available(
    profile: RuntimeProfile,
    snapshot: RuntimeSnapshot,
    health: RuntimeHealth,
    required_capabilities: list[str] | tuple[str, ...] | set[str],
    labels: dict[str, str] | None = None,
) -> bool:
    """判定 Runtime 是否能在当前时刻被调度，不在这里产生任何状态变更。"""
    # 将调用方传入的序列标准化为集合，能力检查只关心包含关系而非顺序或重复。
    required = set(required_capabilities)
    labels = labels or {}
    return (
        profile.enabled
        and required.issubset(profile.capabilities)
        and all(profile.labels.get(key) == value for key, value in labels.items())
        and snapshot.available_slots > 0
        and health.healthy
    )


is_available = is_runtime_available

# TODO(scheduling-policy): 此处仅计算健康分数；端到端调度已有成本/地域约束，
# 租户配额和动态计费仍需权威数据源，接入后保持计算函数无存储副作用。
