"""将心跳和执行结果转化为资源健康度。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .algorithms import exponential_moving_average
from .health_store import InMemoryResourceHealthStore, ResourceHealthStore
from .models import ResourceHealth


def _utc(value: datetime) -> datetime:
    """统一时间用于超时比较，拒绝没有时区的歧义输入。"""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


class ResourceHealthMonitor:
    """维护资源运行指标，并在读取时基于心跳年龄计算健康状态。"""

    def __init__(
        self,
        *,
        heartbeat_timeout: timedelta = timedelta(seconds=60),
        alpha: float = 0.2,
        initial_reliability: float = 0.5,
        store: ResourceHealthStore | None = None,
    ) -> None:
        if heartbeat_timeout <= timedelta(0):
            raise ValueError("heartbeat_timeout must be positive")
        if not 0.0 <= initial_reliability <= 1.0:
            raise ValueError("initial_reliability must be in [0, 1]")
        if not 0.0 < alpha <= 1.0:
            raise ValueError("alpha must be in (0, 1]")
        self.heartbeat_timeout = heartbeat_timeout
        self.alpha = alpha
        self.initial_reliability = initial_reliability
        self.store = store or InMemoryResourceHealthStore()

    def heartbeat(self, resource_id: str, *, received_at: datetime | None = None) -> ResourceHealth:
        """记录本地接收心跳的时间，并返回新的健康投影。"""
        timestamp = _utc(received_at) if received_at is not None else datetime.now(timezone.utc)
        state = self.store.get(resource_id)
        self.store.upsert(
            resource_id=resource_id,
            reliability=state.reliability if state else self.initial_reliability,
            latency_ms=state.latency_ms if state else None,
            last_heartbeat=timestamp,
            forced_health=None,
            updated_at=timestamp,
        )
        return self.health(resource_id, now=timestamp)

    def set_health(self, resource_id: str, *, healthy: bool) -> ResourceHealth:
        """Apply an explicit adapter observation without inventing a heartbeat."""
        current = datetime.now(timezone.utc)
        state = self.store.get(resource_id)
        self.store.upsert(
            resource_id=resource_id,
            reliability=state.reliability if state else self.initial_reliability,
            latency_ms=state.latency_ms if state else None,
            last_heartbeat=state.last_heartbeat if state else None,
            forced_health=healthy,
            updated_at=current,
        )
        return self.health(resource_id)

    def observe(
        self,
        resource_id: str,
        *,
        success: bool,
        latency_ms: float,
        observed_at: datetime | None = None,
    ) -> ResourceHealth:
        """根据一次执行结果用 EMA 平滑可靠性和时延，并视为活动信号。"""
        if latency_ms < 0:
            raise ValueError("latency_ms must be non-negative")
        state = self.store.get(resource_id)
        previous_reliability = state.reliability if state else self.initial_reliability
        reliability = exponential_moving_average(
            previous_reliability, 1.0 if success else 0.0, self.alpha
        )
        latency = exponential_moving_average(
            state.latency_ms if state else None, latency_ms, self.alpha
        )
        timestamp = _utc(observed_at) if observed_at is not None else datetime.now(timezone.utc)
        self.store.upsert(
            resource_id=resource_id,
            reliability=reliability,
            latency_ms=latency,
            last_heartbeat=timestamp,
            forced_health=None,
            updated_at=timestamp,
        )
        return self.health(resource_id, now=timestamp)

    def health(self, resource_id: str, *, now: datetime | None = None) -> ResourceHealth:
        """按调用时刻计算健康状态，因此资源会在没有新心跳时自然过期。"""
        current_time = _utc(now) if now is not None else datetime.now(timezone.utc)
        state = self.store.get(resource_id)
        heartbeat = state.last_heartbeat if state else None
        naturally_healthy = heartbeat is not None and current_time - heartbeat <= self.heartbeat_timeout
        healthy = state.forced_health if state and state.forced_health is not None else naturally_healthy
        return ResourceHealth(
            resource_id=resource_id,
            healthy=healthy,
            reliability=state.reliability if state else self.initial_reliability,
            latency_ms=state.latency_ms if state else None,
            last_heartbeat=heartbeat,
        )

    calculate = health


# TODO: 继续补齐跨进程心跳的签名鉴权、重放保护和持久化；当前由 ResourceService
# 接收远程观测并更新本进程监测器，尚不等同于生产级多节点健康中心。
