import asyncio
from types import SimpleNamespace

import pytest

from app.api import chat
from app.tools.chat_catalog import ChatToolCatalog
from app.tools.contracts import ToolPayload
from app.tools.permissions import (
    ApprovalDecision,
    ApprovalResolutionError,
    ChatPermissionService,
    PermissionDeniedError,
    PermissionPolicy,
    PermissionScope,
    SessionPermissionStore,
)
from app.tools.runtime import ToolInvocationContext
from app.tools.runtime import AgentsToolRuntime
from app.llm.chat_stream import ChatStreamEventType
import app.tools.runtime as runtime_module


class _Executor:
    def __init__(self):
        self.authorization = SimpleNamespace(workspace_id="workspace-main")
        self.calls = []

    async def execute(self, name, arguments, *, call_id):
        self.calls.append((name, dict(arguments), call_id))
        return ToolPayload(summary=f"executed {name}", data={})


def _catalog(service, executor):
    return ChatToolCatalog(
        local_runtime_executor=executor,
        permission_service=service,
        legacy_terminal_enabled=False,
    )


def test_sdk_timeout_keeps_full_approval_budget_without_mutating_shared_tools():
    from app.tools.runtime import SDK_TOOLS

    service = ChatPermissionService(approval_ttl_seconds=300)
    context = ToolInvocationContext(_catalog(service, _Executor()), frozenset({'write_file'}))
    original = SDK_TOOLS['write_file']
    tool = context.sdk_tools()[0]
    assert tool is not original
    assert tool.timeout_seconds > service.approval_ttl.total_seconds()
    assert tool.timeout_seconds > context.invocation_timeout('write_file')
    assert original.timeout_seconds == 30.0
    # Calls without a Chat permission service retain the original SDK budget.
    plain = ToolInvocationContext(_catalog(None, _Executor()), frozenset({'write_file'}))
    assert plain.sdk_tools()[0] is original


def test_policy_defaults_read_list_and_asks_for_mutations():
    policy = PermissionPolicy()
    grants = SessionPermissionStore()
    assert policy.evaluate(
        PermissionScope(capability_id="fs.read", workspace_id="workspace", relative_path="a.txt"),
        session_id="session",
        session_grants=grants,
    ).value == "allow"
    assert policy.evaluate(
        PermissionScope(capability_id="fs.list", workspace_id="workspace", relative_path="."),
        session_id="session",
        session_grants=grants,
    ).value == "allow"
    assert policy.evaluate(
        PermissionScope(capability_id="fs.write", workspace_id="workspace", relative_path="a.txt"),
        session_id="session",
        session_grants=grants,
    ).value == "ask"
    assert policy.evaluate(
        PermissionScope(capability_id="shell.exec", workspace_id="workspace", relative_path="."),
        session_id="session",
        session_grants=grants,
    ).value == "ask"


def test_ask_suspends_original_call_and_allow_once_preserves_call_id():
    async def scenario():
        service = ChatPermissionService()
        executor = _Executor()
        queue = asyncio.Queue()
        context = ToolInvocationContext(
            _catalog(service, executor),
            frozenset({"write_file"}),
            session_id="session-1",
            permission_event_queue=queue,
        )
        task = asyncio.create_task(
            context.invoke("write_file", {"path": "hello.txt", "content": "A"}, call_id="call-1")
        )
        event, payload = await asyncio.wait_for(queue.get(), timeout=1)
        assert event == "approval_required"
        approval = payload["approval"]
        assert not executor.calls
        assert "workspace-main" not in str(approval)
        assert "allowedRoot" not in str(approval)

        await service.resolve(
            approval["approvalId"],
            decision=ApprovalDecision.ALLOW_ONCE,
            session_id="session-1",
            invocation_id="call-1",
            capability_id="fs.write",
            relative_path="hello.txt",
        )
        resolved_event, resolved_payload = await asyncio.wait_for(queue.get(), timeout=1)
        assert resolved_event == "approval_resolved"
        assert resolved_payload["approval"]["status"] == "approved"
        await task
        assert executor.calls == [("write_file", {"path": "hello.txt", "content": "A"}, "call-1")]

    asyncio.run(scenario())


