from __future__ import annotations

import inspect
from pathlib import Path

from agentos.agents import AgentOutput, AgentProfile, AgentRegistry, BaseAgent
from agentos.core.acg import ControlType, EdgeType, NodeType, validate_blueprint
from agentos.core.planning import (
    ACGBuilder,
    CapabilityCatalog,
    CognitiveRouter,
    IntentParser,
    PlanningCapabilityDescriptor,
    TaskSemanticProfile,
)
from agentos.core.planning.cognitive_router import CapabilityBinding, CollaborationNetwork
from agentos.core.planning.default_catalog import build_default_capability_catalog


class Agent(BaseAgent):
    def __init__(self, name: str, domain: str, capability: str, priority: int = 0):
        super().__init__(
            AgentProfile(
                agentName=name,
                domain=domain,
                capabilities=[capability],
                bindingPriority=priority,
            )
        )

    async def run(self, context):
        return AgentOutput(output={}, summary="ok")


def test_intent_prompt_is_catalog_driven_and_general_prompt_has_no_specialized_fields():
    parser = IntentParser(capability_catalog=build_default_capability_catalog())

    prompt = parser.build_prompt(intent="design a system", domain="general", task_type="general")

    assert "architecture_design" in prompt
    assert "process_decomposition" in prompt
    assert "contract_type" not in prompt
    assert "legal_evidence_match" not in prompt


def test_intent_parser_filters_unknown_llm_capability_and_uses_deterministic_fallback():
    class LLM:
        def generate_json(self, prompt, schema, **kwargs):
            return {
                "data": {
                    "primaryGoal": "unknown",
                    "requiredCapabilities": ["invented_capability"],
                    "estimatedComplexity": "simple",
                }
            }

    profile = IntentParser(LLM()).parse(
        intent="把这件事情妥善处理好",
        domain="general",
        task_type="general",
    )

    assert profile.required_capabilities == [
        "task_understanding",
        "analysis",
        "artifact_generation",
    ]


def test_deterministic_parser_distinguishes_three_task_families():
    parser = IntentParser()
    software = parser.parse(
        intent="设计企业知识库系统技术方案，包括需求、系统架构、数据流、安全风险和验收方式",
        domain="general",
        task_type="general",
        use_llm=False,
    )
    industrial = parser.parse(
        intent="规划装配生产线，包括工序拆解、设备资源、产能、成本、质量控制和风险",
        domain="general",
        task_type="general",
        use_llm=False,
    )
    research = parser.parse(
        intent="形成研究报告，需要资料梳理、证据分析、方案比较、结论验证和最终报告",
        domain="general",
        task_type="general",
        use_llm=False,
    )

    assert {"requirement_analysis", "architecture_design"}.issubset(software.required_capabilities)
    assert "process_decomposition" not in software.required_capabilities
    assert {"process_decomposition", "resource_planning", "cost_analysis"}.issubset(
        industrial.required_capabilities
    )
    assert {"information_retrieval", "evidence_analysis", "comparative_analysis"}.issubset(
        research.required_capabilities
    )
    assert "architecture_design" not in research.required_capabilities


def test_equivalent_industrial_meaning_selects_equivalent_capabilities():
    parser = IntentParser()

    first = parser.parse(
        intent="规划装配流程，完成工序拆解、设备资源配置、成本预算、质量控制和风险分析",
        domain="general",
        task_type="general",
        use_llm=False,
    )
    second = parser.parse(
        intent="制定制造方案，需要步骤拆解、人员配置与产能、费用评估、验证以及风险控制",
        domain="general",
        task_type="general",
        use_llm=False,
    )

    assert first.required_capabilities == second.required_capabilities


def test_scene_word_without_capability_semantics_uses_bounded_fallback():
    profile = IntentParser().parse(
        intent="请把‘生产线’这个词写成一句简短摘要",
        domain="general",
        task_type="general",
        use_llm=False,
    )

    assert profile.required_capabilities == [
        "task_understanding",
        "analysis",
        "artifact_generation",
    ]
    assert profile.risk_level == "normal"


