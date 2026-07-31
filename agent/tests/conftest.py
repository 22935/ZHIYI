import asyncio
import inspect
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest


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


PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENTOS_SRC = PROJECT_ROOT / "agentOS" / "src"
AGENT_APP_ROOT = PROJECT_ROOT / "agent"

# AgentOS creates its global Chroma client while test modules are imported.
# Isolate that client before collection so tests never open the tracked database.
_TEST_CHROMA_DIR = tempfile.TemporaryDirectory(prefix="kinlin-agent-chroma-tests-")
os.environ["AGENT_CHROMA_PATH"] = _TEST_CHROMA_DIR.name
_TEST_WORKFLOW_DIR = tempfile.TemporaryDirectory(
    prefix="kinlin-agent-workflow-tests-", ignore_cleanup_errors=True
)
os.environ["AGENTOS_WORKFLOW_DB_PATH"] = str(
    Path(_TEST_WORKFLOW_DIR.name) / "workflows.sqlite3"
)

for path in (PROJECT_ROOT, AGENT_APP_ROOT, AGENTOS_SRC):
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)


class _ContractReviewTestProvider:
    """Deterministic business fixtures kept outside the application package."""

    provider_name = "test-fixture"
    model = "contract-review-fixture"

    def generate_text(self, prompt, **kwargs):
        return ""

    def generate_json(self, prompt, schema, **kwargs):
        from app.llm.schemas import compact_schema_name

        task = compact_schema_name(schema)
        if task == "parse_contract":
            return {
                "contract_title": "测试合同",
                "parties": [
                    {"name": "甲方", "role": "委托方"},
                    {"name": "乙方", "role": "服务方"},
                ],
                "contract_type": "测试服务合同",
                "key_dates": [],
                "amounts": [],
                "obligations": [],
                "summary": "测试输入中的合同内容。",
                "scope": "测试服务范围",
                "payment_terms": "测试付款安排",
                "acceptance_terms": "测试验收安排",
                "ip_terms": "",
                "dispute_resolution": "",
            }
        if task == "risk_detect":
            return {
                "risks": [{
                    "id": "risk-test-payment",
                    "title": "付款安排需要复核",
                    "level": "high",
                    "clause": "测试付款安排",
                    "reason": "测试输入中的付款触发条件需要进一步核对。",
                    "consequence": "付款条件不清可能导致履约争议。",
                    "suggestion": "结合交付与验收节点复核付款条件。",
                    "evidenceIds": [],
                }]
            }
        if task == "report_generate":
            return {"report_markdown": "# 测试合同审查报告\n\n报告内容来自测试夹具。"}
        native_fields = {
            "task_summary",
            "extracted_information",
            "retrieved_information",
            "requirements",
            "process_steps",
            "resource_plan",
            "architecture",
            "analysis",
            "evidence_analysis",
            "comparison",
            "cost_analysis",
            "risk_analysis",
            "solution_design",
            "verification",
            "deliverable",
        }
        if native_fields.intersection(schema.get("required") or []):
            return _schema_value(schema)
        return {}


class _ReadOnlyToolTestRuntime:
    """Deterministic read-only tool fixture; never reaches a model or the network."""

    def __init__(self, allowed_tools=None):
        self.allowed_tools = set(
            allowed_tools
            or {
                "web_search",
                "web_extract",
                "knowledge_search",
                "codebase_search",
                "current_datetime",
            }
        )

    def scoped(self, allowed_tools):
        return _ReadOnlyToolTestRuntime(self.allowed_tools.intersection(allowed_tools))

    async def run(self, text, **kwargs):
        from app.tools.contracts import SourceReference, ToolExecutionRecord, ToolRunResult

        source = SourceReference(
            citationId="src_test_evidence",
            title="Test evidence fixture",
            url="https://example.test/evidence",
            snippet="Deterministic evidence for isolated tests.",
            provider="test-fixture",
            retrievedAt="2026-01-01T00:00:00+00:00",
        )
        record = ToolExecutionRecord(
            callId="call_test_retrieval",
            toolName="knowledge_search",
            status="completed",
            durationMs=1,
            outputSummary="Found deterministic test evidence.",
            sourceRefs=[source.citation_id],
        )
        return ToolRunResult(
            text="Evidence-backed result from the isolated test fixture.",
            sources=[source],
            toolExecutions=[record],
        )

    async def execute(self, name, arguments, **kwargs):
        from app.tools.contracts import SourceReference, ToolExecutionRecord, ToolRunResult

        if name not in self.allowed_tools:
            raise PermissionError(f"tool is not allowed in this test run: {name}")
        source = SourceReference(
            citationId="src_test_code",
            title="agent/app/security/internal_auth.py:55",
            filename="agent/app/security/internal_auth.py",
            snippet="class InternalServiceAuthMiddleware:",
            provider="test-fixture",
            retrievedAt="2026-01-01T00:00:00+00:00",
        )
        record = ToolExecutionRecord(
            callId="call_test_code",
            toolName=name,
            status="completed",
            durationMs=1,
            outputSummary="Found one deterministic code location.",
            sourceRefs=[source.citation_id],
        )
        payload = {
            "ok": True,
            "tool": name,
            "summary": "Found one deterministic code location.",
            "data": {
                "results": [{
                    "citationId": source.citation_id,
                    "file_path": source.filename,
                    "line": 55,
                    "language": "python",
                    "score": 1.0,
                    "content": source.snippet,
                }]
            },
            "sources": [source.public_dict()],
        }
        return ToolRunResult(
            text=json.dumps(payload),
            sources=[source],
            toolExecutions=[record],
        )


@pytest.fixture(autouse=True)
def _force_mock_llm(monkeypatch):
    """默认让所有测试走 mock LLM，保证稳定、零成本、零网络。

    生产环境通过 .env 的 DEEPSEEK_*/DASHSCOPE_* 自动接通真实模型；
    但测试不应依赖外部 API。显式置 AGENTOS_LLM_PROVIDER=mock 可覆盖
    config.from_env 的供应商回落映射；需要真实 provider 行为的个别
    测试仍可用 set_llm_gateway_for_tests 注入自定义 provider。
    """
    monkeypatch.setenv("AGENTOS_LLM_PROVIDER", "mock")
    from app.llm.gateway import LLMGateway, set_llm_gateway_for_tests
    from agentos.adapters.tool_adapter import (
        clear_tool_runtime_factory,
        register_tool_runtime_factory,
    )

    set_llm_gateway_for_tests(LLMGateway(provider=_ContractReviewTestProvider()))
    register_tool_runtime_factory(_ReadOnlyToolTestRuntime)
    yield
    clear_tool_runtime_factory()
    set_llm_gateway_for_tests(None)


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


def pytest_unconfigure(config):
    chroma_module = sys.modules.get("agentos.adapters.retrieval.chroma_client")
    if chroma_module is not None:
        client = getattr(chroma_module.chroma_legal_client, "client", None)
        close = getattr(client, "close", None)
        if callable(close):
            close()
    _TEST_CHROMA_DIR.cleanup()
    _TEST_WORKFLOW_DIR.cleanup()
