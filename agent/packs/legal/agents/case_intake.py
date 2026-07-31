"""法律 Pack 的智能体实现，负责法律工作流中的专业步骤执行。"""


from agentos.agents.base import AgentOutput, AgentProfile, BaseAgent
from packs.legal.agents.common import case_text


class CaseIntakeAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            AgentProfile(
                agentName="case_intake",
                domain="legal",
                capabilities=["case_intake", "fact_extraction"],
                allowedSkills=["case_understanding"],
                description="Extracts facts, issues, and missing information from legal task input.",
            )
        )

    async def run(self, context):
        text = case_text(context.task.input) or context.task.title
        output = {
            "case_summary": text[:300],
            "case_type": "",
            "parties": [],
            "legal_issues": [],
            "claims": [],
            "missing_info": [],
            "analysis_status": "unavailable",
        }
        return AgentOutput(output=output, summary="Case intake completed.")
