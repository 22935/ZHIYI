import json
from typing import Any, Dict, List, Tuple

from app.agent_core.react.tool_router import ToolRouter
from app.agent_core.schema.agent_types import (
    AgentTraceStep,
    PlannedAction,
    SkillRequest,
)


class ReactExecutor:
    """Executes ReAct plan loop and collects trace."""

    def __init__(self, tool_router: ToolRouter, max_steps: int = 10):
        self.tool_router = tool_router
        self.max_steps = max_steps

    async def execute(
        self,
        plan: List[PlannedAction],
        session_id: str,
        text: str,
        memory: Dict[str, object],
    ) -> Tuple[List[AgentTraceStep], List[str], Dict[str, object]]:
        trace: List[AgentTraceStep] = []
        skills_used: List[str] = []
        observations: Dict[str, object] = {}
        current_memory: Dict[str, Any] = dict(memory)
        current_memory.setdefault("observations", {})

        for index, action in enumerate(plan[: self.max_steps], start=1):
            request = SkillRequest(
                sessionId=session_id,
                text=text,
                actionInput=action.action_input,
                memory=current_memory,
            )
            result = await self.tool_router.run(action, request)

            if action.action not in skills_used:
                skills_used.append(action.action)
            observations[action.action] = result.output
            current_memory["observations"][action.action] = result.output
            current_memory[action.action] = result.output

            observation_text = result.message or json.dumps(result.output, ensure_ascii=False)
            trace.append(
                AgentTraceStep(
                    step=index,
                    thought=action.thought,
                    action=action.action,
                    observation=observation_text,
                )
            )

        return trace, skills_used, observations
