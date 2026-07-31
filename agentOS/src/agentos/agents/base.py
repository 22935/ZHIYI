"""AgentOS Core 的智能体基础接口，定义 AgentProfile、AgentOutput、运行上下文和 BaseAgent。"""


from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field
from ..core.models.types import AgentTask, WorkflowDefinition, WorkflowRun, WorkflowStep


class AgentProfile(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    agent_name: str = Field(alias="agentName")
    domain: str
    capabilities: List[str] = Field(default_factory=list)
    allowed_skills: List[str] = Field(default_factory=list, alias="allowedSkills")
    allowed_tools: List[str] = Field(default_factory=list, alias="allowedTools")
    risk_level: str = Field(default="normal", alias="riskLevel")
    description: str = ""
    agent_id: Optional[str] = Field(default=None, alias="agentId")
    model_name: Optional[str] = Field(default=None, alias="modelName")
    binding_priority: int = Field(default=0, alias="bindingPriority")
    enabled: bool = True
    source: Literal["native", "plugin"] = "native"
    plugin_id: Optional[str] = Field(default=None, alias="pluginId")
    plugin_version: Optional[str] = Field(default=None, alias="pluginVersion")
    contribution_id: Optional[str] = Field(default=None, alias="contributionId")


class AgentOutput(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    output: Dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    risk_level: Optional[str] = Field(default=None, alias="riskLevel")
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    tool_executions: List[Dict[str, Any]] = Field(default_factory=list, alias="toolExecutions")
    evidence_refs: List[str] = Field(default_factory=list, alias="evidenceRefs")
    model_invocations: List[Dict[str, Any]] = Field(
        default_factory=list, alias="modelInvocations"
    )


class AgentRunContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    task: AgentTask
    run: WorkflowRun
    workflow: WorkflowDefinition
    step: WorkflowStep
    memory: Any
    context_pack: Optional[Any] = Field(default=None, alias="contextPack")
    tool_runtime: Optional[Any] = Field(default=None, alias="toolRuntime")
    model_runtime: Optional[Any] = Field(default=None, alias="modelRuntime")
    capability_descriptor: Optional[Any] = Field(
        default=None, alias="capabilityDescriptor"
    )


class BaseAgent(ABC):
    """所有应用层 Pack 智能体的统一接口。"""

    def __init__(self, profile: AgentProfile):
        self.profile = profile

    @abstractmethod
    async def run(self, context: AgentRunContext) -> AgentOutput:
        raise NotImplementedError

    async def review(self, context: AgentRunContext) -> AgentOutput:
        return await self.run(context)
