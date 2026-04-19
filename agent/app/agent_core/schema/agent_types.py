from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AgentLawyerRequest(BaseModel):
    text: str = Field(..., min_length=1)
    session_id: Optional[str] = Field(default=None, alias="sessionId")

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class AgentTeacherRequest(BaseModel):
    text: str = Field(..., min_length=1)
    session_id: Optional[str] = Field(default=None, alias="sessionId")

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class AgentWriterRequest(BaseModel):
    text: str = Field(..., min_length=1)
    session_id: Optional[str] = Field(default=None, alias="sessionId")

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class AgentProgrammerRequest(BaseModel):
    text: str = Field(..., min_length=1)
    session_id: Optional[str] = Field(default=None, alias="sessionId")

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class PlannedAction(BaseModel):
    thought: str
    action: str
    action_input: Dict[str, Any] = Field(default_factory=dict, alias="actionInput")

    model_config = ConfigDict(populate_by_name=True)


class SkillRequest(BaseModel):
    session_id: str = Field(alias="sessionId")
    text: str
    action_input: Dict[str, Any] = Field(default_factory=dict, alias="actionInput")
    memory: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(populate_by_name=True)


class SkillResult(BaseModel):
    skill_name: str = Field(alias="skillName")
    success: bool = True
    output: Dict[str, Any] = Field(default_factory=dict)
    message: str = ""

    model_config = ConfigDict(populate_by_name=True)


class AgentTraceStep(BaseModel):
    step: int
    thought: str
    action: str
    observation: str


class AgentLawyerResponse(BaseModel):
    success: bool = True
    answer: str
    session_id: str = Field(alias="sessionId")
    skills_used: List[str] = Field(default_factory=list, alias="skillsUsed")
    trace: List[AgentTraceStep] = Field(default_factory=list)
    risk_level: Optional[str] = Field(default=None, alias="riskLevel")
    federated: Dict[str, Any] = Field(default_factory=dict)
    message: Optional[str] = None
    error: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class AgentTeacherResponse(BaseModel):
    success: bool = True
    answer: str
    session_id: str = Field(alias="sessionId")
    skills_used: List[str] = Field(default_factory=list, alias="skillsUsed")
    trace: List[AgentTraceStep] = Field(default_factory=list)
    risk_level: Optional[str] = Field(default=None, alias="riskLevel")
    federated: Dict[str, Any] = Field(default_factory=dict)
    message: Optional[str] = None
    error: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class AgentWriterResponse(BaseModel):
    success: bool = True
    answer: str
    session_id: str = Field(alias="sessionId")
    skills_used: List[str] = Field(default_factory=list, alias="skillsUsed")
    trace: List[AgentTraceStep] = Field(default_factory=list)
    risk_level: Optional[str] = Field(default=None, alias="riskLevel")
    federated: Dict[str, Any] = Field(default_factory=dict)
    message: Optional[str] = None
    error: Optional[str] = None
    inspiration_expand: Optional[Dict[str, Any]] = None
    outline_generate: Optional[Dict[str, Any]] = None
    content_write: Optional[Dict[str, Any]] = None
    character_relation_map: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(populate_by_name=True)


class AgentProgrammerResponse(BaseModel):
    success: bool = True
    answer: str
    session_id: str = Field(alias="sessionId")
    skills_used: List[str] = Field(default_factory=list, alias="skillsUsed")
    trace: List[AgentTraceStep] = Field(default_factory=list)
    risk_level: Optional[str] = Field(default=None, alias="riskLevel")
    federated: Dict[str, Any] = Field(default_factory=dict)
    message: Optional[str] = None
    error: Optional[str] = None
    requirement_analysis: Optional[Dict[str, Any]] = None
    codebase_semantic_search: Optional[Dict[str, Any]] = None
    code_generation: Optional[Dict[str, Any]] = None
    diagram_generation: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(populate_by_name=True)
