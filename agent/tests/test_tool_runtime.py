"""Read-only tool catalog and runtime policy tests."""

import asyncio
import json

import pytest

from app.config import settings
from app.tools.catalog import ReadOnlyToolCatalog
from app.tools.contracts import SourceReference, ToolPayload, ToolUnavailableError
from app.tools.runtime import AgentsToolRuntime, ToolInvocationContext, _tool_call_id


class _FakeTavily:
    async def search(self, **kwargs):
        return {
            "results": [
                {
                    "title": "Official result",
                    "url": "https://example.com/reference",
                    "content": "A current public result.",
                    "score": 0.9,
                },
                {
                    "title": "Blocked local result",
                    "url": "http://127.0.0.1/private",
                    "content": "must not be exposed",
                    "score": 1.0,
                },
            ]
        }

    async def extract(self, **kwargs):
        return {
            "results": [{
                "title": "Extracted page",
                "url": kwargs["urls"][0],
                "raw_content": "External page body " * 100,
            }]
        }


class _CatalogStub:
    async def execute(self, name, arguments, *, role_id=None):
        if arguments.get("sleep"):
            await asyncio.sleep(0.1)
        source = SourceReference(
            citationId="src_stub",
            title="Stub source",
            url="https://example.com/stub",
            provider="stub",
            retrievedAt="2026-01-01T00:00:00+00:00",
        )
        return ToolPayload(summary="stub completed", data={"name": name}, sources=[source])


def test_tavily_search_normalizes_sources_and_skips_local_urls(monkeypatch):
    monkeypatch.setattr(settings, "TOOL_RUNTIME_ENABLED", True)
    monkeypatch.setattr(settings, "TAVILY_API_KEY", "test-key")
    catalog = ReadOnlyToolCatalog()
    catalog._tavily = _FakeTavily()

    payload = asyncio.run(catalog.execute("web_search", {"query": "current law"}))

    assert len(payload.sources) == 1
    assert payload.sources[0].url == "https://example.com/reference"
    assert payload.sources[0].provider == "tavily"
    assert payload.data["results"][0]["citationId"] == payload.sources[0].citation_id


def test_web_extract_rejects_private_url_before_provider_call(monkeypatch):
    monkeypatch.setattr(settings, "TOOL_RUNTIME_ENABLED", True)
    monkeypatch.setattr(settings, "TAVILY_API_KEY", "test-key")
    catalog = ReadOnlyToolCatalog()
    catalog._tavily = _FakeTavily()

    with pytest.raises(ValueError, match="private|non-global"):
        asyncio.run(catalog.execute("web_extract", {"urls": ["http://10.0.0.1/a"]}))


def test_missing_tavily_key_marks_web_tools_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "TOOL_RUNTIME_ENABLED", True)
    monkeypatch.setattr(settings, "TAVILY_API_KEY", "")
    catalog = ReadOnlyToolCatalog()

    assert catalog.availability()["web_search"]["available"] is False
    with pytest.raises(ToolUnavailableError):
        asyncio.run(catalog.execute("web_search", {"query": "latest news"}))


def test_missing_optional_provider_returns_tool_error_without_removing_schema(monkeypatch):
    monkeypatch.setattr(settings, "TOOL_RUNTIME_ENABLED", True)
    monkeypatch.setattr(settings, "TAVILY_API_KEY", "")
    runtime = AgentsToolRuntime(
        ReadOnlyToolCatalog(), {"web_search", "current_datetime"}
    )
    context = runtime._context()

    result = json.loads(asyncio.run(context.invoke("web_search", {"query": "latest news"})))
    agent, client, _ = runtime._build_agent(
        context,
        model="deepseek-chat",
        base_url="https://example.com/v1",
        api_key="test-key",
        require_evidence=False,
        thinking_mode="disabled",
    )
    asyncio.run(client.close())

    assert result == {"ok": False, "tool": "web_search", "error": "TOOL_UNAVAILABLE"}
    assert context.records[0].status == "failed"
    assert {tool.name for tool in agent.tools} == {"current_datetime", "web_search"}


def test_tool_output_uses_sdk_normalized_call_id_when_raw_payload_has_none():
    item = type("OutputItem", (), {"call_id": "call_normalized", "raw_item": {}})()

    assert _tool_call_id(item) == "call_normalized"


def test_tool_context_enforces_allowlist_and_call_limit():
    context = ToolInvocationContext(
        catalog=_CatalogStub(),
        allowed_tools=frozenset({"current_datetime"}),
        max_calls=1,
    )

    first = json.loads(asyncio.run(context.invoke("current_datetime", {})))
    second = json.loads(asyncio.run(context.invoke("current_datetime", {})))

    assert first["ok"] is True
    assert second == {
        "ok": False,
        "tool": "current_datetime",
        "error": "TOOL_CALL_LIMIT_EXCEEDED",
    }
    assert [item.status for item in context.records] == ["completed", "failed"]

    denied = ToolInvocationContext(
        catalog=_CatalogStub(),
        allowed_tools=frozenset({"knowledge_search"}),
    )
    result = json.loads(asyncio.run(denied.invoke("codebase_search", {})))
    assert result["ok"] is False
    assert result["error"] == "PERMISSIONERROR"


def test_tool_context_reports_timeout(monkeypatch):
    monkeypatch.setattr(settings, "TOOL_TIMEOUT_SECONDS", 0.01)
    context = ToolInvocationContext(
        catalog=_CatalogStub(),
        allowed_tools=frozenset({"current_datetime"}),
    )

    result = json.loads(
        asyncio.run(context.invoke("current_datetime", {"sleep": True}))
    )

    assert result["ok"] is False
    assert result["error"] == "TOOL_TIMEOUT"
    assert context.records[0].error_code == "TOOL_TIMEOUT"


def test_scoped_runtime_cannot_expand_parent_allowlist():
    catalog = ReadOnlyToolCatalog()
    runtime = AgentsToolRuntime(catalog, {"knowledge_search", "current_datetime"})

    scoped = runtime.scoped({"current_datetime", "web_search"})

    assert scoped.allowed_tools == frozenset({"current_datetime"})
