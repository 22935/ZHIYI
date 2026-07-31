from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.llm.contracts import (
    ProviderConversationState,
    ProviderProtocolMessage,
    ProviderRawResult,
    ProviderToolCall,
)
from app.llm.provider_conversation import (
    EncryptedRedisProviderConversationStore,
    IncompleteToolBranchError,
    ProviderConversationManager,
)


class FakePipeline:
    def __init__(self, redis):
        self.redis = redis
        self.operations = []

    def set(self, key, value, ex=None):
        self.operations.append((key, value, ex))
        return self

    async def execute(self):
        for key, value, ttl in self.operations:
            self.redis.values[key] = value
            self.redis.ttls[key] = ttl
        return [True] * len(self.operations)


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.ttls = {}

    async def get(self, key):
        return self.values.get(key)

    async def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)
            self.ttls.pop(key, None)

    def pipeline(self, transaction=True):
        assert transaction is True
        return FakePipeline(self)


class MemoryStore:
    def __init__(self):
        self.states = {}

    async def load_active(self, conversation_id, provider, model):
        return self.states.get((conversation_id, provider, model))

    async def save(self, state):
        self.states[(state.conversation_id, state.provider, state.model)] = state.model_copy(deep=True)

    async def delete_active(self, conversation_id, provider, model):
        self.states.pop((conversation_id, provider, model), None)

    async def ping(self):
        return True