def test_risk_level_is_derived_from_selected_capability_metadata():
    profile = IntentParser().parse(
        intent="分析实施过程中的安全风险和风险控制措施",
        domain="general",
        task_type="general",
        use_llm=False,
    )

    assert "risk_analysis" in profile.required_capabilities
    assert profile.risk_level == "high"


def test_risk_level_changes_with_descriptor_hint_and_ignores_unselected_hints():
    def parse_with_hint(selected_hint: str, unselected_hint: str):
        catalog = CapabilityCatalog(
            [
                PlanningCapabilityDescriptor(
                    capabilityId="task_understanding",
                    displayName="Understand",
                    parallelizable=False,
                ),
                PlanningCapabilityDescriptor(
                    capabilityId="analysis",
                    displayName="Analyze",
                    aliases=["inspect"],
                    dependsOn=["task_understanding"],
                    riskLevelHint=selected_hint,
                ),
                PlanningCapabilityDescriptor(
                    capabilityId="artifact_generation",
                    displayName="Deliver",
                    dependsOn=["task_understanding"],
                    optionalDependencies=["analysis"],
                    parallelizable=False,
                ),
                PlanningCapabilityDescriptor(
                    capabilityId="unselected",
                    displayName="Unselected",
                    aliases=["not-present"],
                    riskLevelHint=unselected_hint,
                ),
            ]
        )
        return IntentParser(capability_catalog=catalog).parse(
            intent="inspect",
            domain="general",
            use_llm=False,
        )

    elevated = parse_with_hint("elevated", "critical")
    critical = parse_with_hint("critical", "normal")

    assert elevated.risk_level == "elevated"
    assert critical.risk_level == "critical"


def test_intent_selection_changes_only_with_catalog_descriptor_and_alias():
    def catalog_with(alias: str | None) -> CapabilityCatalog:
        descriptors = [
            PlanningCapabilityDescriptor(
                capabilityId="task_understanding",
                displayName="Understand",
                aliases=["understand"],
                parallelizable=False,
            ),
            PlanningCapabilityDescriptor(
                capabilityId="analysis",
                displayName="Analyze",
                aliases=["analyze"],
                dependsOn=["task_understanding"],
            ),
            PlanningCapabilityDescriptor(
                capabilityId="artifact_generation",
                displayName="Deliver",
                aliases=["deliver"],
                dependsOn=["task_understanding"],
                optionalDependencies=["analysis", "custom_capability"] if alias else ["analysis"],
                parallelizable=False,
            ),
        ]
        if alias:
            descriptors.append(
                PlanningCapabilityDescriptor(
                    capabilityId="custom_capability",
                    displayName="Custom",
                    aliases=[alias],
                    dependsOn=["task_understanding"],
                )
            )
        catalog = CapabilityCatalog(descriptors)
        catalog.validate()
        return catalog

    old_alias = IntentParser(capability_catalog=catalog_with("semantic-marker")).parse(
        intent="semantic-marker",
        domain="general",
        use_llm=False,
    )
    changed_alias = IntentParser(capability_catalog=catalog_with("replacement-marker")).parse(
        intent="semantic-marker",
        domain="general",
        use_llm=False,
    )
    descriptor_removed = IntentParser(capability_catalog=catalog_with(None)).parse(
        intent="replacement-marker",
        domain="general",
        use_llm=False,
    )

    assert "custom_capability" in old_alias.required_capabilities
    assert changed_alias.required_capabilities == [
        "task_understanding",
        "analysis",
        "artifact_generation",
    ]
    assert descriptor_removed.required_capabilities == changed_alias.required_capabilities


def test_router_prefers_exact_domain_then_general_and_never_leaks_to_general_task():
    catalog = CapabilityCatalog(
        [PlanningCapabilityDescriptor(capabilityId="inspect", displayName="Inspect")]
    )
    agents = AgentRegistry()
    agents.register(Agent("general_agent", "general", "inspect", priority=100))
    agents.register(Agent("specialized_agent", "specialized", "inspect"))
    router = CognitiveRouter(agents, catalog)
    profile = TaskSemanticProfile(primaryGoal="x", requiredCapabilities=["inspect"])

    specialized = router.route(profile, domain="specialized")
    general = router.route(profile, domain="general")

    assert specialized.bindings[0].agent_name == "specialized_agent"
    assert general.bindings[0].agent_name == "general_agent"


