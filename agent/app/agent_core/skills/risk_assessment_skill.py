from typing import Any, Dict, List

from app.agent_core.federated.federated_adapter import FederatedAdapter
from app.agent_core.schema.agent_types import SkillRequest, SkillResult
from app.agent_core.skills.base import BaseSkill


class RiskAssessmentSkill(BaseSkill):
    def __init__(self):
        super().__init__("risk_assessment")
        self.federated_adapter = FederatedAdapter()

    def _to_list(self, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        if isinstance(value, str):
            return [value] if value.strip() else []
        return [str(value)]

    def _score_to_level(self, score: int) -> str:
        if score >= 70:
            return "high"
        if score >= 40:
            return "medium"
        return "low"

    def _calc_score(
        self,
        case_info: Dict[str, Any],
        statutes: List[Dict[str, Any]],
        cases: List[Dict[str, Any]],
        evidence_analysis: Dict[str, Any],
        limitation_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        score = 20
        matrix: List[Dict[str, Any]] = []
        key_risks: List[str] = []
        suggestions: List[str] = []

        facts = str(case_info.get("facts", "")).strip()
        missing_info = self._to_list(case_info.get("missing_info"))
        parties = self._to_list(case_info.get("parties"))
        legal_issues = self._to_list(case_info.get("legal_issues"))

        evidence_score = 20
        if not facts or len(facts) < 40:
            evidence_score += 15
            key_risks.append("案情事实描述较少，证据链不足")
            suggestions.append("补充关键事实时间线、金额、履约行为和证据目录")
        if len(missing_info) >= 3:
            evidence_score += 20
            key_risks.append("缺失关键信息较多")
            suggestions.append("优先补齐 missing_info 列表中的核心事实")
        if not parties:
            evidence_score += 10
            key_risks.append("当事人身份不清晰")
            suggestions.append("明确原被告主体资格与关联关系")

        missing_evidence = self._to_list(evidence_analysis.get("missing_evidence"))
        if len(missing_evidence) >= 2:
            evidence_score += 10
            key_risks.append("证据链存在缺口")
            suggestions.append("按证据分析结果优先补齐关键证据")
        score += min(evidence_score, 40)
        matrix.append({"dimension": "evidence", "score": min(evidence_score, 40), "note": "证据与事实完整性"})

        legal_basis_score = 10
        if len(statutes) == 0:
            legal_basis_score += 20
            key_risks.append("未检索到可支持法条")
            suggestions.append("补充检索关键词并确认条文适用条件")
        elif len(statutes) < 2:
            legal_basis_score += 10
            key_risks.append("法条支撑较弱")
            suggestions.append("增加备选法条并做适用性对比")

        if len(cases) == 0:
            legal_basis_score += 15
            key_risks.append("缺少可参考判例")
            suggestions.append("补充同案由、同争点的判例参考")
        score += min(legal_basis_score, 30)
        matrix.append({"dimension": "legal_basis", "score": min(legal_basis_score, 30), "note": "法条与判例支撑度"})

        procedure_score = 10
        if any("时效" in issue for issue in legal_issues):
            procedure_score += 10
            key_risks.append("可能存在诉讼时效争议")
            suggestions.append("核查权利被侵害时间点，准备时效中断/中止证据")

        if limitation_result.get("is_expired") is True:
            procedure_score += 20
            key_risks.append("时效结果显示可能已过期")
            suggestions.append("优先核查时效中断/中止证据并评估可诉性")
        elif limitation_result.get("status") == "临近时效":
            procedure_score += 12
            key_risks.append("案件临近时效截止")
            suggestions.append("立即采取仲裁/诉讼等程序动作锁定时效")
        score += min(procedure_score, 20)
        matrix.append({"dimension": "procedure", "score": min(procedure_score, 20), "note": "程序性风险"})

        total = max(0, min(int(score), 100))
        level = self._score_to_level(total)

        if not key_risks:
            key_risks.append("当前未发现明显高风险项")
        if not suggestions:
            suggestions.append("持续补充事实与证据，定期复评风险")

        return {
            "risk_level": level,
            "risk_score": total,
            "risk_matrix": matrix,
            "key_risks": key_risks,
            "mitigation_suggestions": suggestions,
        }

    async def _merge_federated_enhancement(self, base_output: Dict[str, Any], case_info: Dict[str, Any]) -> Dict[str, Any]:
        enhancement = await self.federated_adapter.get_risk_enhancement(case_info)

        federated_info = {
            "enabled": self.federated_adapter.enabled,
            "applied": False,
            "risk_adjustment": 0.0,
            "confidence": 0.0,
            "federated_nodes_count": 0,
        }

        if not enhancement:
            base_output["federated"] = federated_info
            return base_output

        adjustment = float(enhancement.get("risk_adjustment", 0.0) or 0.0)
        confidence = float(enhancement.get("confidence", 0.0) or 0.0)
        nodes = int(enhancement.get("federated_nodes_count", 0) or 0)

        base_score = int(base_output.get("risk_score", 0) or 0)
        adjusted_score = max(0, min(100, int(round(base_score + adjustment * 100))))

        base_output["base_risk_score"] = base_score
        base_output["risk_score"] = adjusted_score
        base_output["risk_level"] = self._score_to_level(adjusted_score)
        base_output["federated"] = {
            "enabled": self.federated_adapter.enabled,
            "applied": True,
            "risk_adjustment": round(adjustment, 4),
            "confidence": round(confidence, 4),
            "federated_nodes_count": nodes,
        }

        base_output.setdefault("mitigation_suggestions", [])
        base_output["mitigation_suggestions"].append(
            "已叠加联邦学习增强评估，建议结合本地证据再次核验风险等级"
        )
        return base_output

    async def run(self, request: SkillRequest) -> SkillResult:
        observations = request.memory.get("observations", {}) if isinstance(request.memory, dict) else {}
        case_info = observations.get("case_understanding", {})
        statutes = observations.get("statute_retrieval", {}).get("statutes", [])
        cases = observations.get("case_retrieval", {}).get("cases", [])
        evidence_analysis = observations.get("evidence_analysis", {})
        limitation_result = observations.get("limitation_calculation", {})

        output = self._calc_score(
            case_info=case_info,
            statutes=statutes,
            cases=cases,
            evidence_analysis=evidence_analysis if isinstance(evidence_analysis, dict) else {},
            limitation_result=limitation_result if isinstance(limitation_result, dict) else {},
        )
        output = await self._merge_federated_enhancement(output, case_info)

        federated_tag = "federated:on" if output.get("federated", {}).get("applied") else "federated:off"
        return SkillResult(
            skillName=self.name,
            success=True,
            output=output,
            message=f"Risk assessed as {output['risk_level']} ({output['risk_score']}/100), {federated_tag}.",
        )
