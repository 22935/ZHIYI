import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

from app.agent_core.retrieval.legal_index_builder import legal_index_builder
from app.agent_core.schema.agent_types import SkillRequest, SkillResult
from app.agent_core.skills.base import BaseSkill

logger = logging.getLogger(__name__)


class JurisdictionDeterminationSkill(BaseSkill):
    def __init__(self):
        super().__init__("jurisdiction_determination")

    def _extract_location(self, text: str, patterns: List[str]) -> Optional[str]:
        for pattern in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            location = match.group("loc").strip()
            if location:
                return location
        return None

    def _detect_case_type(self, text: str, case_info: Dict[str, Any]) -> str:
        merged = f"{text} {case_info.get('case_type', '')} {' '.join(case_info.get('legal_issues', []))}"
        if any(token in merged for token in ["劳动", "工资", "用人单位"]):
            return "劳动争议"
        if "侵权" in merged:
            return "侵权纠纷"
        if "合同" in merged:
            return "合同纠纷"
        return "一般民事"

    def _build_recommendations(
        self,
        case_type: str,
        plaintiff_loc: Optional[str],
        defendant_loc: Optional[str],
        contract_loc: Optional[str],
        tort_loc: Optional[str],
    ) -> List[Dict[str, Any]]:
        recommendations: List[Dict[str, Any]] = []

        if defendant_loc:
            recommendations.append(
                {
                    "court": f"{defendant_loc}有管辖权的基层人民法院",
                    "reason": "一般由被告住所地法院管辖",
                    "priority": "high",
                }
            )

        if case_type == "合同纠纷" and contract_loc:
            recommendations.append(
                {
                    "court": f"{contract_loc}有管辖权的基层人民法院",
                    "reason": "合同纠纷可由合同履行地法院管辖",
                    "priority": "high",
                }
            )

        if case_type == "侵权纠纷" and tort_loc:
            recommendations.append(
                {
                    "court": f"{tort_loc}有管辖权的基层人民法院",
                    "reason": "侵权纠纷可由侵权行为地法院管辖",
                    "priority": "high",
                }
            )

        if case_type == "劳动争议":
            if contract_loc:
                recommendations.append(
                    {
                        "court": f"{contract_loc}有管辖权的基层人民法院",
                        "reason": "劳动争议诉讼通常可由劳动合同履行地法院受理（仲裁后起诉）",
                        "priority": "medium",
                    }
                )
            if defendant_loc:
                recommendations.append(
                    {
                        "court": f"{defendant_loc}有管辖权的基层人民法院",
                        "reason": "劳动争议也可由用人单位所在地法院受理（仲裁后起诉）",
                        "priority": "medium",
                    }
                )

        if not recommendations and plaintiff_loc:
            recommendations.append(
                {
                    "court": f"{plaintiff_loc}附近具管辖权法院（待补充案由与被告地）",
                    "reason": "当前关键信息不足，先给出近端备选",
                    "priority": "low",
                }
            )

        dedup = []
        seen = set()
        for item in recommendations:
            key = f"{item['court']}|{item['reason']}"
            if key in seen:
                continue
            seen.add(key)
            dedup.append(item)
        return dedup[:4]

    async def run(self, request: SkillRequest) -> SkillResult:
        try:
            return await asyncio.wait_for(self._run_impl(request), timeout=8)
        except asyncio.TimeoutError:
            return SkillResult(
                skillName=self.name,
                success=True,
                output={
                    "case_type": "未知",
                    "detected_locations": {},
                    "recommended_courts": [],
                    "legal_basis": [],
                    "notes": ["管辖分析超时，请补充被告住所地、合同履行地后重试。"],
                },
                message="Jurisdiction determination timeout, fallback returned.",
            )
        except Exception as exc:
            logger.warning("JurisdictionDeterminationSkill failed: %s", exc, exc_info=True)
            return SkillResult(
                skillName=self.name,
                success=True,
                output={
                    "case_type": "未知",
                    "detected_locations": {},
                    "recommended_courts": [],
                    "legal_basis": [],
                    "notes": ["管辖分析失败，请由律师人工确认具体法院。"],
                },
                message="Jurisdiction determination fallback returned.",
            )

    async def _run_impl(self, request: SkillRequest) -> SkillResult:
        observations = request.memory.get("observations", {}) if isinstance(request.memory, dict) else {}
        case_info = observations.get("case_understanding", {}) if isinstance(observations, dict) else {}
        text = request.text or ""

        plaintiff_loc = self._extract_location(
            text,
            [
                r"(?:我|原告)[^，。；,]{0,8}(?:在|位于|住在)(?P<loc>[\u4e00-\u9fa5]{2,12})",
                r"(?:我在)(?P<loc>[\u4e00-\u9fa5]{2,12})",
            ],
        )
        defendant_loc = self._extract_location(
            text,
            [
                r"(?:被告|对方|公司|单位)[^，。；,]{0,10}(?:在|位于|住所地在)(?P<loc>[\u4e00-\u9fa5]{2,12})",
                r"(?:被告在)(?P<loc>[\u4e00-\u9fa5]{2,12})",
            ],
        )
        contract_loc = self._extract_location(
            text,
            [r"(?:合同履行地|履行地|工作地|用工地)[^，。；,]{0,6}(?:在|为)(?P<loc>[\u4e00-\u9fa5]{2,12})"],
        )
        tort_loc = self._extract_location(
            text,
            [r"(?:侵权行为地|事故发生地|侵权地)[^，。；,]{0,6}(?:在|为)(?P<loc>[\u4e00-\u9fa5]{2,12})"],
        )

        case_type = self._detect_case_type(text=text, case_info=case_info)
        rules = legal_index_builder.search_jurisdiction_rules(query=f"{case_type} 管辖", top_k=5)
        legal_basis = []
        for row in rules:
            basis = str(row.get("metadata", {}).get("basis", "")).strip()
            if basis and basis not in legal_basis:
                legal_basis.append(basis)

        recommended = self._build_recommendations(
            case_type=case_type,
            plaintiff_loc=plaintiff_loc,
            defendant_loc=defendant_loc,
            contract_loc=contract_loc,
            tort_loc=tort_loc,
        )

        notes = []
        if case_type == "劳动争议":
            notes.append("劳动争议通常需要先仲裁后诉讼。")
        if not defendant_loc:
            notes.append("未识别到被告住所地，建议补充后可提高准确度。")
        if not recommended:
            notes.append("信息不足，建议至少补充被告住所地和案由。")

        output = {
            "case_type": case_type,
            "detected_locations": {
                "plaintiff_location": plaintiff_loc,
                "defendant_location": defendant_loc,
                "contract_or_work_location": contract_loc,
                "tort_location": tort_loc,
            },
            "recommended_courts": recommended,
            "legal_basis": legal_basis[:5],
            "notes": notes,
        }
        return SkillResult(
            skillName=self.name,
            success=True,
            output=output,
            message=f"Jurisdiction determination completed with {len(recommended)} option(s).",
        )
