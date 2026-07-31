"""Stable application contracts for tool calls, evidence, and citations."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SourceReference(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    citation_id: str = Field(alias="citationId")
    title: str = ""
    filename: str | None = None
    url: str | None = None
    snippet: str = ""
    provider: str
    retrieved_at: str = Field(alias="retrievedAt")

    def public_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json", exclude_none=True)


class ToolPayload(BaseModel):
    summary: str
    data: Any = Field(default_factory=dict)
    sources: list[SourceReference] = Field(default_factory=list)


class ToolExecutionRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    call_id: str = Field(alias="callId")
    tool_name: str = Field(alias="toolName")
    status: Literal["completed", "failed"]
    duration_ms: int = Field(alias="durationMs")
    input_summary: str = Field(default="", alias="inputSummary")
    output_summary: str = Field(default="", alias="outputSummary")
    source_refs: list[str] = Field(default_factory=list, alias="sourceRefs")
    error_code: str | None = Field(default=None, alias="errorCode")

    def public_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json", exclude_none=True)


class ToolRunResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    text: str
    model: str = ""
    usage: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    sources: list[SourceReference] = Field(default_factory=list)
    tool_executions: list[ToolExecutionRecord] = Field(
        default_factory=list, alias="toolExecutions"
    )


class ToolUnavailableError(RuntimeError):
    code = "TOOL_UNAVAILABLE"


class ToolLimitExceededError(RuntimeError):
    code = "TOOL_CALL_LIMIT_EXCEEDED"


__all__ = [
    "SourceReference",
    "ToolExecutionRecord",
    "ToolLimitExceededError",
    "ToolPayload",
    "ToolRunResult",
    "ToolUnavailableError",
]
