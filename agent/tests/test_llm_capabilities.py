import sys
from types import SimpleNamespace

from app.llm.capabilities import (
    adapt_chat_completion_parameters,
    normalize_model_request,
    normalize_thinking_mode,
    provider_model_capabilities,
)
from app.llm.contracts import (
    LLMInvocationResult,
    LLMUsage,
    ModelInvocationAudit,
    ProviderRawResult,
    ThinkingMode,
)
from app.llm.config import LLMConfig
from app.llm.providers.openai_compatible_provider import OpenAICompatibleProvider
from app.ai_engine.deepseekadapter import DeepSeekAdapter


def test_legacy_thinking_values_map_to_three_internal_modes():
    assert normalize_thinking_mode("off") == ThinkingMode.DISABLED
    assert normalize_thinking_mode("low") == ThinkingMode.STANDARD
    assert normalize_thinking_mode("medium") == ThinkingMode.STANDARD
    assert normalize_thinking_mode("high") == ThinkingMode.DEEP
    assert normalize_thinking_mode("max") == ThinkingMode.DEEP


def test_deepseek_legacy_models_migrate_with_compatible_defaults():
    chat = normalize_model_request("deepseek-chat")
    assert chat.effective_model == "deepseek-v4-flash"
    assert chat.effective_thinking_mode == ThinkingMode.DISABLED

    reasoner = normalize_model_request("deepseek-reasoner")
    assert reasoner.effective_model == "deepseek-v4-flash"
    assert reasoner.effective_thinking_mode == ThinkingMode.STANDARD


def test_deepseek_capabilities_include_tool_call_protocol_requirements():
    capabilities = provider_model_capabilities(
        "deepseek-v4-pro", "https://api.deepseek.com/v1"
    )
    assert capabilities.supports_thinking is True
    assert capabilities.supports_reasoning_effort is True
    assert capabilities.supports_tool_choice_in_thinking is False
    assert capabilities.requires_reasoning_content_for_tool_calls is True
    assert capabilities.requires_non_null_assistant_content_for_tool_calls is True
    assert capabilities.supports_json_object is True
    assert capabilities.supports_json_schema is False


def test_deepseek_thinking_request_removes_unsupported_parameters():
    adapted = adapt_chat_completion_parameters(
        model="deepseek-v4-pro",
        base_url="https://api.deepseek.com/v1",
        thinking_mode=ThinkingMode.DEEP,
        parameters={
            "temperature": 0.2,
            "top_p": 0.8,
            "presence_penalty": 0.1,
            "frequency_penalty": 0.1,
            "tool_choice": "auto",
        },
    )
    assert adapted.effective_reasoning_effort == "max"
    assert adapted.parameters == {
        "reasoning_effort": "max",
        "extra_body": {"thinking": {"type": "enabled"}},
    }


def test_acg_safe_invocation_result_has_no_reasoning_field():
    fields = LLMInvocationResult.model_fields
    assert "reasoning_content" not in fields
    result = LLMInvocationResult(
        content="final",
        usage=LLMUsage(total_tokens=10),
        audit=ModelInvocationAudit(
            provider="deepseek",
            requested_model="deepseek-v4-pro",
            effective_model="deepseek-v4-pro",
            requested_thinking_mode=ThinkingMode.DEEP,
            effective_thinking_mode=ThinkingMode.DEEP,
            effective_reasoning_effort="max",
        ),
    )
    assert "reasoning_content" not in result.model_dump()


def test_provider_raw_result_keeps_reasoning_provider_private():
    completion = SimpleNamespace(
        id="response-1",
        usage=None,
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(
                    content="final answer",
                    reasoning_content="private reasoning",
                    tool_calls=None,
                ),
            )
        ],
    )
    raw = OpenAICompatibleProvider._extract_raw_result(completion)
    assert isinstance(raw, ProviderRawResult)
    assert raw.reasoning_content == "private reasoning"
    assert raw.content == "final answer"


def test_json_provider_prompt_contains_the_supplied_schema():
    prompt = OpenAICompatibleProvider._json_system_prompt({
        "type": "object",
        "required": ["parties"],
        "properties": {"parties": {"type": "array"}},
    })
    assert '"required":["parties"]' in prompt
    assert '"parties":{"type":"array"}' in prompt


def test_openai_compatible_provider_uses_one_explicit_request_budget(monkeypatch):
    captured = {}

    def fake_openai(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=fake_openai))
    OpenAICompatibleProvider(
        base_url="https://example.test/v1",
        api_key="test-key",
        model="deepseek-v4-flash",
        timeout_seconds=120,
    )

    assert captured["timeout"] == 120
    assert captured["max_retries"] == 0


def test_llm_config_default_budget_supports_deep_report_generation(monkeypatch):
    monkeypatch.delenv("AGENTOS_LLM_TIMEOUT_SECONDS", raising=False)
    assert LLMConfig.from_env().timeout_seconds == 120


def test_legacy_deepseek_adapter_uses_v4_and_preserves_non_thinking_default():
    adapter = DeepSeekAdapter(api_key="test-key", model_name="deepseek-chat")
    assert adapter.get_model_name() == "deepseek-v4-flash"
    parameters = adapter._adapt_parameters(
        temperature=0.7,
        max_tokens=512,
        stream=False,
        thinking_mode=None,
        kwargs={},
    )
    assert parameters["temperature"] == 0.7
    assert parameters["extra_body"] == {"thinking": {"type": "disabled"}}