def test_router_uses_catalog_alias_and_stable_registration_order():
    catalog = CapabilityCatalog(
        [
            PlanningCapabilityDescriptor(
                capabilityId="inspect",
                displayName="Inspect",
                aliases=["inspection"],
            )
        ]
    )
    agents = AgentRegistry()
    agents.register(Agent("first", "general", "inspection"))
    agents.register(Agent("second", "general", "inspection"))
    profile = TaskSemanticProfile(primaryGoal="x", requiredCapabilities=["inspect"])

    first = CognitiveRouter(agents, catalog).route(profile, domain="general")
    second = CognitiveRouter(agents, catalog).route(profile, domain="general")

    assert first.bindings[0].agent_name == second.bindings[0].agent_name == "first"


def test_router_reports_unresolved_capability():
    catalog = CapabilityCatalog(
        [PlanningCapabilityDescriptor(capabilityId="inspect", displayName="Inspect")]
    )
    profile = TaskSemanticProfile(primaryGoal="x", requiredCapabilities=["inspect"])

    network = CognitiveRouter(AgentRegistry(), catalog).route(profile, domain="general")

    assert network.unresolved_capabilities == ["inspect"]


def test_generic_builder_derives_dependencies_parallel_flags_and_enrichment_nodes():
    schema = {"type": "object", "required": ["value"]}
    catalog = CapabilityCatalog(
        [
            PlanningCapabilityDescriptor(
                capabilityId="start", displayName="Start", outputContract=schema,
                planningStage="understand", parallelizable=False,
            ),
            PlanningCapabilityDescriptor(
                capabilityId="left", displayName="Left", dependsOn=["start"],
                inputContract=schema, outputContract=schema, planningStage="analysis",
                requiresEvidence=True,
            ),
            PlanningCapabilityDescriptor(
                capabilityId="right", displayName="Right", dependsOn=["start"],
                inputContract=schema, outputContract=schema, planningStage="analysis",
                writesMemory=True, requiresReview=True,
            ),
        ]
    )
    catalog.validate()
    network = CollaborationNetwork(
        bindings=[
            CapabilityBinding(capability="start", agent_name="a", score=1),
            CapabilityBinding(capability="left", agent_name="b", score=1),
            CapabilityBinding(capability="right", agent_name="c", score=1),
        ]
    )

    blueprint = ACGBuilder(catalog).build(
        task_id="generic",
        profile=TaskSemanticProfile(primaryGoal="x", requiredCapabilities=["start", "left", "right"]),
        network=network,
    )

    validate_blueprint(blueprint)
    assert len(blueprint.step_nodes()) == 3
    assert any(
        node.node_type == NodeType.CONTROL
        and getattr(node, "control_type", None) == ControlType.PARALLEL
        for node in blueprint.nodes
    )
    assert any(node.node_type == NodeType.EVIDENCE for node in blueprint.nodes)
    assert any(node.node_type == NodeType.MEMORY for node in blueprint.nodes)
    assert next(step for step in blueprint.step_nodes() if step.capability == "right").review_required
    assert all(edge.source_id != edge.target_id for edge in blueprint.edges)
    assert blueprint.edges_of_type(EdgeType.DEPENDENCY)


def test_generic_builder_supports_single_step_without_enrichment():
    catalog = CapabilityCatalog(
        [PlanningCapabilityDescriptor(capabilityId="only", displayName="Only")]
    )
    blueprint = ACGBuilder(catalog).build(
        task_id="single",
        profile=TaskSemanticProfile(primaryGoal="x", requiredCapabilities=["only"]),
        network=CollaborationNetwork(
            bindings=[CapabilityBinding(capability="only", agent_name="agent", score=1)]
        ),
    )

    validate_blueprint(blueprint)
    assert len(blueprint.step_nodes()) == 1
    assert not any(node.node_type in {NodeType.EVIDENCE, NodeType.MEMORY} for node in blueprint.nodes)


