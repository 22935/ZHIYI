"""Programmer workflow pack."""

from pathlib import Path

from agentos.packs.programmer.agents import (
    CodeGenerationAgent,
    CodebaseSearchAgent,
    DiagramGenerationAgent,
    RequirementAnalysisAgent,
)


def register_pack(agent_registry, workflow_registry) -> None:
    """Register the programmer workflow pack."""

    agent_registry.register(RequirementAnalysisAgent())
    agent_registry.register(CodebaseSearchAgent())
    agent_registry.register(CodeGenerationAgent())
    agent_registry.register(DiagramGenerationAgent())
    workflow_registry.load_directory(Path(__file__).resolve().parent / "workflows")
