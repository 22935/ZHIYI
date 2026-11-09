from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from components.scheduler.leases import (
    InMemoryLeaseCoordinator,
    LeaseRenewalFailedError,
    RedisLeaseCoordinator,
)
from components.scheduler.models import SchedulerUnavailable


class _RedisStub:
    def __init__(self, results: list[int], payload: bytes | None = None) -> None:
        self.results = list(results)
        self.payload = payload
        self.calls: list[tuple] = []

    def eval(self, *args):
        self.calls.append(args)
        return self.results.pop(0)

    def get(self, key):
        self.calls.append(("get", key))
        return self.payload


class _BrokenRedis:
    def eval(self, *args):
        raise ConnectionError("redis unavailable")


def _acquire(coordinator: RedisLeaseCoordinator, *, lease_id: str = "lease-1"):
    return coordinator.acquire(
        lease_id=lease_id,
        resource_id="worker-1",
        capacity=2,
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        slot_count=1,
        ttl=timedelta(seconds=30),
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_redis_coordinator_uses_one_atomic_script_for_allocation() -> None:
    client = _RedisStub([1])
    lease = _acquire(RedisLeaseCoordinator(client))

    assert lease is not None
    assert lease.resource_id == "worker-1"
    assert len(client.calls) == 1
    assert client.calls[0][1] == 4
    assert "HVALS" in client.calls[0][0]
    assert "SET" in client.calls[0][0]


def test_redis_coordinator_returns_existing_idempotent_lease() -> None:
    original = _acquire(RedisLeaseCoordinator(_RedisStub([1])))
    assert original is not None
    client = _RedisStub([2], original.model_dump_json(by_alias=True).encode())

    repeated = _acquire(RedisLeaseCoordinator(client))

    assert repeated == original


def test_redis_acquire_script_compares_identity_from_actual_payload_argument() -> None:
    client = _RedisStub([1])
    _acquire(RedisLeaseCoordinator(client))

    script = client.calls[0][0]
    assert "cjson.decode(ARGV[8])" in script
    assert "ARGV[9]" not in script
    assert "existing['attemptId'] ~= requested['attemptId']" in script
    assert "existing['status'] ~= 'active'" in script


def test_redis_coordinator_never_falls_back_when_redis_is_unavailable() -> None:
    with pytest.raises(SchedulerUnavailable, match="SCHEDULER_UNAVAILABLE"):
        _acquire(RedisLeaseCoordinator(_BrokenRedis()))


def test_in_memory_coordinator_renews_only_current_owner_and_version() -> None:
    coordinator = InMemoryLeaseCoordinator()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    lease = coordinator.acquire(
        lease_id="lease-1", resource_id="worker-1", capacity=1,
        run_id="run-1", step_id="step-1", attempt_id="attempt-1",
        slot_count=1, ttl=timedelta(seconds=30), now=now,
    )
    assert lease is not None and lease.version == 1

    renewed = coordinator.renew(
        lease_id=lease.lease_id, owner_id="attempt-1", version=lease.version,
        ttl=timedelta(seconds=30), now=now + timedelta(seconds=10),
    )
    assert renewed.version == 2
    assert renewed.expires_at == now + timedelta(seconds=40)

    with pytest.raises(LeaseRenewalFailedError, match="owner"):
        coordinator.renew(
            lease_id=lease.lease_id, owner_id="attempt-2", version=renewed.version,
            ttl=timedelta(seconds=30), now=now + timedelta(seconds=11),
        )


def test_in_memory_coordinator_refuses_to_renew_an_expired_lease() -> None:
    coordinator = InMemoryLeaseCoordinator()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    lease = coordinator.acquire(
        lease_id="lease-1", resource_id="worker-1", capacity=1,
        run_id="run-1", step_id="step-1", attempt_id="attempt-1",
        slot_count=1, ttl=timedelta(seconds=5), now=now,
    )
    assert lease is not None
    with pytest.raises(LeaseRenewalFailedError, match="expired"):
        coordinator.renew(
            lease_id=lease.lease_id, owner_id="attempt-1", version=lease.version,
            ttl=timedelta(seconds=30), now=now + timedelta(seconds=6),
        )


def test_redis_coordinator_renews_current_owner_and_version() -> None:
    original = _acquire(RedisLeaseCoordinator(_RedisStub([1])))
    assert original is not None
    renewed = original.model_copy(update={
        "version": 2, "expires_at": original.expires_at + timedelta(seconds=30),
    })
    client = _RedisStub([2], RedisLeaseCoordinator._redis_payload(renewed).encode())

    result = RedisLeaseCoordinator(client).renew(
        lease_id=original.lease_id, owner_id="attempt-1", version=1,
        ttl=timedelta(seconds=30), now=original.created_at + timedelta(seconds=1),
    )

    assert result.version == 2
    assert "cjson.decode" in client.calls[0][0]


@pytest.mark.parametrize(
    ("result", "message"),
    [(-1, "owner"), (-2, "version"), (-3, "expired")],
)
def test_redis_coordinator_rejects_invalid_renewal(result: int, message: str) -> None:
    client = _RedisStub([result])
    with pytest.raises(LeaseRenewalFailedError, match=message):
        RedisLeaseCoordinator(client).renew(
            lease_id="lease-1", owner_id="attempt-1", version=1,
            ttl=timedelta(seconds=30), now=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
