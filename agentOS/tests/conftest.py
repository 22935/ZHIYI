"""AgentOS Core test fixtures for application-neutral tool runtime injection."""

import asyncio
import inspect
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


AGENTOS_ROOT = Path(__file__).resolve().parents[1]
AGENTOS_SRC = AGENTOS_ROOT / "src"

value = str(AGENTOS_SRC)
if value not in sys.path:
    sys.path.insert(0, value)


from agentos.adapters.tool_adapter import (  # noqa: E402
    clear_tool_runtime_factory,
    register_tool_runtime_factory,
)
from agentos.adapters.model_adapter import StructuredGenerationResult  # noqa: E402


def _schema_value(schema, field_name="value"):
    schema = schema if isinstance(schema, dict) else {}
    value_type = schema.get("type")
    if isinstance(value_type, list):
        value_type = value_type[0] if value_type else None
    if value_type == "object" or "properties" in schema:
        properties = schema.get("properties") or {}
        return {
            name: _schema_value(properties.get(name), name)
            for name in (schema.get("required") or properties.keys())
        }
    if value_type == "array":
        return [_schema_value(schema.get("items") or {}, field_name)]
    if value_type in {"number", "integer"}:
        return 1 if value_type == "integer" else 1.0
    if value_type == "boolean":
        return True
    allowed = schema.get("enum") or []
    return allowed[0] if allowed else f"generated:{field_name}"


class SchemaStructuredRuntime:
    def __init__(self):
        self.calls = []

    def is_available(self):
        return True

    async def generate_json(self, *, prompt, schema, prompt_version, **kwargs):
        self.calls.append({"prompt": prompt, "schema": schema, **kwargs})
        return StructuredGenerationResult(
            data=_schema_value(schema),
            provider="test-provider",
            model="test-model",
            latencyMs=1,
            promptVersion=prompt_version,
        )


class _Source:
    citation_id = "src_agentos_test"

    def public_dict(self):
        return {
            "citationId": self.citation_id,
            "title": "AgentOS test evidence",
            "url": "https://example.test/agentos-evidence",
            "provider": "test-fixture",
            "retrievedAt": "2026-01-01T00:00:00+00:00",
        }


class _Execution:
    tool_name = "knowledge_search"

    def public_dict(self):
        return {
            "callId": "call_agentos_test",
            "toolName": self.tool_name,
            "status": "completed",
            "durationMs": 1,
            "inputSummary": "query",
            "outputSummary": "Found test evidence.",
            "sourceRefs": [_Source.citation_id],
        }


class _ToolRuntime:
    def scoped(self, allowed_tools):
        return self

    async def run(self, text, **kwargs):
        return SimpleNamespace(
            text="Evidence-backed result from the AgentOS test fixture.",
            sources=[_Source()],
            tool_executions=[_Execution()],
        )

    async def execute(self, name, arguments, **kwargs):
        source = _Source()
        return SimpleNamespace(
            text=json.dumps({
                "ok": True,
                "tool": name,
                "data": {
                    "results": [{
                        "citationId": source.citation_id,
                        "snippet": "Evidence-backed result from the AgentOS test fixture.",
                    }]
                },
            }),
            sources=[source],
            tool_executions=[_Execution()],
        )


@pytest.fixture(autouse=True)
def _configured_tool_runtime():
    register_tool_runtime_factory(_ToolRuntime)
    yield
    clear_tool_runtime_factory()


@pytest.fixture
def structured_model_runtime():
    return SchemaStructuredRuntime()


def pytest_pyfunc_call(pyfuncitem):
    """Run async test functions without requiring an extra pytest plugin."""

    test_func = pyfuncitem.obj
    if not inspect.iscoroutinefunction(test_func):
        return None

    kwargs = {
        name: pyfuncitem.funcargs[name]
        for name in pyfuncitem._fixtureinfo.argnames
    }
    asyncio.run(test_func(**kwargs))
    return True