def state(messages):
    now = datetime.now(timezone.utc)
    return ProviderConversationState(
        conversation_id="conversation-1",
        provider="deepseek",
        model="deepseek-v4-flash",
        context_revision="rev_one",
        messages=messages,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_redis_state_is_encrypted_ttl_bounded_and_identity_isolated():
    redis = FakeRedis()
    store = EncryptedRedisProviderConversationStore(redis, "encryption-secret", ttl_seconds=900)
    messages = [
        ProviderProtocolMessage(role="user", content="private user text"),
        ProviderProtocolMessage(
            role="assistant",
            content="",
            reasoning_content="private reasoning",
            tool_calls=[ProviderToolCall(id="call-1", function={"name": "lookup", "arguments": "{}"})],
        ),
        ProviderProtocolMessage(role="tool", content="private result", tool_call_id="call-1"),
    ]
    expected = state(messages)

    await store.save(expected)

    serialized_redis = b" ".join(redis.values.values())
    assert b"private user text" not in serialized_redis
    assert b"private reasoning" not in serialized_redis
    assert b"private result" not in serialized_redis
    assert set(redis.ttls.values()) == {900}
    assert await store.load_active(
        "conversation-1", "deepseek", "deepseek-v4-flash"
    ) == expected
    assert await store.load_active(
        "conversation-1", "deepseek", "deepseek-v4-pro"
    ) is None
    assert await store.load_active(
        "conversation-1", "other-provider", "deepseek-v4-flash"
    ) is None


@pytest.mark.asyncio
async def test_store_rejects_incomplete_tool_branch():
    redis = FakeRedis()
    store = EncryptedRedisProviderConversationStore(redis, "encryption-secret")
    incomplete = state(
        [
            ProviderProtocolMessage(
                role="assistant",
                content="",
                reasoning_content="must stay with tool branch",
                tool_calls=[ProviderToolCall(id="call-1", function={"name": "lookup"})],
            )
        ]
    )

    with pytest.raises(IncompleteToolBranchError):
        await store.save(incomplete)
    assert redis.values == {}


@pytest.mark.asyncio
async def test_store_rejects_reasoning_without_tool_calls():
    redis = FakeRedis()
    store = EncryptedRedisProviderConversationStore(redis, "encryption-secret")
    ordinary_reasoning = state(
        [ProviderProtocolMessage(role="assistant", content="answer", reasoning_content="private")]
    )

    with pytest.raises(Exception, match="only be stored with a tool-call branch"):
        await store.save(ordinary_reasoning)
    assert redis.values == {}


@pytest.mark.asyncio
async def test_complete_tool_round_restores_full_protocol_chain_on_next_user_turn():
    store = MemoryStore()
    manager = ProviderConversationManager(store)
    prepared = await manager.prepare(
        conversation_id="conversation-1",
        provider="deepseek",
        model="deepseek-v4-flash",
        business_messages=[ProviderProtocolMessage(role="user", content="find contract")],
    )
    invocations = []

    async def invoke(messages):
        invocations.append(messages)
        if len(invocations) == 1:
            return ProviderRawResult(
                content="",
                reasoning_content="need authoritative evidence",
                tool_calls=[
                    ProviderToolCall(
                        id="call-1",
                        function={"name": "legal_search", "arguments": '{"query":"contract"}'},
                    )
                ],
            )
        return ProviderRawResult(content="final answer", reasoning_content="not persisted")

    result = await manager.execute_tool_round(
        prepared,
        invoke,
        lambda name, arguments: {"source": "civil-code", "query": arguments["query"]},
    )

    assert result.context_revision == prepared.state.context_revision
    assert result.tool_names == ["legal_search"]
    continuation = invocations[1]
    assert continuation[1]["reasoning_content"] == "need authoritative evidence"
    assert continuation[1]["tool_calls"][0]["id"] == "call-1"
    assert continuation[2]["role"] == "tool"
    assert continuation[2]["tool_call_id"] == "call-1"
    assert continuation[2]["content"] == '{"source":"civil-code","query":"contract"}'

    next_turn = await manager.prepare(
        conversation_id="conversation-1",
        provider="deepseek",
        model="deepseek-v4-flash",
        business_messages=[
            ProviderProtocolMessage(role="assistant", content="business history"),
            ProviderProtocolMessage(role="user", content="next question"),
        ],
    )
    outbound = [message.to_provider_dict() for message in next_turn.messages]
    assert next_turn.restored is True
    assert next_turn.context_reset_reason is None
    assert any(message.get("reasoning_content") == "need authoritative evidence" for message in outbound)
    assert any(message.get("tool_call_id") == "call-1" for message in outbound)
    assert outbound[-1] == {"role": "user", "content": "next question"}
    assert "not persisted" not in str(outbound)


@pytest.mark.asyncio
async def test_missing_state_starts_clean_revision_with_auditable_reason():
    manager = ProviderConversationManager(MemoryStore())
    prepared = await manager.prepare(
        conversation_id="conversation-1",
        provider="deepseek",
        model="deepseek-v4-flash",
        business_messages=[
            ProviderProtocolMessage(role="assistant", content="execution summary only"),
            ProviderProtocolMessage(role="user", content="continue"),
        ],
    )

    assert prepared.restored is False
    assert prepared.context_reset_reason == "provider_state_expired_or_missing"
    assert prepared.state.context_revision.startswith("rev_")
    assert all(message.reasoning_content is None for message in prepared.messages)


@pytest.mark.asyncio
async def test_tool_execution_failure_never_persists_partial_branch():
    store = MemoryStore()
    manager = ProviderConversationManager(store)
    prepared = await manager.prepare(
        conversation_id="conversation-1",
        provider="deepseek",
        model="deepseek-v4-flash",
        business_messages=[ProviderProtocolMessage(role="user", content="question")],
    )

    async def invoke(_messages):
        return ProviderRawResult(
            reasoning_content="private reasoning",
            tool_calls=[ProviderToolCall(id="call-1", function={"name": "broken", "arguments": "{}"})],
        )

    def fail(_name, _arguments):
        raise RuntimeError("tool failed")

    with pytest.raises(RuntimeError, match="tool failed"):
        await manager.execute_tool_round(prepared, invoke, fail)
    assert store.states == {}


@pytest.mark.asyncio
async def test_no_tool_call_does_not_persist_provider_reasoning():
    store = MemoryStore()
    manager = ProviderConversationManager(store)
    prepared = await manager.prepare(
        conversation_id="conversation-1",
        provider="deepseek",
        model="deepseek-v4-flash",
        business_messages=[ProviderProtocolMessage(role="user", content="ordinary question")],
    )

    async def invoke(_messages):
        return ProviderRawResult(content="ordinary answer", reasoning_content="unneeded reasoning")

    result = await manager.execute_tool_round(prepared, invoke, lambda _name, _args: None)
    assert result.raw_result.content == "ordinary answer"
    assert store.states == {}


@pytest.mark.asyncio
async def test_explicit_revision_change_invalidates_old_protocol_state():
    store = MemoryStore()
    existing = state(
        [
            ProviderProtocolMessage(role="user", content="old user"),
            ProviderProtocolMessage(role="assistant", content="old answer"),
        ]
    )
    store.states[(existing.conversation_id, existing.provider, existing.model)] = existing
    manager = ProviderConversationManager(store)

    prepared = await manager.prepare(
        conversation_id="conversation-1",
        provider="deepseek",
        model="deepseek-v4-flash",
        requested_context_revision="rev_two",
        business_messages=[
            ProviderProtocolMessage(role="assistant", content="clean execution summary"),
            ProviderProtocolMessage(role="user", content="new user"),
        ],
    )

    assert prepared.restored is False
    assert prepared.state.context_revision == "rev_two"
    assert prepared.context_reset_reason == "context_revision_changed"
    assert all(message.content != "old user" for message in prepared.messages)
