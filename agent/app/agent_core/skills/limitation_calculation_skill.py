import asyncio
import datetime as dt
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.agent_core.retrieval.legal_index_builder import legal_index_builder
from app.agent_core.schema.agent_types import SkillRequest, SkillResult
from app.agent_core.skills.base import BaseSkill

logger = logging.getLogger(__name__)


class LimitationCalculationSkill(BaseSkill):
    def __init__(self):
        super().__init__("limitation_calculation")

    def _extract_date(self, text: str) -> Optional[dt.date]:
        text = text or ""
        patterns = [
            r"(?P<y>20\d{2})[-/年](?P<m>\d{1,2})[-/月](?P<d>\d{1,2})日?",
            r"(?P<y>20\d{2})[-/年](?P<m>\d{1,2})月",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            year = int(match.group("y"))
            month = int(match.group("m"))
            day = int(match.groupdict().get("d") or 1)
            try:
                return dt.date(year, month, day)
            except ValueError:
                continue
        return None

    def _detect_case_type(self, text: str, case_info: Dict[str, Any]) -> str:
        source = f"{text} {case_info.get('case_type', '')} {' '.join(case_info.get('legal_issues', []))}"
        if any(token in source for token in ["劳动", "工资", "用人单位", "劳动合同"]):
            return "劳动争议"
        if any(token in source for token in ["借款", "借条"]):
            return "民间借贷"
        if any(token in source for token in ["合同", "违约"]):
            return "合同纠纷"
        if any(token in source for token in ["侵权", "人身损害", "交通事故"]):
            return "侵权纠纷"
        return "一般民事"

    def _select_rule(self, rows: List[Dict[str, Any]], case_type: str) -> Tuple[int, List[str], str]:
        basis: List[str] = []
        years = None
        for row in rows:
            metadata = row.get("metadata", {})
            row_type = str(metadata.get("rule_type", ""))
            if metadata.get("basis"):
                basis.append(str(metadata.get("basis")))
            value = metadata.get("years")
            if isinstance(value, (int, float)) and int(value) > 0:
                if case_type in row_type or row_type in case_type:
                    years = int(value)
                    break
                years = years or int(value)

        default_years = 1 if case_type == "劳动争议" else 3
        final_years = years or default_years
        if not basis:
            basis = ["《民法典》第188条"]
            if final_years == 1:
                basis = ["《劳动争议调解仲裁法》第27条"]
        return final_years, basis[:3], case_type

    def _add_years(self, start: dt.date, years: int) -> dt.date:
        try:
            return start.replace(year=start.year + years)
        except ValueError:
            # Handle leap day.
            return start.replace(month=2, day=28, year=start.year + years)

    def _detect_interruptions(self, text: str) -> List[str]:
        hints = {
            "起诉": "已提起诉讼可能导致时效中断",
            "仲裁": "已申请仲裁可能导致时效中断",
            "催告": "催告并留痕可能导致时效中断",
            "承诺": "对方书面承诺履行可能导致时效中断",
            "调解": "调解协商记录可作为中断/中止的辅助证据",
        }
        result = [hint for token, hint in hints.items() if token in (text or "")]
        return result[:3]

    async def run(self, request: SkillRequest) -> SkillResult:
        try:
            return await asyncio.wait_for(self._run_impl(request), timeout=45)
        except asyncio.TimeoutError:
            return SkillResult(
                skillName=self.name,
                success=True,
                output={
                    "case_type": "未知",
                    "start_date": None,
                    "expiry_date": None,
                    "limitation_years": None,
                    "is_expired": None,
                    "status": "计算超时",
                    "suggestion": "请补充具体起算日期后重试。",
                    "legal_basis": [],
                },
                message="Limitation calculation timeout, fallback returned.",
            )
        except Exception as exc:
            logger.warning("LimitationCalculationSkill failed: %s", exc, exc_info=True)
            return SkillResult(
                skillName=self.name,
                success=True,
                output={
                    "case_type": "未知",
                    "start_date": None,
                    "expiry_date": None,
                    "limitation_years": None,
                    "is_expired": None,
                    "status": "计算失败",
                    "suggestion": "请提供权利受侵害日期、案由和是否存在中断/中止情形。",
                    "legal_basis": [],
                },
                message="Limitation calculation fallback returned.",
            )

    async def _run_impl(self, request: SkillRequest) -> SkillResult:
        observations = request.memory.get("observations", {}) if isinstance(request.memory, dict) else {}
        case_info = observations.get("case_understanding", {}) if isinstance(observations, dict) else {}
        text = request.text or ""

        case_type = self._detect_case_type(text=text, case_info=case_info)
        query = f"{case_type} 诉讼时效 中断 中止"
        rows = legal_index_builder.search_limitation_rules(query=query, top_k=5)
        years, legal_basis, case_type = self._select_rule(rows=rows, case_type=case_type)

        start_date = self._extract_date(text)
        interruption_hints = self._detect_interruptions(text)

        if not start_date:
            output = {
                "case_type": case_type,
                "start_date": None,
                "expiry_date": None,
                "limitation_years": years,
                "is_expired": None,
                "status": "缺少起算日期",
                "interruption_hints": interruption_hints,
                "legal_basis": legal_basis,
                "suggestion": "请明确“权利被侵害日期”或“合同到期日期”，以便精确计算。",
            }
            return SkillResult(
                skillName=self.name,
                success=True,
                output=output,
                message="Limitation calculation requires explicit start date.",
            )

        expiry_date = self._add_years(start_date, years)
        today = dt.date.today()
        is_expired = today > expiry_date
        days_remaining = (expiry_date - today).days

        if is_expired:
            status = "可能已过时效"
            suggestion = "建议立即核查是否存在时效中断/中止证据，并尽快由律师评估可诉空间。"
        elif days_remaining <= 90:
            status = "临近时效"
            suggestion = "建议尽快采取仲裁/诉讼或有效催告措施，避免时效风险。"
        else:
            status = "时效尚可"
            suggestion = "建议尽快固定证据并预留程序准备时间。"

        output = {
            "case_type": case_type,
            "start_date": start_date.isoformat(),
            "expiry_date": expiry_date.isoformat(),
            "limitation_years": years,
            "is_expired": is_expired,
            "days_remaining": days_remaining,
            "status": status,
            "interruption_hints": interruption_hints,
            "legal_basis": legal_basis,
            "suggestion": suggestion,
        }
        return SkillResult(
            skillName=self.name,
            success=True,
            output=output,
            message=f"Limitation calculated: {status}.",
        )
