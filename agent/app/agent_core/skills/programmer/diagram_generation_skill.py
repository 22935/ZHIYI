import asyncio
import json
import logging
from typing import Any, Dict

from app.agent_core.schema.agent_types import SkillRequest, SkillResult
from app.agent_core.skills.base import BaseSkill
from app.agent_core.skills.programmer.common import ProgrammerSkillHelper
from app.services.aiservice import AIService

logger = logging.getLogger(__name__)


class DiagramGenerationSkill(BaseSkill):
    def __init__(self, ai_service: AIService = None):
        super().__init__("diagram_generation")
        self.ai_service = ai_service or AIService()

    def _fallback_output(self, query: str, diagram_type: str, reason: str) -> Dict[str, Any]:
        normalized_type = diagram_type or "flowchart"
        return {
            "title": "Generated Diagram",
            "diagram_type": normalized_type,
            "mermaid_code": ProgrammerSkillHelper.default_mermaid(normalized_type),
            "source_query": query,
            "fallback_reason": reason,
        }

    async def execute(self, request: SkillRequest) -> SkillResult:
        action_input = request.action_input or {}
        diagram_type = str(action_input.get("diagram_type", "flowchart")).strip() or "flowchart"
        query = str(action_input.get("query", request.text or "")).strip()

        observations = request.memory.get("observations", {})
        code_context = ""
        if isinstance(observations, dict):
            search_payload = observations.get("codebase_semantic_search")
            if isinstance(search_payload, dict):
                code_context = ProgrammerSkillHelper.compact_code_context(
                    search_payload.get("hits", []),
                    max_items=4,
                )

        prompt = ProgrammerSkillHelper.load_prompt(
            "diagram_generation.txt",
            (
                "You are a software architect.\n"
                "Generate Mermaid diagram code from request and code context.\n"
                "Return strict JSON with keys: title, diagram_type, mermaid_code.\n"
                "Request: {query}\n"
                "Preferred diagram_type: {diagram_type}\n"
                "Code context:\n{code_context}\n"
            ),
        )
        prompt = prompt.replace("{query}", query)
        prompt = prompt.replace("{diagram_type}", diagram_type)
        prompt = prompt.replace("{code_context}", code_context)

        llm_json: Dict[str, Any] = {}
        mermaid_code = ""
        try:
            llm_response = await self.ai_service.generate_text(
                text=prompt,
                context=request.memory.get("history", [])[-8:],
            )
            raw_text = llm_response.get("text", "")
            llm_json = ProgrammerSkillHelper.extract_json_obj(raw_text)
            mermaid_code = ProgrammerSkillHelper.extract_mermaid_code(raw_text)
        except Exception as exc:
            logger.warning("DiagramGenerationSkill LLM call failed: %s", exc)

        output = self._fallback_output(query=query, diagram_type=diagram_type, reason="llm_unavailable")
        if llm_json:
            output = ProgrammerSkillHelper.merge_fallback_json(output, llm_json)
        if mermaid_code:
            output["mermaid_code"] = mermaid_code
        if not str(output.get("mermaid_code", "")).strip():
            output["mermaid_code"] = ProgrammerSkillHelper.default_mermaid(diagram_type)

        output["diagram_type"] = str(output.get("diagram_type", diagram_type)).strip() or diagram_type
        output["source_query"] = query

        return SkillResult(
            skillName=self.name,
            success=True,
            output=output,
            message="Diagram generation completed.",
        )

    async def run(self, request: SkillRequest) -> SkillResult:
        action_input = request.action_input or {}
        diagram_type = str(action_input.get("diagram_type", "flowchart")).strip() or "flowchart"
        query = str(action_input.get("query", request.text or "")).strip()
        try:
            return await asyncio.wait_for(self.execute(request), timeout=10)
        except asyncio.TimeoutError:
            return SkillResult(
                skillName=self.name,
                success=True,
                output=self._fallback_output(query=query, diagram_type=diagram_type, reason="timeout"),
                message="Diagram generation timeout, fallback returned.",
            )
        except Exception as exc:
            logger.error("DiagramGenerationSkill failed: %s", exc, exc_info=True)
            return SkillResult(
                skillName=self.name,
                success=True,
                output=self._fallback_output(query=query, diagram_type=diagram_type, reason="error"),
                message="Diagram generation error, fallback returned.",
            )
