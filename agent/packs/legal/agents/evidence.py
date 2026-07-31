"""法律 Pack 的智能体实现，负责法律工作流中的专业步骤执行。"""


from agentos.agents.base import AgentOutput, AgentProfile, BaseAgent
from packs.legal.agents.common import case_text


class EvidenceAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            AgentProfile(
                agentName="evidence",
                domain="legal",
                capabilities=["evidence_analysis"],
                allowedSkills=["evidence_analysis"],
                description="Assesses evidence strength and missing materials.",
            )
        )

    async def run(self, context):
        text = case_text(context.task.input)
        output = {
            "evidence_items": [],
            "missing_evidence": [],
            "overall_assessment": "",
            "source_preview": text[:120],
            "analysis_status": "unavailable",
        }
        return AgentOutput(output=output, summary="No evidence assessment was generated.")
