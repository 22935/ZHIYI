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


class HearingOutlineGenerationSkill(BaseSkill):
    def __init__(self):
        super().__init__("hearing_outline_generation")
        self.prompt_path = Path(__file__).resolve().parents[2] / "prompts" / "hearing_outline_generation.txt"

    def _load_template(self) -> str:
        if self.prompt_path.exists():
            return self.prompt_path.read_text(encoding="utf-8", errors="ignore")
        return (
            "你是律师庭审准备助手。基于给定案情和证据，输出庭审提纲，包含："
            "开场主张、法官可能关注问题、对被告发问清单、举证质证要点、法庭辩论要点、庭后补充材料。"
            "要求条理清晰，编号输出。\n"
            "用户问题: {user_text}\n案情结构: {case_info}\n证据分析: {evidence}\n法条依据: {statutes}\n风险评估: {risk}\n"
        )

    def _fallback_outline(
        self,
        user_text: str,
        case_info: Dict[str, Any],
        evidence: Dict[str, Any],
        statutes: List[Dict[str, Any]],
        risk: Dict[str, Any],
    ) -> str:
        legal_issues = case_info.get("legal_issues", [])
        evidence_items = evidence.get("evidence_items", [])
        missing = evidence.get("missing_evidence", [])
        statute_titles = [f"{item.get('lawName', '')}{item.get('article', '')}" for item in statutes[:3]]

        return (
            "一、开庭目标与核心请求\n"
            f"1. 围绕争议焦点：{json.dumps(legal_issues, ensure_ascii=False)}。\n"
            "2. 先明确请求，再展示证据链。\n\n"
            "二、发问提纲（对方/证人）\n"
            "1. 确认法律关系成立时间、履行过程、违约节点。\n"
            "2. 确认关键事实中的时间、金额、沟通记录。\n"
            "3. 针对抗辩理由逐项发问并要求对方举证。\n\n"
            "三、举证与质证要点\n"
            f"1. 现有证据：{json.dumps(evidence_items, ensure_ascii=False)}。\n"
            f"2. 待补证据：{json.dumps(missing, ensure_ascii=False)}。\n"
            "3. 对电子数据重点说明来源、完整性、关联性和合法性。\n\n"
            "四、法庭辩论主线\n"
            f"1. 主要法律依据：{json.dumps(statute_titles, ensure_ascii=False)}。\n"
            "2. 先事实后法律，再回应对方抗辩。\n"
            f"3. 风险提示：当前风险等级 {risk.get('risk_level', 'unknown')}。\n\n"
            "五、庭后补充清单\n"
            "1. 补充书证原件与电子数据原始载体。\n"
            "2. 补充时间线对照表与证据目录。\n"
            "3. 形成书面代理意见用于庭后提交。"
        )

    async def run(self, request: SkillRequest) -> SkillResult:
        try:
            return await asyncio.wait_for(self._run_impl(request), timeout=45)
        except asyncio.TimeoutError:
            return SkillResult(
                skillName=self.name,
                success=True,
                output={
                    "outline": "庭审提纲生成超时，请稍后重试。",
                    "agenda": [],
                    "question_points": [],
                    "risk_focus": [],
                },
                message="Hearing outline generation timeout, fallback returned.",
            )
        except Exception as exc:
            logger.warning("HearingOutlineGenerationSkill failed: %s", exc, exc_info=True)
            return SkillResult(
                skillName=self.name,
                success=True,
                output={
                    "outline": "庭审提纲生成失败，请补充案情后重试。",
                    "agenda": [],
                    "question_points": [],
                    "risk_focus": [],
                },
                message="Hearing outline generation fallback returned.",
            )

    async def _run_impl(self, request: SkillRequest) -> SkillResult:
        observations = request.memory.get("observations", {}) if isinstance(request.memory, dict) else {}
        case_info = observations.get("case_understanding", {})
        evidence = observations.get("evidence_analysis", {})
        statutes = observations.get("statute_retrieval", {}).get("statutes", [])
        risk = observations.get("risk_assessment", {})

        template = self._load_template()
        prompt = template.format(
            user_text=request.text,
            case_info=json.dumps(case_info, ensure_ascii=False),
            evidence=json.dumps(evidence, ensure_ascii=False),
            statutes=json.dumps(statutes[:5], ensure_ascii=False),
            risk=json.dumps(risk, ensure_ascii=False),
        )

        draft = ""
        try:
            response = await asyncio.wait_for(_ai_service.generate_text(text=prompt), timeout=45)
            draft = (response.get("text", "") or "").strip()
        except Exception:
            draft = ""

        if not draft:
            draft = self._fallback_outline(
                user_text=request.text,
                case_info=case_info if isinstance(case_info, dict) else {},
                evidence=evidence if isinstance(evidence, dict) else {},
                statutes=statutes if isinstance(statutes, list) else [],
                risk=risk if isinstance(risk, dict) else {},
            )

        output = {
            "outline": draft,
            "agenda": ["开场主张", "发问提纲", "举证质证", "法庭辩论", "庭后补充"],
            "question_points": [
                "对方对关键事实是否认可",
                "对方抗辩是否有证据支撑",
                "证据取得与保存过程是否完整",
            ],
            "risk_focus": (risk or {}).get("key_risks", []),
        }
        return SkillResult(
            skillName=self.name,
            success=True,
            output=output,
            message="Hearing outline generated.",
        )
