"""认知规划引擎契约测试。

锁定不变量：意图解析画像、模板匹配阈值命中走静态、无命中走动态生成、
动态 ACG 含赋能节点注入且图合法。
"""

from __future__ import annotations

# Test collection must make the source checkout importable before agentos imports.
# ruff: noqa: E402
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
_AGENT = Path(__file__).resolve().parents[2] / "agent"
if str(_AGENT) not in sys.path:
    sys.path.insert(0, str(_AGENT))

from agentos.agents import AgentRegistry
from agentos.agents.base import AgentOutput, AgentProfile, BaseAgent
from agentos.core.acg import EdgeType, NodeType, validate_blueprint
from agentos.core.acg.enums import ComplexityLevel
from agentos.core.models.types import WorkflowDefinition
from agentos.core.planning import ACGPlanningError, IntentParser, PlanningEngine, TaskSemanticProfile
from agentos.core.planning.cognitive_router import CognitiveRouter
from agentos.core.planning.template_matcher import TemplateMatcher
from agentos.core.planning.default_catalog import build_default_capability_catalog
from agentos.core.workflow.registry import WorkflowRegistry
from packs.legal.planning import register_legal_capabilities


class _Agent(BaseAgent):
    def __init__(self, name, domain, caps):
        super().__init__(AgentProfile(agentName=name, domain=domain, capabilities=caps))

    async def run(self, context):
        return AgentOutput(output={}, summary="ok")


def _legal_catalog():
    catalog = build_default_capability_catalog()
    register_legal_capabilities(catalog)
    return catalog


def _registries():
    wr = WorkflowRegistry()
    wr.register(
        WorkflowDefinition(
            workflowId="legal_contract_review_v1",
            name="合同审查",
            domain="legal",
            intent="contract_review",
            runtimeEngine="acg",
            description="标准合同审查流程：解析、风险、证据、报告",
            steps=[
                {"stepId": "parse", "name": "解析", "agentName": "parse", "nextStepId": "risk"},
                {"stepId": "risk", "name": "风险", "agentName": "risk"},
            ],
        )
    )
    ar = AgentRegistry()
    ar.register(_Agent("parser", "legal", ["文本解析"]))
    ar.register(_Agent("risk", "legal", ["风险识别"]))
    ar.register(_Agent("reporter", "legal", ["报告生成"]))
    return wr, ar


def _legal_acg_agent_registry():
    ar = AgentRegistry()
    for name, caps in [
        ("contract_parse", ["contract_parse"]),
        ("clause_classify", ["clause_classify"]),
        ("risk_detect", ["risk_detect"]),
        ("legal_evidence_match", ["legal_evidence_match"]),
        ("revision_suggest", ["revision_suggest"]),
        ("human_review", ["human_review_gate"]),
        ("report_generate", ["report_generate"]),
    ]:
        ar.register(_Agent(name, "legal", caps))
    return ar


# ---------- 意图解析 ----------
def test_intent_parser_heuristic_extracts_capabilities():
    parser = IntentParser(capability_catalog=_legal_catalog())  # 无 LLM，走启发式
    profile = parser.parse(intent="审查合同违约风险并生成报告", domain="legal", task_type="contract_review")
    assert isinstance(profile, TaskSemanticProfile)
    assert profile.domain_hint == "legal"
    assert "风险识别" in profile.required_capabilities
    assert "报告生成" in profile.required_capabilities
    assert profile.risk_level == "high"  # 含“风险/违约”


def test_intent_parser_uses_injected_llm():
    class _LLM:
        def generate_json(self, prompt, schema, **kwargs):
            return {
                "data": {
                    "primaryGoal": "LLM目标",
                    "requiredCapabilities": ["architecture_design"],
                    "estimatedComplexity": "complex",
                }
            }

    profile = IntentParser(_LLM()).parse(intent="x", domain="general", task_type="impl")
    assert profile.primary_goal == "LLM目标"
    assert profile.required_capabilities == [
        "task_understanding",
        "requirement_analysis",
        "architecture_design",
    ]
    assert profile.estimated_complexity == ComplexityLevel.COMPLEX


