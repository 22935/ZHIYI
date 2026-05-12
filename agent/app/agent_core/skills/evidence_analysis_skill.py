import asyncio
import json
import logging
import re
from typing import Any, Dict, List

from app.agent_core.retrieval.legal_index_builder import legal_index_builder
from app.agent_core.schema.agent_types import SkillRequest, SkillResult
from app.agent_core.skills.base import BaseSkill
from app.services.aiservice import AIService

logger = logging.getLogger(__name__)

_ai_service = AIService()


class EvidenceAnalysisSkill(BaseSkill):
    def __init__(self):
        super().__init__("evidence_analysis")

    def _extract_items(self, text: str) -> List[Dict[str, str]]:
        evidence_map = {
            "微信": ("微信聊天记录", "电子数据", "中等", "建议保留原始聊天导出文件并证明对方身份"),
            "聊天": ("聊天记录", "电子数据", "中等", "应提交完整上下文，避免断章取义"),
            "转账": ("银行转账记录", "书证", "较强", "建议提供银行回单和账户主体信息"),
            "银行流水": ("银行流水", "书证", "较强", "与工资条/合同对应时证明力更高"),
            "录音": ("通话录音", "视听资料", "中等", "需说明取得方式合法，建议形成文字整理稿"),
            "证人": ("证人证言", "证人证言", "较弱", "建议确保关键证人可出庭并有客观印证"),
            "劳动合同": ("书面劳动合同", "书证", "较强", "可直接证明劳动关系和约定义务"),
            "工资条": ("工资条", "书证", "中等", "与银行流水、考勤记录结合更有效"),
            "考勤": ("考勤记录", "电子数据", "中等", "应体现时间连续性和完整性"),
            "邮件": ("电子邮件", "电子数据", "中等", "需包含完整邮件头与发送接收信息"),
            "截图": ("页面截图", "电子数据", "较弱", "应补充原始数据或平台取证记录"),
            "发票": ("发票凭证", "书证", "中等", "应与交易合同、付款记录形成闭环"),
        }

        text = text or ""
        extracted: List[Dict[str, str]] = []
        for keyword, (name, item_type, strength, notes) in evidence_map.items():
            if keyword in text:
                extracted.append(
                    {
                        "name": name,
                        "type": item_type,
                        "strength": strength,
                        "notes": notes,
                    }
                )

        seen = set()
        unique_items: List[Dict[str, str]] = []
        for item in extracted:
            key = item["name"]
            if key in seen:
                continue
            seen.add(key)
            unique_items.append(item)
        return unique_items

    def _infer_missing(self, items: List[Dict[str, str]], case_info: Dict[str, Any], text: str) -> List[str]:
        names = {item.get("name", "") for item in items}
        missing: List[str] = []
        text = text or ""
        case_type = str(case_info.get("case_type", ""))

        if "劳动" in case_type or "工资" in text:
            if "书面劳动合同" not in names:
                missing.append("书面劳动合同（或能证明劳动关系的替代证据）")
            if "银行流水" not in names and "银行转账记录" not in names:
                missing.append("工资银行流水")
            if "考勤记录" not in names:
                missing.append("考勤记录或工作安排记录")

        if "合同" in case_type or "合同" in text:
            if "合同正本/盖章版本" not in names:
                missing.append("合同正本或盖章版本")
            if "履约/违约通知记录" not in names:
                missing.append("履约过程记录与违约通知证据")

        if not missing:
            if len(items) < 2:
                missing.append("至少补充 1-2 项可客观核验的书证或电子原始数据")
            else:
                missing.append("补充能够形成时间线闭环的证据（时间、主体、金额）")
        return missing

    def _assessment_text(self, items: List[Dict[str, str]], missing: List[str]) -> str:
        strong_count = sum(1 for item in items if item.get("strength") == "较强")
        if strong_count >= 2 and len(items) >= 4 and len(missing) <= 2:
            return "证据链总体较完整，建议补充缺口后再进入实质争议举证。"
        if len(items) >= 2:
            return "现有证据可初步支撑主张，但仍存在关键缺口，建议尽快补齐核心书证与原始电子数据。"
        return "当前证据基础较弱，建议优先补充可直接证明法律关系和关键事实的证据。"

    def _collect_legal_basis(self, rows: List[Dict[str, Any]]) -> List[str]:
        basis = []
        for row in rows:
            metadata = row.get("metadata", {})
            item = str(metadata.get("basis", "")).strip()
            if item:
                basis.append(item)
        seen = set()
        ordered = []
        for item in basis:
            if item in seen:
                continue
            seen.add(item)
            ordered.append(item)
        return ordered[:5]

    async def _refine_assessment(self, payload: Dict[str, Any], text: str) -> str:
        prompt = (
            "你是律师证据审查助手。请基于给定JSON输出一段80字以内结论，"
            "必须包含“证明力、关联性、合法性”三点，不要编造事实。\n"
            f"用户问题: {text}\n"
            f"结构化信息: {json.dumps(payload, ensure_ascii=False)}"
        )
        response = await asyncio.wait_for(_ai_service.generate_text(text=prompt), timeout=45)
        result = (response.get("text", "") or "").strip()
        return result or payload.get("overall_assessment", "")

    async def run(self, request: SkillRequest) -> SkillResult:
        try:
            return await asyncio.wait_for(self._run_impl(request), timeout=45)
        except asyncio.TimeoutError:
            return SkillResult(
                skillName=self.name,
                success=True,
                output={
                    "evidence_items": [],
                    "missing_evidence": ["证据分析超时，请补充证据清单后重试"],
                    "overall_assessment": "证据分析超时，已返回降级结果。",
                    "legal_basis": [],
                },
                message="Evidence analysis timeout, fallback returned.",
            )
        except Exception as exc:
            logger.warning("EvidenceAnalysisSkill failed: %s", exc, exc_info=True)
            return SkillResult(
                skillName=self.name,
                success=True,
                output={
                    "evidence_items": [],
                    "missing_evidence": ["暂无法完成自动分析，请手动补充关键证据清单"],
                    "overall_assessment": "证据分析失败，已返回降级结果。",
                    "legal_basis": [],
                },
                message="Evidence analysis fallback returned.",
            )

    async def _run_impl(self, request: SkillRequest) -> SkillResult:
        observations = request.memory.get("observations", {}) if isinstance(request.memory, dict) else {}
        case_info = observations.get("case_understanding", {}) if isinstance(observations, dict) else {}

        text = request.text or ""
        items = self._extract_items(text)
        rows = legal_index_builder.search_evidence_rules(query=text, top_k=5)
        legal_basis = self._collect_legal_basis(rows)
        missing = self._infer_missing(items=items, case_info=case_info, text=text)
        assessment = self._assessment_text(items=items, missing=missing)

        payload = {
            "evidence_items": items,
            "missing_evidence": missing,
            "overall_assessment": assessment,
            "legal_basis": legal_basis,
        }

        try:
            payload["overall_assessment"] = await self._refine_assessment(payload, text)
        except Exception:
            pass

        return SkillResult(
            skillName=self.name,
            success=True,
            output=payload,
            message=f"Evidence analysis completed with {len(items)} identified evidence item(s).",
        )
