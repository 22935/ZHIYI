"""任务语义画像（设计书表2.3）。

意图解析模块的产物，是后续认知路由与 ACG 构建的统一输入。
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field

from agentos.core.acg.enums import ComplexityLevel


class CapabilityCandidate(BaseModel):
    """Catalog-normalized semantic candidate with an auditable confidence score."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    capability_id: str = Field(alias="capabilityId")
    score: float = Field(ge=0, le=1)
    matched_terms: List[str] = Field(default_factory=list, alias="matchedTerms")
    source: Literal["catalog_alias", "llm", "fallback", "dependency"]


class TaskSemanticProfile(BaseModel):
    """结构化任务语义画像。"""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    primary_goal: str = Field(default="", alias="primaryGoal")
    key_constraints: List[str] = Field(default_factory=list, alias="keyConstraints")
    required_capabilities: List[str] = Field(default_factory=list, alias="requiredCapabilities")
    capability_candidates: List[CapabilityCandidate] = Field(
        default_factory=list, alias="capabilityCandidates"
    )
    expected_artifacts: List[str] = Field(default_factory=list, alias="expectedArtifacts")
    verification_requirements: List[str] = Field(
        default_factory=list,
        alias="verificationRequirements",
    )
    estimated_complexity: ComplexityLevel = Field(
        default=ComplexityLevel.SIMPLE, alias="estimatedComplexity"
    )
    domain_hint: str = Field(default="general", alias="domainHint")
    task_type_hint: str = Field(default="general", alias="taskTypeHint")
    implicit_requirements: List[str] = Field(default_factory=list, alias="implicitRequirements")
    risk_level: str = Field(default="normal", alias="riskLevel")
    resource_budget: Dict[str, Any] = Field(default_factory=dict, alias="resourceBudget")
    entropy_budget: int = Field(default=0, alias="entropyBudget")
    raw_intent: str = Field(default="", alias="rawIntent")

    def to_summary(self) -> str:
        caps = ", ".join(self.required_capabilities) or "(none)"
        return f"[{self.domain_hint}/{self.task_type_hint}] {self.primary_goal} | caps={caps}"


__all__ = ["CapabilityCandidate", "TaskSemanticProfile"]