def test_intent_parser_does_not_accept_entropy_budget_from_llm():
    class _LLM:
        def generate_json(self, prompt, schema, **kwargs):
            assert "entropyBudget" not in schema["properties"]
            return {
                "data": {
                    "primaryGoal": "完成合同审查",
                    "requiredCapabilities": ["文本解析", "报告生成"],
                    "estimatedComplexity": "complex",
                    "entropyBudget": 1000,
                }
            }

    profile = IntentParser(_LLM(), _legal_catalog()).parse(
        intent="审查合同并生成报告",
        domain="legal",
        task_type="contract_review",
    )

    assert profile.entropy_budget == 0


def test_intent_parser_can_use_deterministic_fast_path():
    class _UnexpectedLLM:
        def generate_json(self, prompt, schema, **kwargs):
            raise AssertionError("deterministic parsing must not call the model")

    profile = IntentParser(_UnexpectedLLM(), _legal_catalog()).parse(
        intent="审查合同风险并生成报告",
        domain="legal",
        task_type="contract_review",
        use_llm=False,
    )

    assert "风险识别" in profile.required_capabilities
    assert "报告生成" in profile.required_capabilities


def test_intent_parser_falls_back_when_llm_raises():
    class _BadLLM:
        def generate_json(self, prompt, schema, **kwargs):
            raise RuntimeError("llm down")

    profile = IntentParser(_BadLLM(), _legal_catalog()).parse(
        intent="审查合同",
        domain="legal",
        task_type="contract_review",
    )
    assert profile.primary_goal  # 回退启发式成功


def test_intent_parser_recovers_from_empty_llm_profile():
    class _EmptyLLM:
        def generate_json(self, prompt, schema, **kwargs):
            return {"data": {}}

    profile = IntentParser(_EmptyLLM(), _legal_catalog()).parse(
        intent="审查合同风险并生成报告",
        domain="legal",
        task_type="contract_review",
    )
    assert profile.primary_goal
    assert "风险识别" in profile.required_capabilities
    assert "报告生成" in profile.required_capabilities


# ---------- 模板匹配 ----------
def test_template_matcher_exact_intent_hits():
    wr, _ = _registries()
    matcher = TemplateMatcher(wr, threshold=0.85)
    profile = TaskSemanticProfile(primaryGoal="审查合同", domainHint="legal", taskTypeHint="contract_review")
    match = matcher.match(profile)
    assert matcher.is_hit(match)
    assert match.workflow.workflow_id == "legal_contract_review_v1"


def test_template_matcher_no_domain_returns_none():
    wr, _ = _registries()
    matcher = TemplateMatcher(wr)
    profile = TaskSemanticProfile(primaryGoal="x", domainHint="aerospace", taskTypeHint="design")
    match = matcher.match(profile)
    assert not matcher.is_hit(match)


# ---------- 端到端规划 ----------
def test_plan_static_template_path():
    wr, ar = _registries()
    engine = PlanningEngine(
        workflow_registry=wr,
        agent_registry=ar,
        capability_catalog=_legal_catalog(),
    )
    result = engine.plan(
        task_id="t1", intent="审查这份采购合同的违约风险", domain="legal", task_type="contract_review"
    )
    assert result.strategy == "static_template"
    assert result.template_id == "legal_contract_review_v1"
    validate_blueprint(result.blueprint)
    # 升格后含 Step 节点；enrich 默认注入 Agent 等认知节点丰富拓扑
    assert len(result.blueprint.step_nodes()) >= 1
    assert all(s.node_type == NodeType.STEP for s in result.blueprint.step_nodes())


