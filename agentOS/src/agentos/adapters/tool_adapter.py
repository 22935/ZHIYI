"""Application-neutral tool runtime registration for AgentOS."""

from __future__ import annotations

from typing import Any, Callable, Iterable, Protocol


class ToolRuntime(Protocol):
    def scoped(self, allowed_tools: Iterable[str]) -> "ToolRuntime": ...

    async def run(self, text: str, **kwargs: Any) -> Any: ...

    async def execute(self, name: str, arguments: dict[str, Any], **kwargs: Any) -> Any: ...


ToolRuntimeFactory = Callable[[], ToolRuntime]
_tool_runtime_factory: ToolRuntimeFactory | None = None


def register_tool_runtime_factory(factory: ToolRuntimeFactory) -> None:
    global _tool_runtime_factory
    _tool_runtime_factory = factory


def clear_tool_runtime_factory() -> None:
    global _tool_runtime_factory
    _tool_runtime_factory = None


def configured_tool_runtime() -> ToolRuntime | None:
    return _tool_runtime_factory() if _tool_runtime_factory is not None else None


__all__ = [
    "ToolRuntime",
    "ToolRuntimeFactory",
    "clear_tool_runtime_factory",
    "configured_tool_runtime",
    "register_tool_runtime_factory",
]