def test_generic_builder_follows_descriptor_dependencies_instead_of_fixed_graph():
    schema = {"type": "object", "required": ["value"]}

    def build(right_depends_on: list[str]):
        catalog = CapabilityCatalog(
            [
                PlanningCapabilityDescriptor(
                    capabilityId="root",
                    displayName="Root",
                    outputContract=schema,
                    parallelizable=False,
                ),
                PlanningCapabilityDescriptor(
                    capabilityId="left",
                    displayName="Left",
                    dependsOn=["root"],
                    inputContract=schema,
                    outputContract=schema,
                ),
                PlanningCapabilityDescriptor(
                    capabilityId="right",
                    displayName="Right",
                    dependsOn=right_depends_on,
                    inputContract=schema,
                    outputContract=schema,
                ),
            ]
        )
        network = CollaborationNetwork(
            bindings=[
                CapabilityBinding(capability="root", agent_name="root_agent", score=1),
                CapabilityBinding(capability="left", agent_name="left_agent", score=1),
                CapabilityBinding(capability="right", agent_name="right_agent", score=1),
            ]
        )
        return ACGBuilder(catalog).build(
            task_id="descriptor-driven",
            profile=TaskSemanticProfile(
                primaryGoal="normalized capability plan",
                requiredCapabilities=["root", "left", "right"],
            ),
            network=network,
        )

    parallel_blueprint = build(["root"])
    chained_blueprint = build(["left"])

    def communication_pairs(blueprint):
        capability_by_node = {
            step.node_id: step.capability for step in blueprint.step_nodes()
        }
        return {
            (capability_by_node[edge.source_id], capability_by_node[edge.target_id])
            for edge in blueprint.edges_of_type(EdgeType.COMMUNICATION)
        }

    assert ("root", "right") in communication_pairs(parallel_blueprint)
    assert ("left", "right") not in communication_pairs(parallel_blueprint)
    assert ("left", "right") in communication_pairs(chained_blueprint)
    assert ("root", "right") not in communication_pairs(chained_blueprint)


def test_generic_builder_api_and_source_have_no_task_scene_input_or_branches():
    parameters = set(inspect.signature(ACGBuilder.build).parameters)
    assert parameters == {"self", "task_id", "profile", "network", "variant"}

    source = inspect.getsource(ACGBuilder)
    assert all(
        marker not in source
        for marker in [
            "生产线",
            "industrial",
            "software",
            "research",
            "task_text",
            "build_industrial_graph",
            "SOFTWARE_CAPABILITIES",
        ]
    )


def test_generic_planning_files_do_not_contain_specialized_contract_fields():
    root = Path(__file__).resolve().parents[1] / "src" / "agentos" / "core" / "planning"
    forbidden = {
        "contract_type",
        "payment_terms",
        "acceptance_terms",
        "ip_terms",
        "clauses",
        "legal_evidence_match",
        "revision_suggestions",
    }
    for filename in [
        "intent_parser.py",
        "cognitive_router.py",
        "acg_builder.py",
        "engine.py",
        "default_catalog.py",
    ]:
        text = (root / filename).read_text(encoding="utf-8")
        assert not forbidden.intersection(text.split())
        assert all(value not in text for value in forbidden)


def test_generic_planning_files_have_no_scenario_capability_presets():
    root = Path(__file__).resolve().parents[1] / "src" / "agentos" / "core" / "planning"
    forbidden = {
        "INDUSTRIAL_CAPABILITIES",
        "SOFTWARE_CAPABILITIES",
        "RESEARCH_CAPABILITIES",
        "INDUSTRIAL_GRAPH",
        "SOFTWARE_GRAPH",
        "RESEARCH_GRAPH",
        "build_industrial_graph",
        "build_software_graph",
        "build_research_graph",
        "生产线",
    }
    for filename in [
        "intent_parser.py",
        "cognitive_router.py",
        "acg_builder.py",
        "engine.py",
        "default_catalog.py",
    ]:
        text = (root / filename).read_text(encoding="utf-8")
        assert all(value not in text for value in forbidden)