def test_stochastic_diversity_bypasses_static_template():
    workflows, _ = _registries()
    engine = PlanningEngine(
        workflow_registry=workflows,
        agent_registry=_legal_acg_agent_registry(),
        capability_catalog=_legal_catalog(),
    )

    result = engine.plan(
        task_id="stochastic-template-bypass",
        intent="审查合同风险并生成报告",
        domain="legal",
        task_type="contract_review",
        planning_diversity="balanced",
        planning_seed=284731,
    )

    assert result.strategy == "dynamic_generation"
    assert result.template_id is None
    validate_blueprint(result.blueprint)


def test_plan_dynamic_generation_path():
    wr, ar = _registries()
    engine = PlanningEngine(
        workflow_registry=wr,
        agent_registry=ar,
        capability_catalog=_legal_catalog(),
    )
    result = engine.plan(
        task_id="t2",
        intent="分析跨境并购的税务合规与风险并生成报告",
        domain="legal",
        task_type="ma_tax_analysis",
    )
    assert result.strategy == "dynamic_generation"
    validate_blueprint(result.blueprint)
    # 动态图应注入赋能节点（Evidence/Memory）
    node_types = {n.node_type for n in result.blueprint.nodes}
    assert NodeType.STEP in node_types
    assert NodeType.EVIDENCE in node_types or NodeType.MEMORY in node_types


def test_plan_force_dynamic_bypasses_template_and_adds_data_edges():
    wr, _ = _registries()
    ar = _legal_acg_agent_registry()
    engine = PlanningEngine(
        workflow_registry=wr,
        agent_registry=ar,
        capability_catalog=_legal_catalog(),
    )
    result = engine.plan(
        task_id="t3",
        intent="审查这份合同中的付款、验收、知识产权和违约责任风险，匹配依据，生成修改建议、人工审核要点和审查报告",
        domain="legal",
        task_type="contract_review",
        force_dynamic=True,
    )

    assert result.strategy == "dynamic_generation"
    assert result.template_id is None
    assert result.template_score == 0.0
    validate_blueprint(result.blueprint)

    roles = {step.metadata.get("role") for step in result.blueprint.step_nodes()}
    assert {"parse", "classify", "risk", "evidence", "suggest", "review", "report"}.issubset(roles)
    agents = {step.agent_name for step in result.blueprint.step_nodes()}
    assert {
        "contract_parse",
        "clause_classify",
        "risk_detect",
        "legal_evidence_match",
        "revision_suggest",
        "human_review",
        "report_generate",
    }.issubset(agents)
    communication_edges = result.blueprint.edges_of_type(EdgeType.COMMUNICATION)
    assert communication_edges
    assert any(edge.data_fields for edge in communication_edges)
    step_ids = {step.node_id for step in result.blueprint.step_nodes()}
    assert all(
        edge.source_id in step_ids and edge.target_id in step_ids
        for edge in communication_edges
    )


def test_dynamic_planner_drops_meta_capabilities_from_llm():
    class _LLM:
        def generate_json(self, prompt, schema, **kwargs):
            return {
                "data": {
                    "primaryGoal": "以 ACG 多智能体方式完成合同审查",
                    "requiredCapabilities": [
                        "文本解析",
                        "条款分类",
                        "风险识别",
                        "证据/依据匹配",
                        "多智能体协作编排",
                        "最终 Markdown 审查报告生成",
                    ],
                    "estimatedComplexity": "complex",
                    "domainHint": "legal",
                    "taskTypeHint": "contract_review",
                }
            }

    wr, _ = _registries()
    engine = PlanningEngine(
        workflow_registry=wr,
        agent_registry=_legal_acg_agent_registry(),
        capability_catalog=_legal_catalog(),
        intent_llm=_LLM(),
    )
    result = engine.plan(
        task_id="t4",
        intent="请以 ACG 多智能体协作方式审查合同，提取人工审核要点，生成 Markdown 审查报告。",
        domain="legal",
        task_type="contract_review",
        force_dynamic=True,
    )

    validate_blueprint(result.blueprint)
    step_caps = {step.capability for step in result.blueprint.step_nodes()}
    assert "多智能体协作编排" not in step_caps
    assert "报告生成" in step_caps
    assert all(not step.agent_name.startswith("ephemeral::") for step in result.blueprint.step_nodes())


