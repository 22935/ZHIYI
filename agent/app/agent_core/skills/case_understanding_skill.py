import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List

from app.agent_core.schema.agent_types import SkillRequest, SkillResult
from app.agent_core.skills.base import BaseSkill
from app.services.aiservice import AIService

logger = logging.getLogger(__name__)

_ai_service = AIService()


class CaseUnderstandingSkill(BaseSkill):
    def __init__(self):
        super().__init__("case_understanding")
        self.prompt_path = Path(__file__).resolve().parents[2] / "prompts" / "case_understanding.txt"

    def _load_prompt_template(self) -> str:
        if self.prompt_path.exists():
            return self.prompt_path.read_text(encoding="utf-8", errors="ignore")
        return (
            "你是法律案情结构化助手。请从给定输入中提取标准 JSON，字段必须包含："
            "parties, facts, claims, legal_issues, missing_info, case_type。仅输出 JSON。"
            "\n历史：{history_text}\n用户问题：{user_text}\n"
        )

    def _render_prompt(self, template: str, history_text: str, user_text: str) -> str:
        # Avoid str.format collisions with literal JSON braces in prompt templates.
        prompt = template.replace("{history_text}", history_text)
        prompt = prompt.replace("{user_text}", user_text)
        return prompt

    def _extract_json_obj(self, text: str) -> Dict[str, Any]:
        text = (text or "").strip()
        if not text:
            return {}

        try:
            value = json.loads(text)
            if isinstance(value, dict):
                return value
        except Exception:
            pass

        fenced_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, flags=re.IGNORECASE)
        if fenced_match:
            try:
                value = json.loads(fenced_match.group(1))
                if isinstance(value, dict):
                    return value
            except Exception:
                pass

        obj_match = re.search(r"(\{[\s\S]*\})", text)
        if obj_match:
            try:
                value = json.loads(obj_match.group(1))
                if isinstance(value, dict):
                    return value
            except Exception:
                pass

        return {}

    def _ensure_list(self, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            parts = re.split(r"[，,；;、\n]", value)
            return [part.strip() for part in parts if part.strip()]
        return [str(value).strip()] if str(value).strip() else []

    def _infer_case_type(self, user_text: str) -> str:
        text = user_text or ""
        if ("劳动" in text) or ("用工" in text):
            return "劳动争议"
        if ("合同" in text) or ("违约" in text):
            return "合同纠纷"
        if ("侵权" in text) or ("赔偿" in text):
            return "侵权纠纷"
        if ("著作权" in text) or ("商标" in text) or ("专利" in text):
            return "知识产权纠纷"
        return "民商事争议"

    def _fallback(self, user_text: str, history: List[Dict[str, str]]) -> Dict[str, Any]:
        legal_issues = []
        if "劳动" in user_text:
            legal_issues.append("劳动关系认定")
        if "合同" in user_text:
            legal_issues.append("合同履行与违约")
        if "赔偿" in user_text:
            legal_issues.append("损害赔偿责任")
        if not legal_issues:
            legal_issues = ["争议事实待核实", "适用法律待检索"]

        facts = user_text.strip()
        if history:
            recent = " ".join(item.get("content", "") for item in history[-3:])
            if recent:
                facts = f"{facts} 历史补充：{recent[:180]}".strip()

        return {
            "parties": ["待明确当事人双方"],
            "facts": facts[:400] if facts else "用户暂未提供充分案情。",
            "claims": ["待明确诉求"],
            "legal_issues": legal_issues,
            "missing_info": ["是否签订合同", "关键时间线", "证据材料完整性"],
            "case_type": self._infer_case_type(user_text),
        }

    async def run(self, request: SkillRequest) -> SkillResult:
        history = request.memory.get("history", []) if isinstance(request.memory, dict) else []
        history_text = "\n".join(
            f"{item.get('role', 'unknown')}: {item.get('content', '')}" for item in history[-8:]
        )
        user_text = request.text or ""

        template = self._load_prompt_template()
        prompt = self._render_prompt(template, history_text or "无", user_text)

        try:
            llm_response = await asyncio.wait_for(
                _ai_service.generate_text(text=prompt, context=history[-6:]),
                timeout=45,
            )
            raw = llm_response.get("text", "")
            parsed = self._extract_json_obj(raw)

            if not parsed:
                fallback = self._fallback(user_text, history)
                return SkillResult(
                    skillName=self.name,
                    success=True,
                    output=fallback,
                    message="Case understanding fallback used because LLM JSON parsing failed.",
                )

            result = {
                "parties": self._ensure_list(parsed.get("parties")) or ["待明确当事人双方"],
                "facts": str(parsed.get("facts", "")).strip() or user_text[:300] or "案情摘要待补充。",
                "claims": self._ensure_list(parsed.get("claims")) or ["待明确诉求"],
                "legal_issues": self._ensure_list(parsed.get("legal_issues")) or ["适用法律待分析"],
                "missing_info": self._ensure_list(parsed.get("missing_info")) or ["关键事实待补充"],
                "case_type": str(parsed.get("case_type", "")).strip() or self._infer_case_type(user_text),
            }

            return SkillResult(
                skillName=self.name,
                success=True,
                output=result,
                message="Case understanding extracted structured case summary.",
            )
        except asyncio.TimeoutError:
            logger.warning("CaseUnderstandingSkill timeout, using fallback.")
            return SkillResult(
                skillName=self.name,
                success=True,
                output=self._fallback(user_text, history),
                message="Case understanding timeout, fallback output returned.",
            )
        except Exception as exc:
            logger.error("CaseUnderstandingSkill failed, fallback used. error=%s", exc, exc_info=True)
            return SkillResult(
                skillName=self.name,
                success=True,
                output=self._fallback(user_text, history),
                message="Case understanding failed, fallback output returned.",
            )

