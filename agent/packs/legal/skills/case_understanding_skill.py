"""法律 Pack 的技能实现，提供案情、法条、证据、风险和文书相关原子能力。"""


import asyncio
import json
import logging
import re
from typing import Any, Dict, List

from agentos.core.models.types import SkillRequest, SkillResult
from agentos.skills.base import BaseSkill
from agentos.adapters.model_adapter import AIService
from agentos.packs.registry import pack_path

logger = logging.getLogger(__name__)

_ai_service = AIService()


class CaseUnderstandingSkill(BaseSkill):
    def __init__(self):
        super().__init__("case_understanding")
        self.prompt_path = pack_path("legal", "prompts", "case_understanding.txt")

    def _load_prompt_template(self) -> str:
        if not self.prompt_path.exists():
            raise FileNotFoundError(f"Role prompt not found: {self.prompt_path}")
        return self.prompt_path.read_text(encoding="utf-8", errors="ignore")

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

    @staticmethod
    def _unavailable(user_text: str) -> Dict[str, Any]:
        return {
            "parties": [],
            "facts": user_text.strip()[:400],
            "claims": [],
            "legal_issues": [],
            "missing_info": [],
            "case_type": "",
            "analysis_status": "unavailable",
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
                return SkillResult(
                    skillName=self.name,
                    success=False,
                    output=self._unavailable(user_text),
                    message="Case understanding returned no valid structured result.",
                )

            result = {
                "parties": self._ensure_list(parsed.get("parties")),
                "facts": str(parsed.get("facts", "")).strip() or user_text[:300],
                "claims": self._ensure_list(parsed.get("claims")),
                "legal_issues": self._ensure_list(parsed.get("legal_issues")),
                "missing_info": self._ensure_list(parsed.get("missing_info")),
                "case_type": str(parsed.get("case_type", "")).strip(),
            }

            return SkillResult(
                skillName=self.name,
                success=True,
                output=result,
                message="Case understanding extracted structured case summary.",
            )
        except asyncio.TimeoutError:
            logger.warning("CaseUnderstandingSkill timeout.")
            return SkillResult(
                skillName=self.name,
                success=False,
                output=self._unavailable(user_text),
                message="Case understanding timed out.",
            )
        except Exception as exc:
            logger.error("CaseUnderstandingSkill failed. error=%s", exc, exc_info=True)
            return SkillResult(
                skillName=self.name,
                success=False,
                output=self._unavailable(user_text),
                message="Case understanding failed without a generated result.",
            )

