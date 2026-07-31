import pytest
from types import SimpleNamespace

from app.ai_engine.model_runtime import (
    apply_reasoning_instruction,
    build_messages,
    completion_options,
    resolve_system_runtime_config,
    validate_runtime_config,
    stream_with_runtime_model,
)


def test_runtime_config_rejects_invalid_or_embedded_credentials():
    with pytest.raises(ValueError, match="http"):
        validate_runtime_config("model", "ftp://example.com/v1", "secret")
    with pytest.raises(ValueError, match="用户名"):
        validate_runtime_config("model", "https://user:pass@example.com/v1", "secret")


def test_build_messages_does_not_duplicate_latest_user_message():
    messages = build_messages(
        "同一个问题",
        [{"role": "user", "content": "同一个问题"}],
        "off",
    )
    assert messages == [{"role": "user", "content": "同一个问题"}]


def test_reasoning_instruction_reuses_existing_system_message():
    messages = apply_reasoning_instruction(
        [{"role": "system", "content": "你是助手"}, {"role": "user", "content": "分析"}],
        "high",
    )
    assert len(messages) == 2
    assert "深入" in messages[0]["content"]


def test_native_reasoning_options_cover_openai_and_qwen():
    assert completion_options("gpt-5-mini", "https://api.openai.com/v1", "medium") == {
        "reasoning_effort": "medium"
    }
    qwen_options = completion_options(
        "qwen3-plus",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "high",
    )
    assert qwen_options["extra_body"]["enable_thinking"] is True
    assert qwen_options["extra_body"]["thinking_budget"] == 8192

    deepseek_options = completion_options(
        "deepseek-v4-pro",
        "https://api.deepseek.com/v1",
        "high",
    )
    assert deepseek_options == {
        "reasoning_effort": "max",
        "extra_body": {"thinking": {"type": "enabled"}},
    }

    assert completion_options(
        "deepseek-v4-flash",
        "https://api.deepseek.com/v1",
        "disabled",
    ) == {"extra_body": {"thinking": {"type": "disabled"}}}


def test_system_runtime_model_override_reuses_server_credentials(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "server-secret")
    monkeypatch.setattr(settings, "DEEPSEEK_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setattr(settings, "DEEPSEEK_MODEL", "deepseek-chat")

    assert resolve_system_runtime_config("deepseek-v4-pro") == (
        "deepseek-v4-pro",
        "https://api.example.com/v1",
        "server-secret",
    )
    assert resolve_system_runtime_config() == (
        "deepseek-v4-flash",
        "https://api.example.com/v1",
        "server-secret",
    )


async def test_stream_separates_reasoning_content_and_final_content(monkeypatch):
    captured = {}

    class FakeStream:
        def __init__(self):
            self.items = iter([
                SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(
                        reasoning_content="private thought",
                        content=None,
                    ))],
                    usage=None,
                ),
                SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(
                        reasoning_content=None,
                        content="final answer",
                    ))],
                    usage=None,
                ),
                SimpleNamespace(
                    choices=[],
                    usage=SimpleNamespace(
                        prompt_tokens=10,
                        completion_tokens=20,
                        total_tokens=30,
                        reasoning_tokens=12,
                        completion_tokens_details=None,
                    ),
                ),
            ])

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self.items)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    class FakeCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return FakeStream()

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

        async def close(self):
            return None

    monkeypatch.setattr("app.ai_engine.model_runtime.AsyncOpenAI", FakeClient)
    events = [
        event
        async for event in stream_with_runtime_model(
            text="test",
            context=None,
            model="deepseek-v4-pro",
            base_url="https://api.deepseek.com/v1",
            api_key="secret",
            reasoning_effort="deep",
            request_id="request-test",
        )
    ]

    assert [event.event.value for event in events] == [
        "reasoning_start",
        "reasoning_delta",
        "reasoning_end",
        "content_delta",
        "usage",
        "done",
    ]
    assert events[1].data["delta"] == "private thought"
    assert events[3].data["delta"] == "final answer"
    assert events[4].data["reasoningTokens"] == 12
    assert captured["reasoning_effort"] == "max"
    assert "temperature" not in captured
