from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from components.resource.service import ResourceService
from components.resource.store import SQLiteResourceStore
from contracts.resource import (
    DeploymentTier,
    ResourceEndpoint,
    ResourceHealthStatus,
    ResourceProfile,
    ResourceSnapshot,
    ResourceType,
)


NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _register_edge() -> ResourceService:
    resources = ResourceService(heartbeat_timeout=timedelta(seconds=30))
    resources.register(
        ResourceProfile(
            resourceId="edge-01",
            resourceType=ResourceType.WORKER,
            deploymentTier=DeploymentTier.EDGE,
            capabilities=["vision.infer"],
            executionEndpoint=ResourceEndpoint(protocol="http", address="http://edge-01:9000"),
        ),
        ResourceSnapshot(
            resourceId="edge-01",
            availableSlots=1,
            utilization=0.0,
            healthStatus=ResourceHealthStatus.UNKNOWN,
        ),
    )
    return resources


def test_remote_heartbeat_is_authoritative_and_expires_without_refresh() -> None:
    resources = _register_edge()

    online = resources.heartbeat("edge-01", received_at=NOW, source="external")
    stale = resources.health_monitor.health("edge-01", now=NOW + timedelta(seconds=31))

    assert online.healthy is True
    assert stale.healthy is False


def test_local_runtime_cannot_refresh_remote_resource() -> None:
    resources = _register_edge()

    with pytest.raises(ValueError, match="external heartbeat"):
        resources.heartbeat("edge-01", received_at=NOW, source="local")


def test_remote_observation_updates_snapshot_and_health_atomically() -> None:
    resources = _register_edge()

    health = resources.observe_remote(
        "edge-01",
        available_slots=3,
        utilization=0.25,
        latency_ms=18,
        observed_at=NOW,
    )
    snapshot = resources.snapshot("edge-01")

    assert health.healthy is True
    assert snapshot.snapshot.available_slots == 3
    assert snapshot.snapshot.utilization == 0.25
    assert snapshot.snapshot.latency_ms == 18
    assert snapshot.snapshot.observation_sequence == 0
    assert snapshot.snapshot.health_status is ResourceHealthStatus.ONLINE


def test_remote_observation_rejects_older_sequence_without_mutating_snapshot() -> None:
    resources = _register_edge()

    resources.observe_remote(
        "edge-01",
        available_slots=3,
        utilization=0.25,
        latency_ms=18,
        observed_at=NOW,
        observation_sequence=2,
    )

    with pytest.raises(ValueError, match="stale observation"):
        resources.observe_remote(
            "edge-01",
            available_slots=0,
            utilization=1.0,
            latency_ms=900,
            observed_at=NOW - timedelta(seconds=1),
            observation_sequence=1,
        )

    snapshot = resources.snapshot("edge-01")
    assert snapshot.snapshot.observation_sequence == 2
    assert snapshot.snapshot.available_slots == 3


def test_sqlite_remote_observation_rejects_older_sequence(tmp_path) -> None:
    store = SQLiteResourceStore(tmp_path / "resources.sqlite3")
    resources = ResourceService(store=store)
    try:
        resources.register(
            ResourceProfile(
                resourceId="edge-sqlite",
                resourceType=ResourceType.WORKER,
                deploymentTier=DeploymentTier.EDGE,
                capabilities=["vision.infer"],
                executionEndpoint=ResourceEndpoint(protocol="http", address="http://edge-sqlite:9000"),
            ),
            ResourceSnapshot(
                resourceId="edge-sqlite",
                availableSlots=1,
                utilization=0.0,
                healthStatus=ResourceHealthStatus.UNKNOWN,
            ),
        )
        resources.observe_remote(
            "edge-sqlite",
            available_slots=1,
            utilization=0.0,
            observation_sequence=2,
            observed_at=NOW,
        )

        with pytest.raises(ValueError, match="stale observation"):
            resources.observe_remote(
                "edge-sqlite",
                available_slots=0,
                utilization=1.0,
                observation_sequence=1,
                observed_at=NOW,
            )

        assert resources.snapshot("edge-sqlite").snapshot.observation_sequence == 2
    finally:
        store.close()
