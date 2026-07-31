from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Set

from pydantic import BaseModel, Field


class ThinkingMode(str, Enum):
    DISABLED = "disabled"
    STANDARD = "standard"
    DEEP = "deep"


class ModelInvocationPolicy(BaseModel):
    model_profile: str
    thinking_mode: ThinkingMode = ThinkingMode.DISABLED
    response_format: str = "text"
    timeout_ms: int = 60_000
    max_output_tokens: int = 4096
    retry_policy: Optional[str] = None
    fallback_policy: Optional[str] = None


class ResolvedModelPolicy(BaseModel):
    policy_id: str
    policy_version: str
    provider: str
    requested_model: str
    effective_model: str
    requested_thinking_mode: ThinkingMode
    effective_thinking_mode: ThinkingMode
    effective_reasoning_effort: Optional[str] = None
    response_format: str = "text"
    timeout_ms: int = 60_000
    max_output_tokens: int = 4096
    fallback_chain: List[str] = Field(default_factory=list)
    resolution_reasons: List[str] = Field(default_factory=list)


class ProviderModelCapabilities(BaseModel):
    supports_thinking: bool = False
    supported_thinking_modes: Set[ThinkingMode] = Field(
        default_factory=lambda: {ThinkingMode.DISABLED}
    )
    supports_reasoning_effort: bool = False
    supports_tools: bool = True
    supports_tool_choice_in_thinking: bool = True
    requires_reasoning_content_for_tool_calls: bool = False
    requires_non_null_assistant_content_for_tool_calls: bool = False
    supports_json_object: bool = True
    supports_json_schema: bool = False
    supports_developer_role: bool = False
    supports_stream_usage: bool = False
    max_tokens_field: str = "max_tokens"


class ProviderToolCall(BaseModel):
    id: str
    type: str = "function"
    function: Dict[str, Any] = Field(default_factory=dict)


class ProviderProtocolMessage(BaseModel):
    """Provider-private wire message used only for tool-call continuation."""

    role: Literal["system", "user", "assistant", "tool"]
    content: Optional[str] = None
    reasoning_content: Optional[str] = None
    tool_calls: List[ProviderToolCall] = Field(default_factory=list)
    tool_call_id: Optional[str] = None
    name: Optional[str] = None

    def to_provider_dict(self) -> Dict[str, Any]:
        message: Dict[str, Any] = {"role": self.role, "content": self.content}
        if self.role == "assistant" and self.reasoning_content is not None:
            message["reasoning_content"] = self.reasoning_content
        if self.tool_calls:
            message["tool_calls"] = [call.model_dump() for call in self.tool_calls]
        if self.tool_call_id is not None:
            message["tool_call_id"] = self.tool_call_id
        if self.name is not None:
            message["name"] = self.name
        return message


class ProviderConversationState(BaseModel):
    """Encrypted-at-rest Provider protocol state; never a business message or memory."""

    schema_version: int = 1
    conversation_id: str
    provider: str
    model: str
    context_revision: str
    messages: List[ProviderProtocolMessage] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ProviderRawResult(BaseModel):
    """Provider-private result. Never expose this type to ACG or persistence."""

    content: str = ""
    reasoning_content: Optional[str] = None
    tool_calls: List[ProviderToolCall] = Field(default_factory=list)
    raw_usage: Dict[str, Any] = Field(default_factory=dict)
    raw_response_metadata: Dict[str, Any] = Field(default_factory=dict)


class LLMUsage(BaseModel):
    input_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


class ModelInvocationAudit(BaseModel):
    provider: str
    requested_model: str
    effective_model: str
    requested_thinking_mode: ThinkingMode
    effective_thinking_mode: ThinkingMode
    effective_reasoning_effort: Optional[str] = None
    latency_ms: int = 0
    retry_count: int = 0
    fallback_used: bool = False
    policy_id: Optional[str] = None
    policy_version: Optional[str] = None
    policy_resolution_reasons: List[str] = Field(default_factory=list)
    context_revision: Optional[str] = None
    context_reset_reason: Optional[str] = None
    created_at: Optional[datetime] = None


class LLMInvocationResult(BaseModel):
    """ACG-safe result. Raw provider reasoning is intentionally absent."""

    content: str = ""
    parsed_output: Optional[Dict[str, Any]] = None
    usage: LLMUsage = Field(default_factory=LLMUsage)
    audit: ModelInvocationAudit
    finish_reason: Optional[str] = None


__all__ = [
    "LLMInvocationResult",
    "LLMUsage",
    "ModelInvocationAudit",
    "ModelInvocationPolicy",
    "ProviderModelCapabilities",
    "ProviderConversationState",
    "ProviderProtocolMessage",
    "ProviderRawResult",
    "ProviderToolCall",
    "ResolvedModelPolicy",
    "ThinkingMode",
]
