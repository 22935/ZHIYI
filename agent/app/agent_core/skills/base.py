from abc import ABC, abstractmethod

from app.agent_core.schema.agent_types import SkillRequest, SkillResult


class BaseSkill(ABC):
    """Base class for all agent skills."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def run(self, request: SkillRequest) -> SkillResult:
        raise NotImplementedError


class NoOpSkill(BaseSkill):
    """Temporary placeholder skill used in Phase 1."""

    async def run(self, request: SkillRequest) -> SkillResult:
        return SkillResult(
            skillName=self.name,
            success=True,
            output={
                "echo": request.text,
                "actionInput": request.action_input,
            },
            message=f"{self.name} placeholder executed.",
        )

