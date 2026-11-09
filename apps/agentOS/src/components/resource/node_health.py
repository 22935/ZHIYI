"""节点心跳分级：把心跳年龄与负载投影为分级健康状态。

Node 健康描述部署实体是否可联通及其粗粒度负载，不等同于 Runtime 的执行
健康。两者分别维护，调度层可以据此区分节点离线和单个运行时不可用。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import RLock

from contracts.resource import NodeHealthStatus

from .models import NodeHealth


def _utc(value: datetime) -> datetime:
    """将节点观测时间标准化为 UTC，并拒绝无法可靠比较的无时区值。"""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def infer_load_status(
    queued_tasks: int, utilization: float, *, overloaded_tasks: int = 10
) -> NodeHealthStatus:
    """根据排队任务数与负载推断在线 / 忙碌 / 过载。"""
    # 阈值优先判定过载，避免高利用率节点被错误归类为普通忙碌。
    if utilization >= 0.9 or queued_tasks >= overloaded_tasks:
        return NodeHealthStatus.OVERLOADED
    if utilization >= 0.7 or queued_tasks > 0:
        return NodeHealthStatus.BUSY
    return NodeHealthStatus.ONLINE


class NodeHealthMonitor:
    """维护节点心跳年龄，读取时计算分级健康，并支持扫地清理。"""

    def __init__(
        self,
        *,
        heartbeat_interval: timedelta = timedelta(seconds=5),
        stale_multiple: int = 3,
        offline_multiple: int = 6,
    ) -> None:
        if heartbeat_interval <= timedelta(0):
            raise ValueError("heartbeat_interval must be positive")
        if not 0 < stale_multiple < offline_multiple:
            raise ValueError("stale_multiple must be positive and below offline_multiple")
        self.heartbeat_interval = heartbeat_interval
        self.stale_threshold = heartbeat_interval * stale_multiple
        self.offline_threshold = heartbeat_interval * offline_multiple
        self._last_heartbeat: dict[str, datetime] = {}
        self._load_status: dict[str, NodeHealthStatus] = {}
        self._consecutive_failures: dict[str, int] = {}
        self._lock = RLock()

    def report(
        self,
        node_id: str,
        *,
        observed_at: datetime | None = None,
        queued_tasks: int = 0,
        utilization: float = 0.0,
        success: bool = True,
        status: NodeHealthStatus | None = None,
    ) -> NodeHealth:
        """记录一次心跳，返回新的分级健康投影。"""
        timestamp = _utc(observed_at) if observed_at is not None else datetime.now(timezone.utc)
        with self._lock:
            failures = 0 if success else self._consecutive_failures.get(node_id, 0) + 1
            self._consecutive_failures[node_id] = failures
            self._last_heartbeat[node_id] = timestamp
            self._load_status[node_id] = status or infer_load_status(queued_tasks, utilization)
        return NodeHealth(
            node_id=node_id,
            status=self._load_status[node_id],
            last_heartbeat=timestamp,
            consecutive_failures=failures,
        )

    def hydrate(
        self,
        node_id: str,
        *,
        last_heartbeat: datetime | None,
        status: NodeHealthStatus = NodeHealthStatus.UNKNOWN,
        consecutive_failures: int = 0,
    ) -> None:
        """进程启动时从持久化节点快照重建本地缓存。"""
        if last_heartbeat is None:
            return
        with self._lock:
            self._last_heartbeat[node_id] = _utc(last_heartbeat)
            self._load_status[node_id] = status
            self._consecutive_failures[node_id] = consecutive_failures

    def health(self, node_id: str, *, now: datetime | None = None) -> NodeHealth:
        """按调用时刻计算分级健康；心跳过期自然降级为 stale/offline。"""
        current = _utc(now) if now is not None else datetime.now(timezone.utc)
        with self._lock:
            heartbeat = self._last_heartbeat.get(node_id)
            failures = self._consecutive_failures.get(node_id, 0)
            load_status = self._load_status.get(node_id, NodeHealthStatus.UNKNOWN)
        if heartbeat is None:
            status = NodeHealthStatus.UNKNOWN
        elif current - heartbeat > self.offline_threshold:
            status = NodeHealthStatus.OFFLINE
        elif current - heartbeat > self.stale_threshold:
            status = NodeHealthStatus.STALE
        else:
            status = load_status
        return NodeHealth(
            node_id=node_id,
            status=status,
            last_heartbeat=heartbeat,
            consecutive_failures=failures,
        )

    def sweep(self, *, now: datetime | None = None) -> list[tuple[str, NodeHealthStatus]]:
        """扫描所有节点，返回心跳超时导致的降级事件，供广播下线/陈旧。"""
        current = _utc(now) if now is not None else datetime.now(timezone.utc)
        events: list[tuple[str, NodeHealthStatus]] = []
        with self._lock:
            for node_id, heartbeat in list(self._last_heartbeat.items()):
                age = current - heartbeat
                if age > self.offline_threshold:
                    events.append((node_id, NodeHealthStatus.OFFLINE))
                elif age > self.stale_threshold:
                    events.append((node_id, NodeHealthStatus.STALE))
        return events


# TODO(node-health-policy): 根据真实负载分布配置阈值，并引入连续超时的退避/恢复窗口。