def test_dynamic_planner_normalizes_legal_knowledge_capability_from_llm():
    class _LLM:
        def generate_json(self, prompt, schema, **kwargs):
            return {
                "data": {
                    "primaryGoal": "完成合同法律审查",
                    "requiredCapabilities": ["合同解析", "法律知识应用", "报告生成"],
                    "estimatedComplexity": "complex",
                }
            }

    workflows, _ = _registries()
    engine = PlanningEngine(
        workflow_registry=workflows,
        agent_registry=_legal_acg_agent_registry(),
        capability_catalog=_legal_catalog(),
        intent_llm=_LLM(),
    )
    result = engine.plan(
        task_id="legal-knowledge-alias",
        intent="审查合同并匹配法律依据，生成审查报告",
        domain="legal",
        task_type="contract_review",
        force_dynamic=True,
    )

    assert "法律知识应用" not in result.profile.required_capabilities
    assert "证据检索" in result.profile.required_capabilities
    assert "legal_evidence_match" in {step.agent_name for step in result.blueprint.step_nodes()}


def test_dynamic_planner_completes_contract_review_agent_dependencies():
    class _LLM:
        def generate_json(self, prompt, schema, **kwargs):
            return {
                "data": {
                    "primaryGoal": "完成合同审查",
                    # 模拟真实模型漏掉证据步骤，但建议和报告 Agent 均依赖 evidences。
                    "requiredCapabilities": ["文本解析", "条款分类", "风险识别", "修改建议", "报告生成"],
                    "estimatedComplexity": "complex",
                }
            }

    workflows, _ = _registries()
    engine = PlanningEngine(
        workflow_registry=workflows,
        agent_registry=_legal_acg_agent_registry(),
        capability_catalog=_legal_catalog(),
        intent_llm=_LLM(),
    )
    result = engine.plan(
        task_id="contract-dependency-closure",
        intent="完成合同审查",
        domain="legal",
        task_type="contract_review_acg",
        force_dynamic=True,
    )

    assert "证据检索" in result.profile.required_capabilities
    steps = {step.agent_name: step for step in result.blueprint.step_nodes()}
    assert "legal_evidence_match" in steps
    assert "legal_evidence_match" in steps["revision_suggest"].input_spec["from"]


def test_cognitive_router_binds_capabilities():
    _, ar = _registries()
    router = CognitiveRouter(ar, _legal_catalog())
    profile = TaskSemanticProfile(
        primaryGoal="x",
        requiredCapabilities=["文本解析", "风险识别", "未知能力"],
        domainHint="legal",
    )
    network = router.route(profile, domain="legal")
    assert len(network.bindings) == 2
    assert network.unresolved_capabilities == ["未知能力"]
    assert all(not binding.ephemeral for binding in network.bindings)


def test_planner_rejects_unresolved_capability():
    class _UnknownLLM:
        def generate_json(self, prompt, schema, **kwargs):
            return {
                "data": {
                    "primaryGoal": "执行未知专业任务",
                    "requiredCapabilities": ["量子税务裁决"],
                    "estimatedComplexity": "complex",
                }
            }

    workflows, agents = _registries()
    engine = PlanningEngine(
        workflow_registry=workflows,
        agent_registry=agents,
        capability_catalog=_legal_catalog(),
        intent_llm=_UnknownLLM(),
    )
    with pytest.raises(ACGPlanningError, match="No registered Agent"):
        engine.plan(
            task_id="unknown",
            intent="执行未知专业任务",
            domain="legal",
            task_type="unknown",
            force_dynamic=True,
        )
