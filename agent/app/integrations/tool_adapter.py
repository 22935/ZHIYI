"""Register the application read-only tool runtime with AgentOS Core."""

from agentos.adapters.tool_adapter import register_tool_runtime_factory
from app.tools import get_tool_runtime


def configure_tool_adapter() -> None:
    register_tool_runtime_factory(get_tool_runtime)


__all__ = ["configure_tool_adapter"]
