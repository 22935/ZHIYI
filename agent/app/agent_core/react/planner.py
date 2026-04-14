from typing import Dict, List

from app.agent_core.schema.agent_types import PlannedAction


class ReactPlanner:
    """ReAct planner for lawyer-agent workflow."""

    def __init__(self, max_plan_steps: int = 6):
        self.max_plan_steps = max_plan_steps

    def plan(self, text: str, history: List[Dict[str, str]]) -> List[PlannedAction]:
        actions: List[PlannedAction] = [
            PlannedAction(
                thought="First understand case facts and legal issues.",
                action="case_understanding",
                actionInput={"historySize": len(history)},
            ),
            PlannedAction(
                thought="Retrieve relevant statutes for legal basis.",
                action="statute_retrieval",
                actionInput={"query": text, "top_k": 5},
            ),
            PlannedAction(
                thought="Retrieve similar cases for reference.",
                action="case_retrieval",
                actionInput={"query": text, "top_k": 5},
            ),
        ]

        lowered = (text or "").lower()
        drafting_tokens_zh = [
            "\u6587\u4e66",      # 文书
            "\u8d77\u8bc9\u72b6",  # 起诉状
            "\u7b54\u8fa9\u72b6",  # 答辩状
            "\u5f8b\u5e08\u51fd",  # 律师函
            "\u8bc9\u72b6",      # 诉状
            "\u8349\u7a3f",      # 草稿
            "\u5199\u4e00\u4efd",  # 写一份
        ]
        drafting_tokens_en = ["draft", "template", "complaint", "petition"]

        if any(token in text for token in drafting_tokens_zh) or any(token in lowered for token in drafting_tokens_en):
            actions.append(
                PlannedAction(
                    thought="Generate legal document draft if requested.",
                    action="document_generation",
                    actionInput={"draftType": "general"},
                )
            )

        # Always provide risk assessment in lawyer workflow.
        actions.append(
            PlannedAction(
                thought="Assess legal and evidence risks.",
                action="risk_assessment",
                actionInput={"mode": "baseline"},
            )
        )

        return actions[: self.max_plan_steps]
