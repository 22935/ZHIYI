"""Runtime 健康状态持久化端口。"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from ..domain.models import ResourceHealthState


class ResourceHealthStore(Protocol):
    """健康监控读写状态所需的最小抽象。"""

    def get(self, resource_id: str) -> ResourceHealthState | None: ...

    def upsert(
        self,
        *,
        resource_id: str,
        reliability: float,
        latency_ms: float | None,
        last_heartbeat: datetime | None,
        forced_health: bool | None,
        updated_at: datetime,
    ) -> ResourceHealthState: ...