def test_allow_session_is_ephemeral_and_exactly_scoped():
    async def scenario():
        service = ChatPermissionService()
        executor = _Executor()
        queue = asyncio.Queue()
        catalog = _catalog(service, executor)
        first = ToolInvocationContext(
            catalog,
            frozenset({"write_file"}),
            session_id="session-1",
            permission_event_queue=queue,
        )
        task = asyncio.create_task(
            first.invoke("write_file", {"path": "hello.txt", "content": "A"}, call_id="call-1")
        )
        _, payload = await asyncio.wait_for(queue.get(), timeout=1)
        await service.resolve(
            payload["approval"]["approvalId"],
            decision=ApprovalDecision.ALLOW_SESSION,
            session_id="session-1",
        )
        await asyncio.wait_for(queue.get(), timeout=1)
        await task

        second = ToolInvocationContext(catalog, frozenset({"write_file"}), session_id="session-1")
        await asyncio.wait_for(
            second.invoke("write_file", {"path": "hello.txt", "content": "B"}, call_id="call-2"),
            timeout=1,
        )
        assert len(executor.calls) == 2

        third = ToolInvocationContext(
            catalog,
            frozenset({"write_file"}),
            session_id="session-1",
            permission_event_queue=queue,
        )
        blocked = asyncio.create_task(
            third.invoke("write_file", {"path": "other.txt", "content": "C"}, call_id="call-3")
        )
        _, other_payload = await asyncio.wait_for(queue.get(), timeout=1)
        assert other_payload["approval"]["relativePath"] == "other.txt"
        await service.resolve(
            other_payload["approval"]["approvalId"],
            decision=ApprovalDecision.DENY,
            session_id="session-1",
        )
        await asyncio.wait_for(queue.get(), timeout=1)
        await asyncio.wait_for(blocked, timeout=1)
        assert len(executor.calls) == 2

    asyncio.run(scenario())


def test_wrong_session_or_replayed_approval_is_rejected_before_execution():
    async def scenario():
        service = ChatPermissionService()
        executor = _Executor()
        queue = asyncio.Queue()
        context = ToolInvocationContext(
            _catalog(service, executor),
            frozenset({"write_file"}),
            session_id="owner",
            permission_event_queue=queue,
        )
        task = asyncio.create_task(
            context.invoke("write_file", {"path": "hello.txt", "content": "A"}, call_id="call-1")
        )
        _, payload = await queue.get()
        approval_id = payload["approval"]["approvalId"]
        with pytest.raises(ApprovalResolutionError, match="another session"):
            await service.resolve(approval_id, decision=ApprovalDecision.ALLOW_ONCE, session_id="other")
        assert not executor.calls
        await service.resolve(approval_id, decision=ApprovalDecision.DENY, session_id="owner")
        await queue.get()
        await task
        with pytest.raises(ApprovalResolutionError, match="already"):
            await service.resolve(approval_id, decision=ApprovalDecision.DENY, session_id="owner")

    asyncio.run(scenario())


def test_approval_ttl_expires_fail_closed_without_reaching_executor():
    async def scenario():
        service = ChatPermissionService(approval_ttl_seconds=0.01)
        executor = _Executor()
        queue = asyncio.Queue()
        context = ToolInvocationContext(
            _catalog(service, executor),
            frozenset({"write_file"}),
            session_id="session-expiry",
            permission_event_queue=queue,
        )
        task = asyncio.create_task(
            context.invoke("write_file", {"path": "expired.txt", "content": "A"}, call_id="call-expiry")
        )
        required_event, required_payload = await queue.get()
        assert required_event == "approval_required"
        await asyncio.sleep(0.03)
        resolved_event, resolved_payload = await asyncio.wait_for(queue.get(), timeout=1)
        assert resolved_event == "approval_resolved"
        assert resolved_payload["approval"]["status"] == "expired"
        result = await task
        assert '"error":"APPROVAL_EXPIRED"' in result
        assert not executor.calls
        assert service.pending(required_payload["approval"]["approvalId"]) is None

    asyncio.run(scenario())


