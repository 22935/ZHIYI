"""Catalog-driven parsing of raw intent into a domain-neutral semantic profile."""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol

from agentos.core.acg.enums import ComplexityLevel
from agentos.core.planning.capabilities import (
    CapabilityCatalog,
    highest_planning_risk_level,
)
from agentos.core.planning.default_catalog import build_default_capability_catalog
from agentos.core.planning.profile import CapabilityCandidate, TaskSemanticProfile


class IntentLLM(Protocol):
    def generate_json(self, prompt: str, schema: Dict[str, Any], **kwargs) -> Dict[str, Any]: ...


_PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "primaryGoal": {"type": "string"},
        "keyConstraints": {"type": "array", "items": {"type": "string"}},
        "requiredCapabilities": {"type": "array", "items": {"type": "string"}},
        "expectedArtifacts": {"type": "array", "items": {"type": "string"}},
        "verificationRequirements": {"type": "array", "items": {"type": "string"}},
        "estimatedComplexity": {
            "type": "string",
            "enum": ["simple", "medium", "complex", "extreme"],
        },
        "domainHint": {"type": "string"},
        "taskTypeHint": {"type": "string"},
        "implicitRequirements": {"type": "array", "items": {"type": "string"}},
        "riskLevel": {"type": "string"},
    },
    "required": ["primaryGoal", "requiredCapabilities", "estimatedComplexity"],
}

_NATIVE_FALLBACK = ["task_understanding", "analysis", "artifact_generation"]


