import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from app.agent_core.schema.agent_types import SkillRequest, SkillResult
from app.agent_core.skills.base import BaseSkill
from app.services.aiservice import AIService

logger = logging.getLogger(__name__)

_ai_service = AIService()


class DocumentGenerationSkill(BaseSkill):
    def __init__(self):
        super().__init__("document_generation")
        self.prompt_path = Path(__file__).resolve().parents[2] / "prompts" / "document_generation.txt"

    def _load_prompt_template(self) -> str:
        if self.prompt_path.exists():
            return self.prompt_path.read_text(encoding="utf-8", errors="ignore")
        return (
            "你是法律文书生成助手。根据案情结构、法条与判例，生成结构化文书草稿。"
            "请使用清晰标题和分段，结尾给出风险提示与待补充信息。\n"
            "文书类型：{document_type}\n"
            "案情结构：{case_understanding}\n"
            "法条证据：{statutes}\n"
            "判例证据：{cases}\n"
            "用户诉求：{user_text}\n"
        )

    def _detect_document_type(self, user_text: str, action_input: Dict[str, Any]) -> str:
        if action_input.get("draftType"):
            return str(action_input.get("draftType"))
        text = user_text or ""
        if "起诉状" in text:
            return "民事起诉状草稿"
        if "答辩" in text:
            return "答辩意见草稿"
        if "律师函" in text:
            return "律师函草稿"
        return "法律分析意见书"

    def _fallback_draft(
        self,
        document_type: str,
        case_understanding: Dict[str, Any],
        statutes: List[Dict[str, Any]],
        cases: List[Dict[str, Any]],
    ) -> str:
        facts = case_understanding.get("facts", "案情事实待补充。")
        claims = case_understanding.get("claims", [])
        legal_issues = case_understanding.get("legal_issues", [])
        missing_info = case_understanding.get("missing_info", [])

        statute_lines = [
            f"- {item.get('lawName', '')} {item.get('article', '')} {item.get('title', '')}".strip()
            for item in statutes[:3]
        ]
        case_lines = [
            f"- {item.get('title', '')} {item.get('caseNo', '')} {item.get('court', '')}".strip()
            for item in cases[:3]
        ]

        return (
            f"# {document_type}\n\n"
            "## 一、案情概要\n"
            f"{facts}\n\n"
            "## 二、主要诉求\n"
            f"{json.dumps(claims, ensure_ascii=False)}\n\n"
            "## 三、争议焦点\n"
            f"{json.dumps(legal_issues, ensure_ascii=False)}\n\n"
            "## 四、参考法条\n"
            f"{chr(10).join(statute_lines) if statute_lines else '- 暂无法条命中'}\n\n"
            "## 五、参考判例\n"
            f"{chr(10).join(case_lines) if case_lines else '- 暂无判例命中'}\n\n"
            "## 六、风险提示\n"
            f"待补充信息：{json.dumps(missing_info, ensure_ascii=False)}\n"
        )

    async def run(self, request: SkillRequest) -> SkillResult:
        observations = request.memory.get("observations", {}) if isinstance(request.memory, dict) else {}
        case_understanding = observations.get("case_understanding", {})
        statutes = observations.get("statute_retrieval", {}).get("statutes", [])
        cases = observations.get("case_retrieval", {}).get("cases", [])
        document_type = self._detect_document_type(request.text, request.action_input)

        template = self._load_prompt_template()
        prompt = template.format(
            document_type=document_type,
            case_understanding=json.dumps(case_understanding, ensure_ascii=False),
            statutes=json.dumps(statutes[:5], ensure_ascii=False),
            cases=json.dumps(cases[:5], ensure_ascii=False),
            user_text=request.text,
        )

        try:
            llm_response = await asyncio.wait_for(_ai_service.generate_text(text=prompt), timeout=45)
            draft = (llm_response.get("text", "") or "").strip()
            if not draft:
                draft = self._fallback_draft(document_type, case_understanding, statutes, cases)

            output = {
                "document_type": document_type,
                "draft": draft,
                "sections": ["案情概要", "主要诉求", "争议焦点", "法律依据", "风险提示"],
                "references": {
                    "statutes": statutes[:5],
                    "cases": cases[:5],
                },
            }
            return SkillResult(
                skillName=self.name,
                success=True,
                output=output,
                message="Document draft generated.",
            )
        except Exception as exc:
            logger.warning("DocumentGenerationSkill fallback used. error=%s", exc)
            output = {
                "document_type": document_type,
                "draft": self._fallback_draft(document_type, case_understanding, statutes, cases),
                "sections": ["案情概要", "主要诉求", "争议焦点", "法律依据", "风险提示"],
                "references": {
                    "statutes": statutes[:5],
                    "cases": cases[:5],
                },
            }
            return SkillResult(
                skillName=self.name,
                success=True,
                output=output,
                message="Document generation fallback output returned.",
            )