def test_invalid_path_is_denied_before_local_runtime_executor():
    async def scenario():
        service = ChatPermissionService()
        executor = _Executor()
        catalog = _catalog(service, executor)
        context = ToolInvocationContext(catalog, frozenset({"write_file"}), session_id="session")
        result = await context.invoke(
            "write_file",
            {"path": "../outside.txt", "content": "must not be written", "allowedRoot": "C:\\"},
            call_id="call-escape",
        )
        assert '"ok":false' in result
        assert context.records[0].error_code == "PERMISSION_SCOPE_INVALID"
        assert not executor.calls

    asyncio.run(scenario())


def test_approval_endpoint_resolves_pending_request_without_grant_authority(monkeypatch):
    async def scenario():
        service = ChatPermissionService()
        events = []

        async def emit(event_type, payload):
            events.append((event_type, payload))

        pending = asyncio.create_task(
            service.authorize(
                tool_name="write_file",
                arguments={"path": "hello.txt", "content": "A"},
                call_id="call-api",
                session_id="session-api",
                workspace_id="workspace-main",
                emit=emit,
            )
        )
        while not events:
            await asyncio.sleep(0)
        approval = events[0][1]["approval"]
        monkeypatch.setattr(chat, "get_chat_permission_service", lambda: service)
        response = await chat.resolve_chat_approval(
            approval["approvalId"],
            chat.ChatApprovalDecisionRequest(
                decision=ApprovalDecision.ALLOW_ONCE,
                sessionId="session-api",
                invocationId="call-api",
                capabilityId="fs.write",
                relativePath="hello.txt",
            ),
        )
        assert response["decision"] == "allow_once"
        await pending
        assert events[-1][0] == "approval_resolved"

    asyncio.run(scenario())


@pytest.mark.parametrize('cancel_pending', [False, True])
def test_runtime_stream_emits_approval_events_while_original_tool_waits(monkeypatch, cancel_pending):
    async def scenario():
        service = ChatPermissionService()
        executor = _Executor()
        catalog = _catalog(service, executor)
        runtime = AgentsToolRuntime(catalog=catalog, allowed_tools={"write_file"})

        class _Client:
            async def close(self):
                return None

        class _Result:
            def __init__(self, context):
                self.context = context
                self.final_output = ""
                self.context_wrapper = SimpleNamespace(usage=SimpleNamespace())

            async def stream_events(self):
                item = SimpleNamespace(
                    call_id="call-stream",
                    raw_item=SimpleNamespace(name="write_file"),
                )
                yield SimpleNamespace(type="run_item_stream_event", name="tool_called", item=item)
                await self.context.invoke(
                    "write_file",
                    {"path": "stream.txt", "content": "A"},
                    call_id="call-stream",
                )
                yield SimpleNamespace(type="run_item_stream_event", name="tool_output", item=item)

        def fake_run_streamed(agent, items, *, context, max_turns, run_config):
            return _Result(context)

        def fake_build_agent_sync(*args, **kwargs):
            return None, _Client(), {"effectiveModel": "test-model"}

        monkeypatch.setattr(runtime, "_build_agent", fake_build_agent_sync)
        monkeypatch.setattr(runtime_module.Runner, "run_streamed", fake_run_streamed)
        monkeypatch.setattr(
            runtime_module,
            "provider_model_capabilities",
            lambda model, base_url: SimpleNamespace(context_window_tokens=1000),
        )

        events = []
        stream = runtime.stream(
            "write stream.txt",
            model="test-model",
            base_url="https://example.test/v1",
            api_key="test-key",
            request_id="request-stream",
            session_id="session-stream",
        )
        tasks_before = asyncio.all_tasks()
        async for event in stream:
            events.append(event)
            if event.event is ChatStreamEventType.APPROVAL_REQUIRED:
                if cancel_pending:
                    await stream.aclose()
                    await asyncio.sleep(0)
                    assert executor.calls == []
                    assert not (asyncio.all_tasks() - tasks_before)
                    return
                approval = event.data["approval"]
                await service.resolve(
                    approval["approvalId"],
                    decision=ApprovalDecision.ALLOW_ONCE,
                    session_id="session-stream",
                    invocation_id="call-stream",
                    capability_id="fs.write",
                    relative_path="stream.txt",
                )

        assert [event.event for event in events] == [
            ChatStreamEventType.TOOL_START,
            ChatStreamEventType.APPROVAL_REQUIRED,
            ChatStreamEventType.APPROVAL_RESOLVED,
            ChatStreamEventType.TOOL_RESULT,
            ChatStreamEventType.USAGE,
            ChatStreamEventType.DONE,
        ]
        assert executor.calls == [("write_file", {"path": "stream.txt", "content": "A"}, "call-stream")]

    asyncio.run(scenario())


