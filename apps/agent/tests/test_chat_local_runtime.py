"""Chat to AgentOS Local Runtime boundary tests."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.config import settings
from app.tools.chat_catalog import ChatToolCatalog
from app.tools.local_runtime import LocalRuntimeToolError, LocalRuntimeToolExecutor
from app.tools.runtime import SDK_TOOLS, ToolInvocationContext
from app.tools.permissions import ApprovalDecision, ChatPermissionService
from contracts.local_runtime import (
    LocalRuntimeAuthorizationRef,
    LocalRuntimeExecutionError,
    LocalRuntimeExecutionLimits,
    LocalRuntimeExecutionResult,
)
from components.resource.application.resource_plane import ResourcePlane
from contracts.resource import Placement, RuntimeKind, RuntimeProfile


def test_chat_composition_uses_the_authenticated_users_current_workspace(monkeypatch):
    from app.security import internal_auth
    from app.tools import runtime as tool_runtime
    template = _executor()
    actor = SimpleNamespace(user_id='current-user')
    selected = LocalRuntimeAuthorizationRef(grantId='selected-grant', workspaceId='selected-workspace')

    def resolve_current(current):
        assert current is actor
        return selected

    execution = SimpleNamespace(local_runtime_client=template.client,
        resource_plane=template.resource_plane, local_runtime_resource=SimpleNamespace(
            profile=SimpleNamespace(runtime_id=template.resource_id)),
        local_runtime_health_projector=template.health_projector,
        local_runtime_transport=template.health_transport,
        local_runtime_authorization=template.authorization,
        workspace_authority=SimpleNamespace(resolve_current=resolve_current))
    monkeypatch.setattr(internal_auth, 'current_trusted_user', lambda: actor)
    monkeypatch.setattr(tool_runtime, '_chat_runtime', None)
    catalog = tool_runtime.configure_chat_tool_runtime(execution).catalog
    catalog.permission_service = None
    asyncio.run(catalog.execute('read_file', {'path': 'note.txt'}, call_id='current-workspace'))
    assert template.client.calls[0][1]['authorization'] == selected
    assert catalog._local_runtime_executor.authorization == template.authorization


def test_dynamic_workspace_is_pinned_before_permission_wait():
    first_client, second_client = _Client(), _Client()
    first, second = _executor(client=first_client), _executor(client=second_client)
    second.authorization = LocalRuntimeAuthorizationRef(grantId="grant-2", workspaceId="workspace-2")
    selected = [first]
    approval_scopes = []

    async def approve(**kwargs):
        approval_scopes.append(kwargs["workspace_id"])
        selected[0] = second

    catalog = ChatToolCatalog(local_runtime_executor=first,
        permission_service=SimpleNamespace(authorize=approve),
        workspace_executor_factory=lambda: selected[0], legacy_terminal_enabled=False)

    async def scenario():
        await catalog.execute("read_file", {"path": "note.txt"}, call_id="dynamic-1")
        await catalog.execute("read_file", {"path": "note.txt"}, call_id="dynamic-2")

    asyncio.run(scenario())
    assert approval_scopes == ["workspace-1", "workspace-2"]
    assert first_client.calls[0][1]["authorization"].workspace_id == "workspace-1"
    assert second_client.calls[0][1]["authorization"].workspace_id == "workspace-2"


class _HealthProjector:
    def __init__(self, healthy=True):
        self.healthy = healthy
        self.calls = 0

    async def refresh(self, _transport):
        self.calls += 1
        return self.healthy


_FILE_CAPABILITIES = ("fs.read", "fs.list", "fs.write", "fs.patch")


def _resource_plane(capabilities=_FILE_CAPABILITIES) -> ResourcePlane:
    plane = ResourcePlane()
    plane.ensure_node("node:device:chat", placement=Placement.DEVICE)
    plane.register_runtime(RuntimeProfile(
        runtimeId="runtime-1",
        kind=RuntimeKind.EXECUTION_BACKEND,
        nodeId="node:device:chat",
        placement=Placement.DEVICE,
        capabilities=list(capabilities),
    ))
    plane.heartbeat_runtime("runtime-1")
    return plane


class _Client:
    def __init__(self, result=None):
        self.result = result
        self.calls = []

    async def execute(self, invocation, **kwargs):
        self.calls.append((invocation, kwargs))
        return self.result or LocalRuntimeExecutionResult(
            requestId="request-1",
            invocationId=invocation.invocation_id,
            status="completed",
            output={"path": invocation.input.get("path", "."), "content": "alpha"},
            startedAt=datetime.now(timezone.utc),
            completedAt=datetime.now(timezone.utc),
        )






class _ShellClient:
    def __init__(self):
        self.calls = []
        self.cancel_calls = []

    async def execute(self, invocation, **kwargs):
        self.calls.append((invocation, kwargs))
        return LocalRuntimeExecutionResult(
            requestId="runtime-request-1",
            invocationId=invocation.invocation_id,
            status="accepted",
            output={"executionId": "execution-1", "state": "running"},
            startedAt=datetime.now(timezone.utc),
            completedAt=datetime.now(timezone.utc),
        )

    async def stream_events(self, **_kwargs):
        for event_type, data in (
            ("started", {}),
            ("stdout_delta", {"delta": "hello\n", "bytes": 6}),
            ("stderr_delta", {"delta": "", "bytes": 0}),
            ("completed", {"exitCode": 0}),
        ):
            yield SimpleNamespace(
                event_type=event_type,
                data=data,
            )

    async def cancel(self, **kwargs):
        self.cancel_calls.append(kwargs)
        return "cancelling"


def _executor(*, healthy=True, candidate=True, client=None):
    return LocalRuntimeToolExecutor(
        resource_plane=(_resource_plane() if candidate else ResourcePlane()),
        client=client or _Client(),
        health_projector=_HealthProjector(healthy=healthy),
        health_transport=object(),
        resource_id="runtime-1",
        authorization=LocalRuntimeAuthorizationRef(
            grantId="grant-1", workspaceId="workspace-1"
        ),
        limits=LocalRuntimeExecutionLimits(
            timeoutSeconds=10, maxStdoutBytes=1024, maxStderrBytes=1024
        ),
    )


def test_chat_file_tool_uses_capability_invocation_and_trusted_binding(monkeypatch):
    monkeypatch.setattr(settings, "TOOL_RUNTIME_ENABLED", True)
    client = _Client()
    executor = _executor(client=client)
    catalog = ChatToolCatalog(
        local_runtime_executor=executor,
        legacy_terminal_enabled=False,
    )
    context = ToolInvocationContext(catalog, frozenset({"read_file"}))

    result = asyncio.run(context.invoke(
        "read_file",
        {"path": "docs/hello.txt", "grantId": "model-must-not-bind"},
        call_id="call-1",
    ))

    assert '"ok":true' in result
    invocation, request = client.calls[0]
    assert invocation.invocation_id == "call-1"
    assert invocation.capability_id == "fs.read"
    assert invocation.input == {"path": "docs/hello.txt"}
    assert request["resource_id"] == "runtime-1"
    assert request["authorization"].grant_id == "grant-1"
    assert request["idempotency_key"] == "chat:call-1"
    assert context.records[0].activity["relativePath"] == "docs/hello.txt"
    forbidden = {"grantId", "workspaceId", "resourceId", "endpoint", "credential", "allowedRoot", "allowedPaths"}
    for tool_name in ("read_file", "list_files", "write_file", "patch_file"):
        properties = set(SDK_TOOLS[tool_name].params_json_schema.get("properties", {}))
        assert properties.isdisjoint(forbidden)


def test_same_chat_call_id_reuses_stable_idempotency_key(monkeypatch):
    monkeypatch.setattr(settings, "TOOL_RUNTIME_ENABLED", True)
    client = _Client()
    executor = _executor(client=client)

    asyncio.run(executor.execute("write_file", {"path": "a.txt", "content": "A", "overwrite": False}, call_id="call-1"))
    asyncio.run(executor.execute("write_file", {"path": "a.txt", "content": "A", "overwrite": False}, call_id="call-1"))
    asyncio.run(executor.execute("write_file", {"path": "a.txt", "content": "B", "overwrite": False}, call_id="call-2"))

    assert [item[1]["idempotency_key"] for item in client.calls] == [
        "chat:call-1", "chat:call-1", "chat:call-2"
    ]


def test_unhealthy_or_unselected_resource_fails_closed_without_client_call(monkeypatch):
    monkeypatch.setattr(settings, "TOOL_RUNTIME_ENABLED", True)
    unhealthy_client = _Client()
    with pytest.raises(LocalRuntimeToolError) as unhealthy:
        asyncio.run(_executor(healthy=False, client=unhealthy_client).execute(
            "read_file", {"path": "a.txt"}, call_id="call-1"
        ))
    assert getattr(unhealthy.value, "code") == "LOCAL_RUNTIME_UNAVAILABLE"
    assert unhealthy_client.calls == []

    unavailable_client = _Client()
    with pytest.raises(LocalRuntimeToolError) as unavailable:
        asyncio.run(_executor(candidate=False, client=unavailable_client).execute(
            "read_file", {"path": "a.txt"}, call_id="call-2"
        ))
    assert getattr(unavailable.value, "code") == "LOCAL_RUNTIME_UNAVAILABLE"
    assert unavailable_client.calls == []


def test_runtime_failure_is_recorded_without_legacy_fallback(monkeypatch):
    monkeypatch.setattr(settings, "TOOL_RUNTIME_ENABLED", True)
    failure = LocalRuntimeExecutionResult(
        requestId="request-1",
        invocationId="call-1",
        status="failed",
        error=LocalRuntimeExecutionError(
            code="PATH_OUTSIDE_WORKSPACE",
            retryable=False,
            message="target is outside workspace",
        ),
        startedAt=datetime.now(timezone.utc),
        completedAt=datetime.now(timezone.utc),
    )
    executor = _executor(client=_Client(result=failure))
    catalog = ChatToolCatalog(local_runtime_executor=executor, legacy_terminal_enabled=False)
    context = ToolInvocationContext(catalog, frozenset({"read_file"}))

    result = asyncio.run(context.invoke("read_file", {"path": "../secret.txt"}, call_id="call-1"))

    assert '"ok":false' in result
    assert context.records[0].error_code == "PATH_OUTSIDE_WORKSPACE"
    assert "terminal" not in catalog.TOOL_NAMES
    assert "LOCAL_RUNTIME" not in catalog.availability().get("terminal", {}).get("provider", "")


def test_file_tools_are_unavailable_without_runtime_and_never_fallback(monkeypatch):
    monkeypatch.setattr(settings, "TOOL_RUNTIME_ENABLED", True)
    catalog = ChatToolCatalog(local_runtime_executor=None, legacy_terminal_enabled=False)
    with pytest.raises(LocalRuntimeToolError) as error:
        asyncio.run(catalog.execute("read_file", {"path": "a.txt"}, call_id="call-1"))
    assert getattr(error.value, "code") == "LOCAL_RUNTIME_UNAVAILABLE"
    assert "terminal" not in catalog.TOOL_NAMES


def test_chat_catalog_only_advertises_runtime_granted_file_capabilities(monkeypatch):
    monkeypatch.setattr(settings, "TOOL_RUNTIME_ENABLED", True)
    plane = _resource_plane(("fs.read", "fs.list"))
    executor = LocalRuntimeToolExecutor(
        resource_plane=plane,
        client=_Client(),
        health_projector=_HealthProjector(),
        health_transport=object(),
        resource_id="runtime-1",
        authorization=LocalRuntimeAuthorizationRef(
            grantId="grant-1", workspaceId="workspace-1"
        ),
    )
    catalog = ChatToolCatalog(local_runtime_executor=executor, legacy_terminal_enabled=False)

    assert "read_file" in catalog.TOOL_NAMES
    assert "list_files" in catalog.TOOL_NAMES
    assert "write_file" not in catalog.TOOL_NAMES
    assert "patch_file" not in catalog.TOOL_NAMES
    assert catalog.availability()["write_file"]["available"] is False
    assert catalog.availability()["patch_file"]["available"] is False


def test_run_command_uses_host_approved_local_runtime_and_streams_events(monkeypatch):
    monkeypatch.setattr(settings, "TOOL_RUNTIME_ENABLED", True)
    plane = _resource_plane((*_FILE_CAPABILITIES, "shell.exec"))
    client = _ShellClient()
    executor = LocalRuntimeToolExecutor(
        resource_plane=plane,
        client=client,
        health_projector=_HealthProjector(),
        health_transport=object(),
        resource_id="runtime-1",
        authorization=LocalRuntimeAuthorizationRef(grantId="grant-1", workspaceId="workspace-1"),
        limits=LocalRuntimeExecutionLimits(timeoutSeconds=10, maxStdoutBytes=1024, maxStderrBytes=1024),
    )
    catalog = ChatToolCatalog(local_runtime_executor=executor, legacy_terminal_enabled=False)
    assert "run_command" in catalog.TOOL_NAMES
    assert catalog.availability()["run_command"]["capabilityId"] == "shell.exec"
    schema = set(SDK_TOOLS["run_command"].params_json_schema.get("properties", {}))
    assert schema.isdisjoint({"securityProfile", "grantId", "workspaceId", "resourceId", "allowedRoot"})

    events = []

    async def sink(event_type, payload):
        events.append((event_type, payload))

    result = asyncio.run(executor.execute(
        "run_command",
        {"mode": "shell", "command": "echo hello", "cwd": "."},
        call_id="call-shell",
        request_id="chat-request",
        event_sink=sink,
    ))

    invocation, request = client.calls[0]
    assert invocation.capability_id == "shell.exec"
    assert invocation.input["securityProfile"] == "host_approved"
    assert "grantId" not in invocation.input
    assert request["authorization"].grant_id == "grant-1"
    assert result.data["terminal"]["stdout"] == "hello\n"
    assert [event[0] for event in events] == [
        "execution_started", "stdout_delta", "stderr_delta", "execution_completed"
    ]

    # The model may emit optional fields as null; null timeout must not fail.
    asyncio.run(executor.execute(
        "run_command",
        {"mode": "shell", "command": "echo hello", "cwd": ".", "timeout": None},
        call_id="call-shell-null-timeout",
        request_id="chat-request-null-timeout",
        event_sink=sink,
    ))
    assert "timeout" not in client.calls[1][0].input

    with pytest.raises(LocalRuntimeToolError, match="system-controlled"):
        asyncio.run(executor.execute(
            "run_command",
            {"mode": "shell", "command": "echo blocked", "cwd": ".", "securityProfile": "isolated_workspace"},
            call_id="call-forbidden",
        ))


def test_run_command_permission_is_one_time_and_exposes_no_host_authority(monkeypatch):
    async def scenario():
        monkeypatch.setattr(settings, "TOOL_RUNTIME_ENABLED", True)
        plane = _resource_plane((*_FILE_CAPABILITIES, "shell.exec"))
        executor = LocalRuntimeToolExecutor(
            resource_plane=plane,
            client=_ShellClient(),
            health_projector=_HealthProjector(),
            health_transport=object(),
            resource_id="runtime-1",
            authorization=LocalRuntimeAuthorizationRef(grantId="grant-1", workspaceId="workspace-1"),
        )
        permission = ChatPermissionService()
        catalog = ChatToolCatalog(
            local_runtime_executor=executor,
            legacy_terminal_enabled=False,
            permission_service=permission,
        )
        queue = asyncio.Queue()
        context = ToolInvocationContext(
            catalog,
            frozenset({"run_command"}),
            session_id="chat-session",
            request_id="chat-request",
            permission_event_queue=queue,
        )
        task = asyncio.create_task(context.invoke(
            "run_command",
            {"mode": "shell", "command": "echo approved", "cwd": "."},
            call_id="call-shell",
        ))
        event, payload = await queue.get()
        assert event == "approval_required"
        approval = payload["approval"]
        assert approval["capabilityId"] == "shell.exec"
        assert approval["operation"] == "Run command"
        assert approval["riskNotice"]
        assert "grantId" not in approval and "resourceId" not in approval
        await permission.resolve(
            approval["approvalId"],
            decision=ApprovalDecision.ALLOW_ONCE,
            session_id="chat-session",
            invocation_id="call-shell",
            capability_id="shell.exec",
            relative_path=".",
        )
        await task

    asyncio.run(scenario())
