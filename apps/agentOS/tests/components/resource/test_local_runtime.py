"""Local Runtime 的资源平面注册与健康投影。

Local Runtime 是新模型的第一个真实实例：Device Node 承载一个
EXECUTION_BACKEND Runtime，暴露 filesystem / shell 执行能力；密钥走带外
引导配置，重启后保持稳定。
"""

from datetime import datetime, timezone

import pytest

from components.resource.runtime.local_runtime import (
    DEFAULT_LOCAL_RUNTIME_NODE_ID,
    LOCAL_RUNTIME_RESOURCE_CAPABILITIES,
    LOCAL_RUNTIME_SHELL_CAPABILITY,
    LocalRuntimeHealthProjector,
    LocalRuntimeResourceConfig,
    ensure_local_runtime_resource,
    local_runtime_profile,
)
from components.resource.application.resource_plane import ResourcePlane
from components.resource.infrastructure.runtime_store import SQLiteResourceStore
from cryptography.fernet import Fernet
from contracts.local_runtime import LOCAL_RUNTIME_PROTOCOL_VERSION
from contracts.resource import HealthStatus, Placement, RuntimeKind, TrustLevel


def _config(**overrides) -> LocalRuntimeResourceConfig:
    values = dict(
        resource_id="runtime:local",
        owner_scope="scope-local",
        execution_endpoint="http://127.0.0.1:15100",
    )
    values.update(overrides)
    return LocalRuntimeResourceConfig(**values)


def _health_payload(profile, **overrides) -> dict:
    payload = dict(
        resourceId=profile.runtime_id,
        protocolVersion=LOCAL_RUNTIME_PROTOCOL_VERSION,
        status="online",
        capabilities=list(profile.capabilities),
        availableSlots=profile.capacity,
        utilization=0.0,
    )
    payload.update(overrides)
    return payload


class _StaticTransport:
    def __init__(self, payload) -> None:
        self._payload = payload

    async def health(self) -> dict:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def test_local_runtime_registers_as_execution_backend_on_device_without_shell() -> None:
    profile = local_runtime_profile(_config())
    assert profile.kind is RuntimeKind.EXECUTION_BACKEND
    assert profile.placement is Placement.DEVICE
    assert profile.trust is TrustLevel.HOST_TRUSTED
    assert profile.node_id == DEFAULT_LOCAL_RUNTIME_NODE_ID
    assert LOCAL_RUNTIME_SHELL_CAPABILITY not in profile.capabilities
    assert set(LOCAL_RUNTIME_RESOURCE_CAPABILITIES).issubset(set(profile.capabilities))


def test_local_runtime_can_advertise_only_configured_file_capabilities() -> None:
    profile = local_runtime_profile(
        _config(capabilities=(LOCAL_RUNTIME_RESOURCE_CAPABILITIES[0],))
    )
    assert profile.capabilities == [LOCAL_RUNTIME_RESOURCE_CAPABILITIES[0]]
    with pytest.raises(ValueError):
        _config(capabilities=("shell.exec.magic",))


def test_local_runtime_can_use_out_of_band_bootstrap_credential() -> None:
    plane = ResourcePlane()
    registered = ensure_local_runtime_resource(
        plane, _config(credential_id="rc_bootstrap", credential_secret="bootstrap-secret")
    )
    assert registered.credential is not None
    assert registered.credential.credential_id == "rc_bootstrap"
    assert registered.credential.secret == "bootstrap-secret"
    credential_id, secret = plane.current_signing_credential("runtime:local")
    assert (credential_id, secret) == ("rc_bootstrap", "bootstrap-secret")


def test_shell_profile_is_opt_in_and_health_must_advertise_it() -> None:
    plain = local_runtime_profile(_config())
    with_shell = local_runtime_profile(_config(shell_exec_enabled=True))
    assert LOCAL_RUNTIME_SHELL_CAPABILITY in with_shell.capabilities

    plane = ResourcePlane()
    ensure_local_runtime_resource(plane, _config())
    projector = LocalRuntimeHealthProjector(plane, "runtime:local")
    # Runtime 未声明 shell，而健康载荷宣称提供 shell：身份不一致，判为不可用。
    import asyncio

    ok = asyncio.run(projector.refresh(_StaticTransport(
        _health_payload(plain, capabilities=[*plain.capabilities, LOCAL_RUNTIME_SHELL_CAPABILITY])
    )))
    assert ok is False


def test_local_runtime_registration_is_idempotent_and_credential_survives_restart(tmp_path) -> None:
    db_path = tmp_path / "plane.sqlite3"
    master_key = Fernet.generate_key().decode("ascii")
    plane = ResourcePlane(store=SQLiteResourceStore(db_path), credential_key=master_key)
    first = ensure_local_runtime_resource(plane, _config())
    assert first.credential is not None

    second = ensure_local_runtime_resource(plane, _config())
    assert second.credential is not None
    assert second.credential.credential_id == first.credential.credential_id
    assert second.credential.secret == first.credential.secret
    plane.store.close()

    # 模拟进程重启：新 Plane 实例读同一持久化库，凭据保持稳定。
    restarted = ResourcePlane(store=SQLiteResourceStore(db_path), credential_key=master_key)
    after = ensure_local_runtime_resource(restarted, _config())
    assert after.credential is not None
    assert after.credential.secret == first.credential.secret
    restarted.store.close()


def test_health_projector_updates_observation_and_stale_health_is_unavailable() -> None:
    import asyncio

    plane = ResourcePlane(heartbeat_timeout=__import__("datetime").timedelta(seconds=60))
    registered = ensure_local_runtime_resource(plane, _config())
    projector = LocalRuntimeHealthProjector(plane, "runtime:local")

    ok = asyncio.run(projector.refresh(_StaticTransport(_health_payload(registered.profile))))
    assert ok is True
    versioned = plane.runtime_snapshot("runtime:local")
    assert versioned.snapshot.observation_sequence >= 1
    assert plane.health_monitor.health("runtime:local").healthy

    failed = asyncio.run(projector.refresh(_StaticTransport(RuntimeError("transport down"))))
    assert failed is False
    assert not plane.health_monitor.health("runtime:local").healthy


def test_health_projector_rejects_wrong_identity_and_forces_offline() -> None:
    import asyncio

    plane = ResourcePlane()
    registered = ensure_local_runtime_resource(plane, _config())
    projector = LocalRuntimeHealthProjector(plane, "runtime:local")
    plane.heartbeat_runtime("runtime:local", source="external")

    ok = asyncio.run(projector.refresh(_StaticTransport(
        _health_payload(registered.profile, resourceId="runtime:someone-else")
    )))
    assert ok is False
    assert not plane.health_monitor.health("runtime:local").healthy


def test_ensure_local_runtime_validates_host_consistency() -> None:
    plane = ResourcePlane()
    # 先登记一个 EDGE 节点占用默认 node_id，再注册 DEVICE 运行时应被拒绝。
    from contracts.resource import NodeHealthStatus, NodeProfile, NodeSnapshot

    plane.node_store.register(
        NodeProfile(nodeId=DEFAULT_LOCAL_RUNTIME_NODE_ID, placement=Placement.EDGE),
        NodeSnapshot(
            nodeId=DEFAULT_LOCAL_RUNTIME_NODE_ID,
            healthStatus=NodeHealthStatus.ONLINE,
            lastHeartbeat=datetime.now(timezone.utc),
        ),
    )
    with pytest.raises(ValueError):
        ensure_local_runtime_resource(plane, _config())
