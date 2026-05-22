from __future__ import annotations

from typing import Any, Dict

from app.llm.schemas import compact_schema_name


class MockLLMProvider:
    provider_name = "mock"
    model = "mock-contract-review"

    def generate_text(self, prompt: str, **kwargs) -> str:
        return "Mock provider response."

    def generate_json(self, prompt: str, schema: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        task = compact_schema_name(schema)
        if task == "parse_contract":
            return {
                "contract_title": "软件开发服务合同",
                "parties": [
                    {"name": "甲方", "role": "委托方"},
                    {"name": "乙方", "role": "开发服务方"},
                ],
                "contract_type": "软件开发服务合同",
                "key_dates": [],
                "amounts": ["签署后 30%", "上线后 70%"],
                "obligations": ["开发 CRM 系统", "完成上线交付", "配合验收"],
                "summary": "合同围绕 CRM 系统开发、付款、验收和源代码权属作出基础约定。",
            }
        if task == "risk_detect":
            return {
                "risks": [
                    {
                        "id": "risk-payment-01",
                        "title": "尾款支付条件过于单一",
                        "level": "high",
                        "clause": "系统上线后支付 70%。",
                        "reason": "基于合同文本本身，上线不等于验收完成，尾款触发条件缺少缺陷修复和验收确认约束。",
                        "consequence": "系统存在缺陷时，双方可能就是否应支付尾款产生争议。",
                        "suggestion": "将尾款支付条件改为验收通过并稳定运行一定期间后支付。",
                        "evidenceIds": [],
                    },
                    {
                        "id": "risk-acceptance-01",
                        "title": "验收标准缺少客观指标",
                        "level": "medium",
                        "clause": "如无重大问题视为验收通过。",
                        "reason": "基于合同文本本身，重大问题未定义，缺少测试标准、反馈期限和整改次数。",
                        "consequence": "双方可能对缺陷严重程度和验收是否通过产生争议。",
                        "suggestion": "补充功能清单、性能指标、验收材料、反馈期限和整改流程。",
                        "evidenceIds": [],
                    },
                    {
                        "id": "risk-ip-01",
                        "title": "知识产权共同所有安排不清",
                        "level": "high",
                        "clause": "项目源代码归双方共同所有。",
                        "reason": "基于合同文本本身，共同所有未说明使用、转让、二次开发和第三方组件边界。",
                        "consequence": "后续系统迭代、商业化或对外交付源码时可能出现权属冲突。",
                        "suggestion": "分别约定定制成果归属、乙方通用工具保留权利和第三方组件合规责任。",
                        "evidenceIds": [],
                    },
                ]
            }
        if task == "report_generate":
            return {
                "report_markdown": """# 软件开发服务合同审查报告

## 合同基本信息
- 合同类型：软件开发服务合同
- 审查范围：付款、验收、知识产权和交付责任

## 风险摘要
当前识别到高风险 2 项、中风险 1 项。风险判断仅基于合同文本本身。

## 风险条款列表
1. 尾款支付条件过于单一
2. 验收标准缺少客观指标
3. 知识产权共同所有安排不清

## 修改建议
- 将尾款支付与验收通过、稳定运行和缺陷修复挂钩。
- 补充验收标准、测试材料、反馈期限和整改流程。
- 明确定制成果、通用工具和第三方组件的权利边界。

## 人工审核状态
已通过人工审核后生成报告。

## 免责声明
当前报告未接入正式法律法规 RAG，法律依据部分仅为演示或待补充；本报告不构成最终法律意见，需律师复核。
"""
            }
        return {}
