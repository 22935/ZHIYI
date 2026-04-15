from typing import Dict, List

from app.agent_core.schema.agent_types import PlannedAction


class ReactPlanner:
    """Intent-aware ReAct planner for lawyer-agent workflow."""

    def __init__(self, max_plan_steps: int = 10):
        self.max_plan_steps = max_plan_steps

    def _contains_any(self, text: str, tokens: List[str]) -> bool:
        raw = text or ""
        lowered = raw.lower()
        return any(token in raw for token in tokens) or any(token in lowered for token in tokens)

    def plan(self, text: str, history: List[Dict[str, str]]) -> List[PlannedAction]:
        actions: List[PlannedAction] = []
        added = set()

        def add_action(thought: str, action: str, action_input: Dict[str, object]) -> None:
            if action in added:
                return
            added.add(action)
            actions.append(
                PlannedAction(
                    thought=thought,
                    action=action,
                    actionInput=action_input,
                )
            )

        evidence_tokens = ["证据", "微信", "转账", "录音", "证人", "证明力", "举证", "evidence", "proof"]
        limitation_tokens = ["时效", "还能起诉", "过期", "截止", "仲裁时效", "limitation", "deadline"]
        jurisdiction_tokens = ["管辖", "哪个法院", "在哪里起诉", "法院", "被告在", "履行地", "jurisdiction", "court"]
        hearing_tokens = ["开庭", "庭审", "提纲", "发问", "质证", "辩论", "hearing", "trial"]
        drafting_tokens = ["文书", "起诉状", "答辩状", "律师函", "草稿", "draft", "template"]

        needs_evidence = self._contains_any(text, evidence_tokens)
        needs_limitation = self._contains_any(text, limitation_tokens)
        needs_jurisdiction = self._contains_any(text, jurisdiction_tokens)
        needs_hearing = self._contains_any(text, hearing_tokens)
        needs_document = self._contains_any(text, drafting_tokens)

        add_action(
            thought="先做案情结构化，明确当事人、事实和争议焦点。",
            action="case_understanding",
            action_input={"historySize": len(history)},
        )

        add_action(
            thought="检索法条为后续分析提供法律依据。",
            action="statute_retrieval",
            action_input={"query": text, "top_k": 5},
        )

        add_action(
            thought="检索同类判例补充裁判思路和风险边界。",
            action="case_retrieval",
            action_input={"query": text, "top_k": 5},
        )

        if needs_evidence or needs_hearing:
            add_action(
                thought="用户涉及证据问题，先进行证据链分析。",
                action="evidence_analysis",
                action_input={"query": text},
            )

        if needs_limitation:
            add_action(
                thought="用户关注时间窗口，计算诉讼/仲裁时效。",
                action="limitation_calculation",
                action_input={"query": text},
            )

        if needs_jurisdiction:
            add_action(
                thought="用户关注立案地点，确定可能有管辖权的法院。",
                action="jurisdiction_determination",
                action_input={"query": text},
            )

        if needs_hearing:
            add_action(
                thought="用户准备开庭，生成庭审提纲。",
                action="hearing_outline_generation",
                action_input={"outlineType": "trial_preparation"},
            )

        if needs_document:
            add_action(
                thought="用户请求法律文书，生成结构化文书草稿。",
                action="document_generation",
                action_input={"draftType": "general"},
            )

        add_action(
            thought="最后综合事实、证据、时效和程序因素进行风险评估。",
            action="risk_assessment",
            action_input={"mode": "baseline"},
        )

        return actions[: self.max_plan_steps]
