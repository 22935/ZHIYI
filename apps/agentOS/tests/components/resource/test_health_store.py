from __future__ import annotations

from datetime import datetime, timedelta, timezone

from components.resource.domain.runtime_health import ResourceHealthMonitor
from components.resource.infrastructure.health_store import InMemoryResourceHealthStore, SQLiteResourceHealthStore


NOW = datetime(2026, 9, 4, tzinfo=timezone.utc)


def test_runtime_health_monitor_requires_an_explicit_store_port() -> None:
    monitor = ResourceHealthMonitor(store=InMemoryResourceHealthStore())

    assert monitor.health("edge-01", now=NOW).healthy is False


def test_sqlite_health_store_shares_heartbeat_and_metrics_between_process_monitors(tmp_path) -> None:
    path = tmp_path / "resource-health.sqlite3"
    first_store = SQLiteResourceHealthStore(path)
    second_store = SQLiteResourceHealthStore(path)
    first = ResourceHealthMonitor(
        store=first_store,
        heartbeat_timeout=timedelta(seconds=30),
        alpha=1.0,
    )
    second = ResourceHealthMonitor(
        store=second_store,
        heartbeat_timeout=timedelta(seconds=30),
        alpha=1.0,
    )
    try:
        first.observe("edge-01", success=True, latency_ms=18, observed_at=NOW)

        shared = second.health("edge-01", now=NOW + timedelta(seconds=1))
        stale = second.health("edge-01", now=NOW + timedelta(seconds=31))

        assert shared.healthy is True
        assert shared.reliability == 1.0
        assert shared.latency_ms == 18
        assert shared.last_heartbeat == NOW
        assert stale.healthy is False
        assert stale.reliability == 1.0
    finally:
        first_store.close()
        second_store.close()


def test_sqlite_health_store_persists_forced_health_until_next_heartbeat(tmp_path) -> None:
    path = tmp_path / "resource-health.sqlite3"
    first_store = SQLiteResourceHealthStore(path)
    first = ResourceHealthMonitor(store=first_store)
    first.set_health("edge-01", healthy=False)
    first_store.close()

    second_store = SQLiteResourceHealthStore(path)
    try:
        restored = ResourceHealthMonitor(store=second_store).health("edge-01")
        assert restored.healthy is False
    finally:
        second_store.close()
