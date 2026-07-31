from __future__ import annotations

import json
from enum import Enum
from typing import Any, Dict

from pydantic import BaseModel, Field


class ChatStreamEventType(str, Enum):
    REASONING_START = "reasoning_start"
    REASONING_DELTA = "reasoning_delta"
    REASONING_END = "reasoning_end"
    CONTENT_DELTA = "content_delta"
    TOOL_START = "tool_start"
    TOOL_RESULT = "tool_result"
    TOOL_ERROR = "tool_error"
    USAGE = "usage"
    DONE = "done"
    ERROR = "error"


class ChatStreamEvent(BaseModel):
    event: ChatStreamEventType
    request_id: str
    sequence: int
    data: Dict[str, Any] = Field(default_factory=dict)

    def sse_data(self) -> str:
        return json.dumps(
            {
                "event": self.event.value,
                "requestId": self.request_id,
                "sequence": self.sequence,
                "data": self.data,
            },
            ensure_ascii=False,
        )


__all__ = ["ChatStreamEvent", "ChatStreamEventType"]