class IntentParser:
    """Select only registered capabilities, using an LLM or deterministic aliases."""

    def __init__(
        self,
        llm: Optional[IntentLLM] = None,
        capability_catalog: CapabilityCatalog | None = None,
    ) -> None:
        self.llm = llm
        self.capability_catalog = capability_catalog or build_default_capability_catalog()

    def parse(
        self,
        *,
        intent: str,
        domain: str = "general",
        task_type: str = "general",
        thinking_mode: str | None = None,
        use_llm: bool = True,
    ) -> TaskSemanticProfile:
        if use_llm and self.llm is not None:
            try:
                return self._parse_with_llm(intent, domain, task_type, thinking_mode)
            except Exception:
                pass
        return self._heuristic(intent, domain, task_type)

    def _parse_with_llm(
        self,
        intent: str,
        domain: str,
        task_type: str,
        thinking_mode: str | None,
    ) -> TaskSemanticProfile:
        result = self.llm.generate_json(
            self.build_prompt(intent=intent, domain=domain, task_type=task_type),
            _PROFILE_SCHEMA,
            thinking_mode=thinking_mode,
        )
        data = result.get("data", result) if isinstance(result, dict) else {}
        data = dict(data) if isinstance(data, dict) else {}
        data.pop("entropyBudget", None)
        data.pop("entropy_budget", None)
        data.setdefault("domainHint", domain)
        data.setdefault("taskTypeHint", task_type)
        data["rawIntent"] = intent
        data["requiredCapabilities"] = self._normalize_capabilities(
            data.get("requiredCapabilities") or [],
            domain=domain,
        )
        data["capabilityCandidates"] = [
            CapabilityCandidate(
                capabilityId=capability_id,
                score=1.0,
                matchedTerms=[],
                source="llm",
            ).model_dump(by_alias=True)
            for capability_id in data["requiredCapabilities"]
        ]
        profile = TaskSemanticProfile.model_validate(data)
        if not profile.primary_goal.strip() or not profile.required_capabilities:
            raise ValueError("LLM returned no executable registered capability")
        return self._finalize(profile, intent=intent, domain=domain, task_type=task_type)

    def build_prompt(self, *, intent: str, domain: str, task_type: str) -> str:
        options = "\n".join(
            f"- {item.capability_id}: {item.display_name}；{item.description}"
            for item in self.capability_catalog.available(domain)
        )
        return (
            "你是任务规划的意图解析器。只返回 JSON。\n"
            "从下列目录选择实际需要执行的稳定 capabilityId，不得创造目录外能力。\n"
            f"可选执行能力：\n{options}\n\n"
            "返回 primaryGoal、keyConstraints、requiredCapabilities、expectedArtifacts、"
            "verificationRequirements、estimatedComplexity、domainHint、taskTypeHint、"
            "implicitRequirements、riskLevel。\n"
            f"领域提示：{domain}\n任务类型提示：{task_type}\n用户需求：{intent}\n"
        )

    def _heuristic(self, intent: str, domain: str, task_type: str) -> TaskSemanticProfile:
        text = intent or ""
        length = len(text)
        complexity = (
            ComplexityLevel.COMPLEX
            if length > 600
            else ComplexityLevel.MEDIUM
            if length > 200
            else ComplexityLevel.SIMPLE
        )
        candidates = self._infer_capability_candidates(text, domain)
        capabilities = [candidate.capability_id for candidate in candidates]
        profile = TaskSemanticProfile(
            primaryGoal=text[:80] or task_type,
            requiredCapabilities=capabilities,
            capabilityCandidates=candidates,
            expectedArtifacts=["deliverable"] if "artifact_generation" in capabilities else [],
            verificationRequirements=["verification"] if "verification" in capabilities else [],
            estimatedComplexity=complexity,
            domainHint=domain,
            taskTypeHint=task_type,
            riskLevel="normal",
            rawIntent=text,
        )
        return self._finalize(profile, intent=text, domain=domain, task_type=task_type)

    def _finalize(
        self,
        profile: TaskSemanticProfile,
        *,
        intent: str,
        domain: str,
        task_type: str,
    ) -> TaskSemanticProfile:
        normalized = self._normalize_capabilities(profile.required_capabilities, domain=domain)
        if not normalized:
            normalized = list(_NATIVE_FALLBACK)
        explicit_capabilities = set(normalized)
        profile.required_capabilities = self.capability_catalog.expand_dependencies(normalized)
        by_capability = {
            candidate.capability_id: candidate for candidate in profile.capability_candidates
        }
        profile.capability_candidates = [
            by_capability.get(capability_id)
            or CapabilityCandidate(
                capabilityId=capability_id,
                score=1.0,
                matchedTerms=[],
                source=(
                    "dependency"
                    if capability_id not in explicit_capabilities
                    else "fallback"
                    if capability_id in _NATIVE_FALLBACK
                    else "catalog_alias"
                ),
            )
            for capability_id in profile.required_capabilities
        ]
        profile.risk_level = highest_planning_risk_level(
            [
                profile.risk_level,
                *(
                    self.capability_catalog.get(capability).risk_level_hint
                    for capability in profile.required_capabilities
                ),
            ]
        )
        profile.primary_goal = profile.primary_goal.strip() or (intent or task_type or "Unnamed task")[:80]
        profile.domain_hint = profile.domain_hint or domain
        profile.task_type_hint = profile.task_type_hint or task_type
        profile.raw_intent = profile.raw_intent or intent
        return profile

    def _infer_capabilities(self, text: str, domain: str) -> list[str]:
        return [
            candidate.capability_id
            for candidate in self._infer_capability_candidates(text, domain)
        ]

    def _infer_capability_candidates(
        self, text: str, domain: str
    ) -> list[CapabilityCandidate]:
        normalized_text = "".join(text.lower().split())
        matches: list[CapabilityCandidate] = []
        for descriptor in self.capability_catalog.available(domain):
            matched_terms = [
                term
                for term in descriptor.aliases
                if (term_normalized := "".join(term.lower().split()))
                and term_normalized in normalized_text
            ]
            if matched_terms:
                longest = max(len("".join(term.split())) for term in matched_terms)
                score = min(1.0, 0.6 + 0.08 * len(matched_terms) + longest / 200)
                matches.append(
                    CapabilityCandidate(
                        capabilityId=descriptor.capability_id,
                        score=round(score, 4),
                        matchedTerms=matched_terms,
                        source="catalog_alias",
                    )
                )

        if domain.strip().lower() == "general":
            specialized = [
                item for item in matches if item.capability_id not in _NATIVE_FALLBACK
            ]
            if not specialized:
                return [
                    CapabilityCandidate(
                        capabilityId=capability_id,
                        score=1.0,
                        matchedTerms=[],
                        source="fallback",
                    )
                    for capability_id in _NATIVE_FALLBACK
                ]
            matches = [
                CapabilityCandidate(
                    capabilityId="task_understanding",
                    score=1.0,
                    matchedTerms=[],
                    source="fallback",
                ),
                *specialized,
            ]
            if "artifact_generation" not in {
                item.capability_id for item in matches
            }:
                matches.append(
                    CapabilityCandidate(
                        capabilityId="artifact_generation",
                        score=1.0,
                        matchedTerms=[],
                        source="fallback",
                    )
                )
        normalized = self._normalize_capabilities(
            [item.capability_id for item in matches], domain=domain
        )
        by_capability = {item.capability_id: item for item in matches}
        return [by_capability[item] for item in normalized]

    def _normalize_capabilities(self, values, *, domain: str) -> list[str]:
        available = {
            descriptor.capability_id
            for descriptor in self.capability_catalog.available(domain)
        }
        normalized: list[str] = []
        for value in values:
            try:
                descriptor = self.capability_catalog.resolve(str(value))
            except KeyError:
                continue
            if descriptor.capability_id in available and descriptor.capability_id not in normalized:
                normalized.append(descriptor.capability_id)
        return normalized


__all__ = ["IntentParser", "IntentLLM", "TaskSemanticProfile"]
