"""Chat endpoint integration with the shared read-only tool runtime."""

import asyncio

from app.api import chat
from app.llm.chat_stream import ChatStreamEvent, ChatStreamEventType
from app.tools.contracts import SourceReference, ToolExecutionRecord, ToolRunResult


class _ChatToolRuntimeStub:
    def __init__(self, enabled=True):
        self.enabled = enabled

    def scoped(self, allowed_tools):
        return _ChatToolRuntimeStub(enabled=bool(list(allowed_tools)))

    async def run(self, text, **kwargs):
        if not self.enabled:
            return ToolRunResult(
                text="answer without tools",
                model="test-model",
                usage={"total_tokens": 4},
            )
        source = SourceReference(
            citationId="src_chat_test",
            title="Chat source",
            url="https://example.test/chat",
            provider="test-fixture",
            retrievedAt="2026-01-01T00:00:00+00:00",
        )
        execution = ToolExecutionRecord(
            callId="call_chat_test",
            toolName="web_search",
            status="completed",
            durationMs=7,
            outputSummary="Found one source.",
            sourceRefs=[source.citation_id],
        )
        return ToolRunResult(
            text="answer with citation",
            model="test-model",
            usage={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
            metadata={"effectiveThinkingMode": "disabled"},
            sources=[source],
            toolExecutions=[execution],
        )


def test_non_stream_chat_returns_sources_and_execution_summary(monkeypatch):
    monkeypatch.setattr(chat, "get_tool_runtime", lambda: _ChatToolRuntimeStub())

    response = asyncio.run(chat.chat_text(chat.ChatRequest(text="latest evidence")))

    assert response.text == "answer with citation"
    assert response.sources[0]["url"] == "https://example.test/chat"
    assert response.metadata["toolsUsed"] == ["web_search"]
    assert response.metadata["toolExecutions"][0]["status"] == "completed"
    assert response.metadata["executionSummary"][0]["durationMs"] == 7


def test_disabled_tool_mode_uses_empty_scope(monkeypatch):
    monkeypatch.setattr(chat, "get_tool_runtime", lambda: _ChatToolRuntimeStub())

    response = asyncio.run(
        chat.chat_text(chat.ChatRequest(text="do not use tools", tool_mode="disabled"))
    )

    assert response.text == "answer without tools"
    assert response.metadata["toolsUsed"] == []
    assert response.sources == []


def test_sse_forwarder_preserves_tool_events():
    async def chunks():
        yield ChatStreamEvent(
            event=ChatStreamEventType.TOOL_START,
            request_id="req_test",
            sequence=1,
            data={"callId": "call_test", "toolName": "web_search"},
        )
        yield ChatStreamEvent(
            event=ChatStreamEventType.TOOL_RESULT,
            request_id="req_test",
            sequence=2,
            data={"callId": "call_test", "toolName": "web_search", "status": "completed"},
        )
        yield ChatStreamEvent(
            event=ChatStreamEventType.DONE,
            request_id="req_test",
            sequence=3,
            data={"status": "completed"},
        )

    class _ConnectedRequest:
        async def is_disconnected(self):
            return False

    async def collect():
        return [
            item
            async for item in chat._stream_sse_events(
                chunks(), _ConnectedRequest(), 0.01, request_id="req_test"
            )
        ]

    events = asyncio.run(collect())

    assert events[0].startswith("event: tool_start")
    assert events[1].startswith("event: tool_result")
    assert events[2].startswith("event: done")
