"""Atomic lease coordination adapters."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from threading import RLock
from typing import Any, Protocol

from contracts.resource import ResourceLease

from .models import SchedulerUnavailable


_ACQUIRE_LEASE_LUA = r"""
local expired = redis.call('ZRANGEBYSCORE', KEYS[3], '-inf', ARGV[5])
for _, lease_id in ipairs(expired) do
  redis.call('HDEL', KEYS[4], lease_id)
  redis.call('HDEL', KEYS[2], lease_id)
end
redis.call('ZREMRANGEBYSCORE', KEYS[3], '-inf', ARGV[5])

if redis.call('EXISTS', KEYS[1]) == 1 then
  return 2
end

local active_slots = 0
for _, slots in ipairs(redis.call('HVALS', KEYS[4])) do
  active_slots = active_slots + tonumber(slots)
end
if active_slots + tonumber(ARGV[4]) > tonumber(ARGV[3]) then
  return 0
end

local stored = redis.call('SET', KEYS[1], ARGV[8], 'PX', ARGV[7], 'NX')
if not stored then
  return 2
end
redis.call('HSET', KEYS[2], ARGV[1], ARGV[2])
redis.call('HSET', KEYS[4], ARGV[1], ARGV[4])
redis.call('ZADD', KEYS[3], ARGV[6], ARGV[1])
return 1
"""

_RELEASE_LEASE_LUA = r"""
local slot_key = redis.call('HGET', KEYS[2], ARGV[1])
local existed = redis.call('DEL', KEYS[1])
if not slot_key then
  return existed
end
redis.call('ZREM', slot_key .. ':leases', ARGV[1])
redis.call('HDEL', slot_key .. ':slots', ARGV[1])
redis.call('HDEL', KEYS[2], ARGV[1])
return 1
"""

_ACTIVE_SLOTS_LUA = r"""
local expired = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
for _, lease_id in ipairs(expired) do
  redis.call('HDEL', KEYS[2], lease_id)
  redis.call('HDEL', KEYS[3], lease_id)
end
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
local active_slots = 0
for _, slots in ipairs(redis.call('HVALS', KEYS[2])) do
  active_slots = active_slots + tonumber(slots)
end
return active_slots
"""


_RENEW_LEASE_LUA = r"""
local payload = redis.call('GET', KEYS[1])
if not payload then
  return 0
end
local lease = cjson.decode(payload)
if lease['ownerId'] ~= ARGV[1] then
  return -1
end
if tonumber(lease['version'] or 1) ~= tonumber(ARGV[2]) then
  return -2
end
if tonumber(lease['expiresAtEpochMs'] or 0) <= tonumber(ARGV[3]) then
  return -3
end
local slot_key = redis.call('HGET', KEYS[2], ARGV[7])
if not slot_key then
  return 0
