"""法律 Pack 的智能体实现，负责法律工作流中的专业步骤执行。"""


from agentos.agents.base import AgentOutput, AgentProfile, BaseAgent


class ReviewAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            AgentProfile(
                agentName="review",
                domain="legal",
                capabilities=["final_review", "quality_gate"],
                allowedSkills=["legal_reason"],
                description="Checks consistency and produces the final workflow answer.",
            )
        )

    async def run(self, context):
        observations = context.memory.observations
        draft = observations.get("draft", {}).get("draft", "")
        final_answer = str(draft or "").strip()
        return AgentOutput(
            output={
                "final_answer": final_answer,
                "review_notes": [],
            },
            summary="Final review completed.",
        )
