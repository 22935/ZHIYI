"""Compatibility facade for the historical ``support.acg.models`` API."""

from .capabilities import (
    CapabilityCatalog, CapabilityPromptProfile, PlanningCapabilityDescriptor,
    PlanningRiskLevel, highest_planning_risk_level,
)
from .graph import (
    ConditionEvaluationError, detect_cycle, find_dangling_dependencies, ready_steps,
    topological_order,
)
from .native_capabilities import (
    NATIVE_CAPABILITY_IDS, build_default_capability_catalog,
    native_capability_descriptors, register_native_capabilities,
)
from .planning import (
    ACGResourcePlan, AgentBindingSpec, CommunicationSpec, EvidenceSpec,
    MemoryAccessSpec, SkillRequirementSpec,
)
from .schema import (
    ACGBlueprint, RuntimeBlueprintSpec, ACGEdge, ACGNode, ACGNodeBase,
    BlueprintStatus, ComplexityLevel, ConditionOperator, ConditionSpec,
    ConsensusSpec, ControlNode, ControlType, EdgeActivation, EdgeType,
    LoopSpec, NodeType, ParallelSpec, StepNode, parse_node,
)
from .semantic_profile import CapabilityCandidate, ComplexityAssessment, TaskSemanticProfile
from .validation import ACGValidationError, validate_blueprint

__all__ = [
    "ACGBlueprint", "RuntimeBlueprintSpec", "ACGEdge", "ACGNode", "ACGNodeBase", "ACGValidationError",
    "ACGResourcePlan", "AgentBindingSpec", "BlueprintStatus", "CapabilityCandidate", "CapabilityCatalog",
    "CapabilityPromptProfile", "ComplexityAssessment",
    "ComplexityLevel", "CommunicationSpec", "ConditionEvaluationError", "ConditionOperator", "ConditionSpec",
    "ControlNode", "ControlType", "EdgeActivation", "EdgeType", "EvidenceSpec",
    "MemoryAccessSpec", "NATIVE_CAPABILITY_IDS", "NodeType", "PlanningCapabilityDescriptor",
    "PlanningRiskLevel", "SkillRequirementSpec", "StepNode", "TaskSemanticProfile",
    "build_default_capability_catalog", "detect_cycle", "find_dangling_dependencies",
    "highest_planning_risk_level", "native_capability_descriptors", "parse_node",
    "ready_steps", "register_native_capabilities",
    "topological_order", "validate_blueprint",
]