end
lease['version'] = tonumber(ARGV[2]) + 1
lease['expiresAt'] = ARGV[4]
lease['expiresAtEpochMs'] = tonumber(ARGV[5])
redis.call('SET', KEYS[1], cjson.encode(lease), 'PX', ARGV[6], 'XX')
redis.call('ZADD', slot_key .. ':leases', ARGV[5], ARGV[7])
return lease['version']
"""


class LeaseRenewalFailedError(RuntimeError):
    """A lease could not be renewed by its current owner/version."""


@dataclass(frozen=True)
class CapacityView:
    """Separate declared capacity, coordinated occupancy, and remote telemetry."""

    static_capacity: int
    active_leases: int
    remote_available_slots: int | None
    snapshot_state: str

    @property
    def has_local_capacity(self) -> bool:
        return self.static_capacity - self.active_leases > 0


class LeaseCoordinator(Protocol):
    def active_slots(self, resource_id: str, *, now: datetime | None = None) -> int: ...

    def acquire(
        self,
        *,
        lease_id: str,
        resource_id: str,
        capacity: int,
        run_id: str,
        step_id: str,
        attempt_id: str,
        slot_count: int,
        ttl: timedelta,
        now: datetime,
    ) -> ResourceLease | None: ...

    def release(self, lease_id: str) -> bool: ...

    def renew(
        self, *, lease_id: str, owner_id: str, version: int, ttl: timedelta,
        now: datetime | None = None,
    ) -> ResourceLease: ...


class InMemoryLeaseCoordinator:
    """Deterministic test/local coordinator with an atomic slot critical section."""

    def __init__(self) -> None:
        self._leases: dict[str, ResourceLease] = {}
        self._lock = RLock()

    def acquire(
        self,
        *,
        lease_id: str,
        resource_id: str,
        capacity: int,
        run_id: str,
        step_id: str,
        attempt_id: str,
        slot_count: int = 1,
        ttl: timedelta = timedelta(seconds=60),
        now: datetime | None = None,
    ) -> ResourceLease | None:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("lease clock must be timezone-aware")
        if slot_count < 1 or capacity < 1 or ttl <= timedelta(0):
            raise ValueError("capacity, slot_count and ttl must be positive")
        with self._lock:
            self._expire(current)
            existing = self._leases.get(lease_id)
            if existing is not None:
                return existing.model_copy(deep=True)
            slot_key = self._slot_key(resource_id)
            active = sum(
                lease.slot_count
                for lease in self._leases.values()
                if self._slot_key(lease.resource_id) == slot_key and lease.status == "active"
            )
            if active + slot_count > capacity:
                return None
            lease = ResourceLease(
                leaseId=lease_id,
                resourceId=resource_id,
                ownerId=attempt_id,
                runId=run_id,
                stepId=step_id,
                attemptId=attempt_id,
                slotCount=slot_count,
                version=1,
                createdAt=current,
                expiresAt=current + ttl,
            )
            self._leases[lease_id] = lease
            return lease.model_copy(deep=True)

    def release(self, lease_id: str) -> bool:
        with self._lock:
            lease = self._leases.get(lease_id)
            if lease is None or lease.status != "active":
                return False
            self._leases[lease_id] = lease.model_copy(update={"status": "released"})
            return True

    def renew(
        self, *, lease_id: str, owner_id: str, version: int, ttl: timedelta,
        now: datetime | None = None,
    ) -> ResourceLease:
        current = now or datetime.now(timezone.utc)
        if ttl <= timedelta(0):
            raise ValueError("lease ttl must be positive")
        with self._lock:
            self._expire(current)
            lease = self._leases.get(lease_id)
            if lease is None or lease.status == "expired":
                raise LeaseRenewalFailedError("lease expired or not found")
            if lease.status != "active":
                raise LeaseRenewalFailedError(f"lease is not active: {lease.status}")
            if lease.owner_id != owner_id:
                raise LeaseRenewalFailedError("lease owner does not match")
            if lease.version != version:
                raise LeaseRenewalFailedError("lease version does not match")
            renewed = lease.model_copy(update={
                "version": lease.version + 1,
                "expires_at": current + ttl,
            })
            self._leases[lease_id] = renewed
            return renewed.model_copy(deep=True)

    def active_slots(
        self,
        resource_id: str,
        *,
        now: datetime | None = None,
    ) -> int:
        current = now or datetime.now(timezone.utc)
        slot_key = self._slot_key(resource_id)
        with self._lock:
            self._expire(current)
            return sum(
                lease.slot_count
                for lease in self._leases.values()
                if self._slot_key(lease.resource_id) == slot_key and lease.status == "active"
            )

    def _expire(self, now: datetime) -> None:
        for lease_id, lease in tuple(self._leases.items()):
            if lease.status == "active" and lease.expires_at <= now:
                self._leases[lease_id] = lease.model_copy(update={"status": "expired"})

    def _slot_key(self, resource_id: str) -> str:
        return f"resource:{resource_id}"


class RedisLeaseCoordinator:
    """Redis DB coordination using one Lua transaction per allocation.

    The adapter never falls back to process-local state. Expired lease members
    are reclaimed inside the next acquire/inspection transaction, while the
    lease payload itself also has a Redis TTL.
    """

    def __init__(self, client: Any, *, key_prefix: str = "agentos:scheduler") -> None:
        if not key_prefix.strip():
            raise ValueError("Redis lease key prefix cannot be blank")
        self.client = client
        self.key_prefix = key_prefix.rstrip(":")

    def acquire(
        self,
        *,
        lease_id: str,
        resource_id: str,
        capacity: int,
        run_id: str,
        step_id: str,
        attempt_id: str,
        slot_count: int = 1,
        ttl: timedelta = timedelta(seconds=60),
        now: datetime | None = None,
    ) -> ResourceLease | None:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("lease clock must be timezone-aware")
        if slot_count < 1 or capacity < 1 or ttl <= timedelta(0):
            raise ValueError("capacity, slot_count and ttl must be positive")
        ttl_ms = max(1, int(ttl.total_seconds() * 1000))
        lease = ResourceLease(
            leaseId=lease_id,
            resourceId=resource_id,
            ownerId=attempt_id,
            runId=run_id,
            stepId=step_id,
            attemptId=attempt_id,
            slotCount=slot_count,
            version=1,
            createdAt=current,
            expiresAt=current + ttl,
        )
        lease_key = self._lease_key(lease_id)
        slot_key = self._slot_key(resource_id)
        try:
            result = int(
                self.client.eval(
                    _ACQUIRE_LEASE_LUA,
                    4,
                    lease_key,
                    self._index_key,
                    f"{slot_key}:leases",
                    f"{slot_key}:slots",
                    lease_id,
                    slot_key,
                    capacity,
                    slot_count,
                    self._epoch_ms(current),
                    self._epoch_ms(current + ttl),
                    ttl_ms,
                    self._redis_payload(lease),
                )
            )
            if result == 0:
                return None
            if result == 2:
                payload = self.client.get(lease_key)
                if payload is None:
                    raise SchedulerUnavailable("SCHEDULER_UNAVAILABLE: lease identity was lost")
                return self._from_redis_payload(payload)
            return lease
        except SchedulerUnavailable:
            raise
        except Exception as exc:
            raise SchedulerUnavailable("SCHEDULER_UNAVAILABLE: Redis lease allocation failed") from exc

    def release(self, lease_id: str) -> bool:
        try:
            return bool(
                self.client.eval(
                    _RELEASE_LEASE_LUA,
                    2,
                    self._lease_key(lease_id),
                    self._index_key,
                    lease_id,
                    self.key_prefix,
                )
            )
        except Exception as exc:
            raise SchedulerUnavailable("SCHEDULER_UNAVAILABLE: Redis lease release failed") from exc

    def renew(
        self, *, lease_id: str, owner_id: str, version: int, ttl: timedelta,
        now: datetime | None = None,
    ) -> ResourceLease:
        current = now or datetime.now(timezone.utc)
        if ttl <= timedelta(0):
            raise ValueError("lease ttl must be positive")
        ttl_ms = max(1, int(ttl.total_seconds() * 1000))
        try:
            result = int(self.client.eval(
                _RENEW_LEASE_LUA, 2, self._lease_key(lease_id), self._index_key,
                owner_id, version, self._epoch_ms(current), (current + ttl).isoformat(),
                self._epoch_ms(current + ttl), ttl_ms, lease_id,
            ))
        except Exception as exc:
            raise SchedulerUnavailable("SCHEDULER_UNAVAILABLE: Redis lease renewal failed") from exc
        reasons = {0: "lease expired or not found", -1: "lease owner does not match",
                   -2: "lease version does not match", -3: "lease expired"}
        if result <= 0:
            raise LeaseRenewalFailedError(reasons.get(result, "lease renewal rejected"))
        payload = self.client.get(self._lease_key(lease_id))
        if payload is None:
            raise SchedulerUnavailable("SCHEDULER_UNAVAILABLE: renewed lease identity was lost")
        return self._from_redis_payload(payload)

    def active_slots(
        self,
        resource_id: str,
        *,
        now: datetime | None = None,
    ) -> int:
        current = now or datetime.now(timezone.utc)
        slot_key = self._slot_key(resource_id)
        try:
            return int(
                self.client.eval(
                    _ACTIVE_SLOTS_LUA,
                    3,
                    f"{slot_key}:leases",
                    f"{slot_key}:slots",
                    self._index_key,
                    self._epoch_ms(current),
                )
            )
        except Exception as exc:
            raise SchedulerUnavailable("SCHEDULER_UNAVAILABLE: Redis lease inspection failed") from exc

    def close(self) -> None:
        close = getattr(self.client, "close", None)
        if callable(close):
            close()

    @property
    def _index_key(self) -> str:
        return f"{self.key_prefix}:lease-index"

    def _lease_key(self, lease_id: str) -> str:
        return f"{self.key_prefix}:lease:{lease_id}"

    @staticmethod
    def _redis_payload(lease: ResourceLease) -> str:
        payload = lease.model_dump(by_alias=True, mode="json")
        payload["expiresAtEpochMs"] = int(lease.expires_at.timestamp() * 1000)
        import json
        return json.dumps(payload, separators=(",", ":"))

    @staticmethod
    def _from_redis_payload(payload: bytes | str) -> ResourceLease:
        import json
        decoded = json.loads(payload.decode() if isinstance(payload, bytes) else payload)
        decoded.pop("expiresAtEpochMs", None)
        return ResourceLease.model_validate(decoded)

    def _slot_key(self, resource_id: str) -> str:
        return f"{self.key_prefix}:resource:{resource_id}"

    @staticmethod
    def _epoch_ms(value: datetime) -> int:
        return int(value.timestamp() * 1000)


def issue_lease(lease_id: str, resource_id: str, owner_id: str, seconds: int = 60) -> ResourceLease:
    created_at = datetime.now(timezone.utc)
    return ResourceLease(
        leaseId=lease_id,
        resourceId=resource_id,
        ownerId=owner_id,
        createdAt=created_at,
        expiresAt=created_at + timedelta(seconds=max(1, seconds)),
    )


__all__ = ["CapacityView", "InMemoryLeaseCoordinator", "LeaseCoordinator", "LeaseRenewalFailedError", "RedisLeaseCoordinator", "issue_lease"]
