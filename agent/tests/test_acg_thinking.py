from types import SimpleNamespace

from agentos.core.planning.default_catalog import build_default_capability_catalog
from agentos.core.planning.intent_parser import IntentParser
from packs.legal.agents import contract_review_migration as contract_agents
from packs.legal.planning import register_legal_capabilities


class _IntentLLM:
    def __init__(self):
        self.kwargs = None

    def generate_json(self, prompt, schema, **kwargs):
        self.kwargs = kwargs
        return {
            "data": {
                "primaryGoal": "完成合同风险审查",
                "requiredCapabilities": ["风险识别"],
                "estimatedComplexity": "complex",
            }
        }


def test_acg_planner_forwards_thinking_mode_to_intent_llm():
    llm = _IntentLLM()
    catalog = build_default_capability_catalog()
    register_legal_capabilities(catalog)

    profile = IntentParser(llm, catalog).parse(
        intent="审查合同风险并生成报告",
        domain="legal",
        task_type="contract_review_acg",
        thinking_mode="deep",
    )

    assert profile.primary_goal == "完成合同风险审查"
    assert llm.kwargs == {"thinking_mode": "deep"}


def test_contract_review_llm_helper_preserves_run_thinking_mode(monkeypatch):
    captured = {}

    class _Gateway:
        provider_name = "test"
        model = "test-model"

        def generate_json(self, prompt, schema, **kwargs):
            captured.update(kwargs)
            return {"data": {"ok": True}}

    monkeypatch.setattr(contract_agents, "get_llm_gateway", lambda: _Gateway())
    context = SimpleNamespace(task=SimpleNamespace(input={"thinkingMode": "deep"}))
    output, metadata = contract_agents._llm_json_or_fallback(
        node_name="test",
        prompt="test",
        schema={"type": "object"},
        fallback={},
        validator=lambda data: data,
        thinking_mode=contract_agents._thinking_mode(context),
    )

    assert output == {"ok": True}
    assert captured == {"thinking_mode": "deep"}
    assert metadata["thinking_mode"] == "deep"