@pytest.mark.parametrize("mode,tool,expects_approval", [
    ("ask", "write_file", True), ("auto", "write_file", False),
    ("auto", "run_command", True), ("full", "write_file", False),
    ("full", "run_command", False),
])
def test_request_approval_modes_reach_policy_without_changing_shared_service(mode, tool, expects_approval):
    async def scenario():
        service = ChatPermissionService()
        events = []
        async def emit(event, payload):
            events.append(event)
            if event == "approval_required":
                await service.resolve(payload["approval"]["approvalId"], decision=ApprovalDecision.DENY,
                                      session_id="selected-session")
        kwargs = dict(tool_name=tool, arguments={"path": "hello.txt", "cwd": ".", "command": "pwd"},
                      call_id="call-mode", session_id="selected-session", workspace_id="workspace", emit=emit)
        if expects_approval:
            with pytest.raises(PermissionDeniedError):
                await service.authorize(**kwargs, approval_mode=mode)
        else:
            await service.authorize(**kwargs, approval_mode=mode)
        assert ("approval_required" in events) is expects_approval
        assert service.session_store.grants("selected-session") == ()
        # A parallel request keeps the default ask behavior even after a full request.
        events.clear()
        with pytest.raises(PermissionDeniedError):
            await service.authorize(**kwargs)
        assert "approval_required" in events
    asyncio.run(scenario())


def test_full_approval_mode_keeps_path_validation():
    async def scenario():
        service = ChatPermissionService()
        with pytest.raises(PermissionDeniedError, match="Chat permission denied") as error:
            await service.authorize(tool_name="write_file", arguments={"path": "../outside.txt"},
                                    call_id="invalid", session_id="s", workspace_id="w", approval_mode="full")
        assert error.value.code == "PERMISSION_SCOPE_INVALID"
    asyncio.run(scenario())


def test_runtime_carries_selected_mode_to_file_approval_and_keeps_default_ask():
    async def scenario():
        service = ChatPermissionService()
        executor = _Executor()
        runtime = AgentsToolRuntime(_catalog(service, executor), {"write_file"})
        full = runtime._context(session_id="full-session", approval_mode="full")
        await full.invoke("write_file", {"path": "ok.txt", "content": "A"}, call_id="full-call")
        assert len(executor.calls) == 1
        queue = asyncio.Queue()
        normal = runtime._context(session_id="ask-session", permission_event_queue=queue)
        waiting = asyncio.create_task(normal.invoke("write_file", {"path": "ok.txt", "content": "B"}, call_id="ask-call"))
        event, payload = await asyncio.wait_for(queue.get(), timeout=1)
        assert event == "approval_required"
        assert len(executor.calls) == 1
        await service.resolve(payload["approval"]["approvalId"], decision=ApprovalDecision.DENY, session_id="ask-session")
        await waiting
        assert len(executor.calls) == 1
    asyncio.run(scenario())


def test_chat_request_validates_approval_mode():
    from pydantic import ValidationError
    assert chat.ChatRequest(text="hello").approval_mode == "ask"
    assert chat.ChatRequest(text="hello", approval_mode="full").approval_mode == "full"
    with pytest.raises(ValidationError):
        chat.ChatRequest(text="hello", approval_mode="unknown")
