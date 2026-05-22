from __future__ import annotations

import json
from typing import Any, Dict


BASE_RULES = """你是合同审查工作流中的结构化信息助手。
输出必须是 JSON，不要输出 Markdown 包裹 JSON。
不要编造法条、案例、法规编号、裁判观点或正式法律依据。
如果无法判断，字段填 unknown 或 empty list。
风险判断只能基于输入合同文本和当前 state。
所有法律依据都标记为待 RAG 补充。
不要做最终法律意见结论。
保持职业、克制、可审核。"""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def render_parse_contract_prompt(contract_text: str) -> str:
    return f"""{BASE_RULES}

TASK: parse_contract
请从合同文本中抽取结构化合同基本信息，严格输出以下 JSON 字段：
contract_title, parties, contract_type, key_dates, amounts, obligations, summary

合同文本：
{contract_text}
"""


def render_risk_detect_prompt(contract_text: str, state: Dict[str, Any]) -> str:
    return f"""{BASE_RULES}

TASK: risk_detect
请基于合同文本和当前 state 识别合同文本自身暴露的风险点。
禁止写“根据某法第几条”“某案例认为”等未检索依据。
reason 只能说明“基于合同文本本身”的风险判断。
evidenceIds 在未接入 RAG 前必须为空数组。
严格输出 JSON：{{"risks": [...]}}

当前 state：
{_json(state)}

合同文本：
{contract_text}
"""


def render_report_generate_prompt(state: Dict[str, Any]) -> str:
    return f"""{BASE_RULES}

TASK: report_generate
请生成合同审查报告 Markdown，并严格输出 JSON：{{"report_markdown": "..."}}。
报告必须包含：
- 合同基本信息
- 风险摘要
- 风险条款列表
- 修改建议
- 人工审核状态
- Evidence 依据链，引用当前 state.evidences 中的 sourceName、citationText，并标注演示依据 / 待正式法律知识库校验
- 免责声明：当前报告未接入正式法律法规 RAG，法律依据部分仅为演示或待补充

当前 state：
{_json(state)}
"""


__all__ = [
    "render_parse_contract_prompt",
    "render_risk_detect_prompt",
    "render_report_generate_prompt",
]
