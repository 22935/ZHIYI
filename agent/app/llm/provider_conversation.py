from __future__ import annotations

import base64
import hashlib
import json
import inspect
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Iterable, Optional, Protocol, Sequence
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken

from app.llm.contracts import (
    ProviderConversationState,
    ProviderProtocolMessage,
    ProviderRawResult,
)


class ProviderConversationStateError(RuntimeError):
    pass


class IncompleteToolBranchError(ProviderConversationStateError):
    pass


class ProviderConversationStore(Protocol):
    async def load_active(
        self, conversation_id: str, provider: str, model: str
    ) -> Optional[ProviderConversationState]: ...

    async def save(self, state: ProviderConversationState) -> None: ...

    async def delete_active(self, conversation_id: str, provider: str, model: str) -> None: ...

    async def ping(self) -> bool: ...


class EncryptedRedisProviderConversationStore:
    """Stores opaque Provider protocol state in Redis with a bounded reclamation TTL."""

    namespace = "kinlin:provider-conversation:v1"

    def __init__(self, redis_client, encryption_secret: str, ttl_seconds: int = 3600):
        if not encryption_secret.strip():
            raise ProviderConversationStateError("Provider state encryption secret is required")
        if ttl_seconds < 60:
            raise ProviderConversationStateError("Provider state TTL must be at least 60 seconds")
        digest = hashlib.sha256(encryption_secret.encode("utf-8")).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))
        self._redis = redis_client
        self._ttl_seconds = ttl_seconds

    @classmethod
    def from_url(
        cls,
        redis_url: str,
        *,
        password: Optional[str],
        encryption_secret: str,
        ttl_seconds: int = 3600,
    ) -> "EncryptedRedisProviderConversationStore":
        from redis.asyncio import Redis

        client = Redis.from_url(
            redis_url,
            password=password or None,
            decode_responses=False,
            socket_connect_timeout=3,
            socket_timeout=3,
            health_check_interval=30,
        )
        return cls(client, encryption_secret, ttl_seconds)

    def _identity(self, conversation_id: str, provider: str, model: str) -> str:
        raw = json.dumps(
            [conversation_id, provider, model], ensure_ascii=True, separators=(",", ":")
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _active_key(self, conversation_id: str, provider: str, model: str) -> str:
        return f"{self.namespace}:active:{self._identity(conversation_id, provider, model)}"

    def _state_key(self, conversation_id: str, provider: str, model: str, revision: str) -> str:
        identity = self._identity(conversation_id, provider, model)
        revision_hash = hashlib.sha256(revision.encode("utf-8")).hexdigest()
        return f"{self.namespace}:state:{identity}:{revision_hash}"

    async def load_active(
        self, conversation_id: str, provider: str, model: str
    ) -> Optional[ProviderConversationState]:
        active_key = self._active_key(conversation_id, provider, model)
        encrypted_revision = await self._redis.get(active_key)
        if not encrypted_revision:
            return None
        try:
            revision = self._fernet.decrypt(encrypted_revision).decode("utf-8")
            state_key = self._state_key(conversation_id, provider, model, revision)
            encrypted_state = await self._redis.get(state_key)
            if not encrypted_state:
                await self._redis.delete(active_key)
                return None
            payload = self._fernet.decrypt(encrypted_state)
            state = ProviderConversationState.model_validate_json(payload)
        except (InvalidToken, UnicodeDecodeError, ValueError):
            await self._redis.delete(active_key)
            return None
        if (
            state.conversation_id != conversation_id
            or state.provider != provider
            or state.model != model
            or state.context_revision != revision
        ):
            await self._redis.delete(active_key)
            return None
        return state

    async def save(self, state: ProviderConversationState) -> None:
        _validate_complete_tool_branches(state.messages)
        state_key = self._state_key(
            state.conversation_id, state.provider, state.model, state.context_revision
        )
        active_key = self._active_key(state.conversation_id, state.provider, state.model)
        encrypted_state = self._fernet.encrypt(state.model_dump_json().encode("utf-8"))
        encrypted_revision = self._fernet.encrypt(state.context_revision.encode("utf-8"))
        pipeline = self._redis.pipeline(transaction=True)
        pipeline.set(state_key, encrypted_state, ex=self._ttl_seconds)
        pipeline.set(active_key, encrypted_revision, ex=self._ttl_seconds)
        await pipeline.execute()

    async def delete_active(self, conversation_id: str, provider: str, model: str) -> None:
        active_key = self._active_key(conversation_id, provider, model)
        encrypted_revision = await self._redis.get(active_key)
        keys = [active_key]
        if encrypted_revision:
            try:
                revision = self._fernet.decrypt(encrypted_revision).decode("utf-8")
                keys.append(self._state_key(conversation_id, provider, model, revision))
            except (InvalidToken, UnicodeDecodeError):
                pass
        await self._redis.delete(*keys)

    async def ping(self) -> bool:
        return bool(await self._redis.ping())

    async def close(self) -> None:
        await self._redis.aclose()


@dataclass
class PreparedProviderConversation:
    state: ProviderConversationState
    messages: list[ProviderProtocolMessage]
    restored: bool
    context_reset_reason: Optional[str]


@dataclass
class ProviderToolRoundResult:
    """Provider-layer result; callers must convert it before crossing into ACG."""

    raw_result: ProviderRawResult
    context_revision: str
    context_reset_reason: Optional[str]
    tool_names: list[str]


class ProviderConversationManager:
    def __init__(self, store: ProviderConversationStore):
        self._store = store

    async def ping(self) -> bool:
        return await self._store.ping()

    async def prepare(
        self,
        *,
        conversation_id: str,
        provider: str,
        model: str,
        business_messages: Sequence[ProviderProtocolMessage],
        requested_context_revision: Optional[str] = None,
    ) -> PreparedProviderConversation:
        state = await self._store.load_active(conversation_id, provider, model)
        reset_reason: Optional[str] = None
        if (
            state is not None
            and requested_context_revision
            and state.context_revision != requested_context_revision
        ):
            await self._store.delete_active(conversation_id, provider, model)
            state = None
            reset_reason = "context_revision_changed"
        if state is not None:
            messages = [*state.messages]
            last_user = next(
                (message for message in reversed(business_messages) if message.role == "user"),
                None,
            )
            if last_user is not None:
                messages.append(last_user)
            return PreparedProviderConversation(state, messages, True, None)

        now = datetime.now(timezone.utc)
        if reset_reason is None:
            reset_reason = (
                "provider_state_expired_or_missing"
                if any(message.role == "assistant" for message in business_messages)
                else None
            )
        state = ProviderConversationState(
            conversation_id=conversation_id,
            provider=provider,
            model=model,
            context_revision=requested_context_revision or f"rev_{uuid4().hex}",
            messages=[],
            created_at=now,
            updated_at=now,
        )
        return PreparedProviderConversation(
            state=state,
            messages=list(business_messages),
            restored=False,
            context_reset_reason=reset_reason,
        )

    async def record_tool_exchange(
        self,
        prepared: PreparedProviderConversation,
        raw_result: ProviderRawResult,
        tool_messages: Sequence[ProviderProtocolMessage],
    ) -> ProviderConversationState:
        if not raw_result.tool_calls:
            raise ProviderConversationStateError("Cannot record a tool exchange without tool calls")
        assistant = ProviderProtocolMessage(
            role="assistant",
            content=raw_result.content or "",
            reasoning_content=raw_result.reasoning_content,
            tool_calls=raw_result.tool_calls,
        )
        candidate = [*prepared.messages, assistant, *tool_messages]
        _validate_complete_tool_branches(candidate)
        prepared.messages = candidate
        prepared.state.messages = candidate
        prepared.state.updated_at = datetime.now(timezone.utc)
        await self._store.save(prepared.state)
        return prepared.state

    async def record_final_assistant(
        self,
        prepared: PreparedProviderConversation,
        content: str,
    ) -> ProviderConversationState:
        if not prepared.restored and not prepared.state.messages:
            return prepared.state
        candidate = [
            *prepared.messages,
            ProviderProtocolMessage(role="assistant", content=content or ""),
        ]
        _validate_complete_tool_branches(candidate)
        prepared.state.messages = candidate
        prepared.messages = candidate
        prepared.state.updated_at = datetime.now(timezone.utc)
        await self._store.save(prepared.state)
        return prepared.state

    async def execute_tool_round(
        self,
        prepared: PreparedProviderConversation,
        invoke: Callable[[list[dict]], Awaitable[ProviderRawResult]],
        tool_executor: Callable[[str, dict[str, Any]], Any],
    ) -> ProviderToolRoundResult:
        """Invoke, execute one complete tool branch, then continue to the final assistant."""
        first_result = await invoke(provider_messages(prepared.messages))
        if not first_result.tool_calls:
            await self.record_final_assistant(prepared, first_result.content)
            return ProviderToolRoundResult(
                raw_result=first_result,
                context_revision=prepared.state.context_revision,
                context_reset_reason=prepared.context_reset_reason,
                tool_names=[],
            )

        tool_messages: list[ProviderProtocolMessage] = []
        tool_names: list[str] = []
        for call in first_result.tool_calls:
            name = str(call.function.get("name", ""))
            raw_arguments = call.function.get("arguments", "{}")
            try:
                arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
            except json.JSONDecodeError as exc:
                raise ProviderConversationStateError(
                    f"Tool call {call.id} contains invalid JSON arguments"
                ) from exc
            if not isinstance(arguments, dict):
                raise ProviderConversationStateError(
                    f"Tool call {call.id} arguments must be a JSON object"
                )
            outcome = tool_executor(name, arguments)
            if inspect.isawaitable(outcome):
                outcome = await outcome
            content = outcome if isinstance(outcome, str) else json.dumps(
                outcome, ensure_ascii=False, separators=(",", ":")
            )
            tool_names.append(name)
            tool_messages.append(
                ProviderProtocolMessage(
                    role="tool",
                    content=content,
                    tool_call_id=call.id,
                    name=name or None,
                )
            )

        await self.record_tool_exchange(prepared, first_result, tool_messages)
        final_result = await invoke(provider_messages(prepared.state.messages))
        if final_result.tool_calls:
            raise IncompleteToolBranchError(
                "Provider requested another tool branch beyond the configured round limit"
            )
        await self.record_final_assistant(prepared, final_result.content)
        return ProviderToolRoundResult(
            raw_result=final_result,
            context_revision=prepared.state.context_revision,
            context_reset_reason=prepared.context_reset_reason,
            tool_names=tool_names,
        )


def provider_messages(messages: Iterable[ProviderProtocolMessage]) -> list[dict]:
    return [message.to_provider_dict() for message in messages]


_configured_store: Optional[EncryptedRedisProviderConversationStore] = None
_configured_manager: Optional[ProviderConversationManager] = None


def configured_provider_conversation_manager() -> Optional[ProviderConversationManager]:
    global _configured_manager, _configured_store
    from app.config import settings

    if not settings.PROVIDER_STATE_ENABLED:
        return None
    if _configured_manager is None:
        _configured_store = EncryptedRedisProviderConversationStore.from_url(
            settings.PROVIDER_STATE_REDIS_URL,
            password=settings.REDIS_PASSWORD,
            encryption_secret=settings.AI_INTERNAL_TOKEN,
            ttl_seconds=settings.PROVIDER_STATE_TTL_SECONDS,
        )
        _configured_manager = ProviderConversationManager(_configured_store)
    return _configured_manager


async def close_configured_provider_conversation_store() -> None:
    global _configured_manager, _configured_store
    if _configured_store is not None:
        await _configured_store.close()
    _configured_store = None
    _configured_manager = None


def _validate_complete_tool_branches(messages: Sequence[ProviderProtocolMessage]) -> None:
    pending: set[str] = set()
    for message in messages:
        if (
            message.role == "assistant"
            and message.reasoning_content is not None
            and not message.tool_calls
        ):
            raise ProviderConversationStateError(
                "Assistant reasoning may only be stored with a tool-call branch"
            )
        if pending and message.role != "tool":
            raise IncompleteToolBranchError(
                "Provider conversation contains an incomplete tool-call branch"
            )
        if message.role == "assistant" and message.tool_calls:
            call_ids = [call.id for call in message.tool_calls]
            if any(not call_id for call_id in call_ids) or len(call_ids) != len(set(call_ids)):
                raise IncompleteToolBranchError("Tool call IDs must be non-empty and unique")
            pending = set(call_ids)
        elif message.role == "tool":
            if not message.tool_call_id or message.tool_call_id not in pending:
                raise IncompleteToolBranchError("Tool message does not match a pending tool call")
            pending.remove(message.tool_call_id)
    if pending:
        raise IncompleteToolBranchError(
            "Provider conversation contains an incomplete tool-call branch"
        )


__all__ = [
    "EncryptedRedisProviderConversationStore",
    "IncompleteToolBranchError",
    "PreparedProviderConversation",
    "ProviderToolRoundResult",
    "ProviderConversationManager",
    "ProviderConversationStateError",
    "close_configured_provider_conversation_store",
    "configured_provider_conversation_manager",
    "provider_messages",
]
