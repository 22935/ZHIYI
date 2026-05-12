import asyncio
import json
import logging
from typing import Any, Dict, List

from app.agent_core.schema.agent_types import SkillRequest, SkillResult
from app.agent_core.skills.base import BaseSkill
from app.agent_core.skills.programmer.common import ProgrammerSkillHelper
from app.services.aiservice import AIService

logger = logging.getLogger(__name__)


class CodeGenerationSkill(BaseSkill):
    def __init__(self, ai_service: AIService = None):
        super().__init__("code_generation")
        self.ai_service = ai_service or AIService()

    def _fallback_output(
        self,
        specification: Dict[str, Any],
        target_language: str,
        context_hits: List[Dict[str, Any]],
        reason: str,
    ) -> Dict[str, Any]:
        language = target_language or "python"
        code = (
            "def handle_request(payload):\n"
            "    if payload is None:\n"
            "        raise ValueError('payload is required')\n"
            "    return {'success': True, 'data': payload}\n"
        )
        if language.lower() in {"java"}:
            code = (
                "public class Handler {\n"
                "    public Map<String, Object> handleRequest(Map<String, Object> payload) {\n"
                "        if (payload == null) {\n"
                "            throw new IllegalArgumentException(\"payload is required\");\n"
                "        }\n"
                "        Map<String, Object> result = new HashMap<>();\n"
                "        result.put(\"success\", true);\n"
                "        result.put(\"data\", payload);\n"
                "        return result;\n"
                "    }\n"
                "}\n"
            )

        return {
            "target_language": language,
            "code": code,
            "explanation": "模型结果不可用，已返回降级代码。",
            "suggested_tests": [
                "校验空输入与异常输入行为。",
                "校验成功响应结构与字段完整性。",
            ],
            "context_refs": [
                {
                    "file_path": item.get("file_path"),
                    "function_name": item.get("function_name"),
                    "class_name": item.get("class_name"),
                    "score": item.get("score"),
                }
                for item in (context_hits or [])[:5]
            ],
            "specification": specification,
            "fallback_reason": reason,
        }

    def _resolve_spec(self, request: SkillRequest) -> Dict[str, Any]:
        action_input = request.action_input or {}
        specification = action_input.get("specification")
        if isinstance(specification, dict):
            return specification

        observations = request.memory.get("observations", {})
        if isinstance(observations, dict):
            requirement_payload = observations.get("requirement_analysis")
            if isinstance(requirement_payload, dict):
                return requirement_payload

        return {"requirement": request.text or ""}

    def _resolve_context_hits(self, request: SkillRequest) -> List[Dict[str, Any]]:
        action_input = request.action_input or {}
        direct = action_input.get("context_hits")
        if isinstance(direct, list):
            return [item for item in direct if isinstance(item, dict)]

        observations = request.memory.get("observations", {})
        if isinstance(observations, dict):
            search_payload = observations.get("codebase_semantic_search")
            if isinstance(search_payload, dict):
                hits = search_payload.get("hits")
                if isinstance(hits, list):
                    return [item for item in hits if isinstance(item, dict)]
        return []

    async def execute(self, request: SkillRequest) -> SkillResult:
        action_input = request.action_input or {}
        target_language = str(action_input.get("target_language", "python")).strip() or "python"
        include_diagram = bool(action_input.get("include_diagram", False))
        specification = self._resolve_spec(request)
        context_hits = self._resolve_context_hits(request)

        context_text = ProgrammerSkillHelper.compact_code_context(context_hits, max_items=5)
        prompt = ProgrammerSkillHelper.load_prompt(
            "code_generation.txt",
            (
                "你是一名资深软件工程师，请始终使用简体中文说明（代码与 JSON 键名保持原样）。\n"
                "请根据规格与代码上下文生成实现代码。\n"
                "返回严格 JSON，键为：code, explanation, suggested_tests, mermaid_code(optional)。\n"
                "目标语言：{target_language}\n"
                "是否包含图示：{include_diagram}\n"
                "规格：\n{specification}\n\n"
                "代码上下文：\n{code_context}\n"
            ),
        )
        prompt = prompt.replace("{target_language}", target_language)
        prompt = prompt.replace("{include_diagram}", str(include_diagram).lower())
        prompt = prompt.replace("{specification}", json.dumps(specification, ensure_ascii=False))
        prompt = prompt.replace("{code_context}", context_text)

        llm_json: Dict[str, Any] = {}
        try:
            llm_response = await self.ai_service.generate_text(
                text=prompt,
                context=request.memory.get("history", [])[-8:],
            )
            raw_text = llm_response.get("text", "")
            llm_json = ProgrammerSkillHelper.extract_json_obj(raw_text)
            if not llm_json:
                # plain code fallback
                llm_json = {"code": (raw_text or "").strip()}
        except Exception as exc:
            logger.warning("CodeGenerationSkill LLM call failed: %s", exc)

        output = self._fallback_output(
            specification=specification,
            target_language=target_language,
            context_hits=context_hits,
            reason="llm_unavailable",
        )
        if llm_json:
            output = ProgrammerSkillHelper.merge_fallback_json(output, llm_json)

        output["target_language"] = target_language
        output["context_refs"] = [
            {
                "file_path": item.get("file_path"),
                "function_name": item.get("function_name"),
                "class_name": item.get("class_name"),
                "score": item.get("score"),
            }
            for item in (context_hits or [])[:5]
        ]

        return SkillResult(
            skillName=self.name,
            success=True,
            output=output,
            message="代码生成完成。",
        )

    async def run(self, request: SkillRequest) -> SkillResult:
        specification = self._resolve_spec(request)
        target_language = str((request.action_input or {}).get("target_language", "python")).strip() or "python"
        context_hits = self._resolve_context_hits(request)
        try:
            return await asyncio.wait_for(self.execute(request), timeout=45)
        except asyncio.TimeoutError:
            return SkillResult(
                skillName=self.name,
                success=True,
                output=self._fallback_output(
                    specification=specification,
                    target_language=target_language,
                    context_hits=context_hits,
                    reason="timeout",
                ),
                message="代码生成超时，已返回降级结果。",
            )
        except Exception as exc:
            logger.error("CodeGenerationSkill failed: %s", exc, exc_info=True)
            return SkillResult(
                skillName=self.name,
                success=True,
                output=self._fallback_output(
                    specification=specification,
                    target_language=target_language,
                    context_hits=context_hits,
                    reason="error",
                ),
                message="代码生成执行异常，已返回降级结果。",
            )
