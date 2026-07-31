export type AcgPromptPreset = {
  id: string
  name: string
  taskName: string
  description: string
  contractText: string
  userIntent: string
}

const softwareDevelopmentContract = `甲方：星河科技有限公司。乙方：知弈软件工作室。甲方委托乙方开发客户关系管理 CRM 系统，乙方负责需求梳理、原型设计、系统开发、测试部署和上线支持。

项目总价为人民币 80 万元。甲方在合同签署后 5 个工作日内支付 30%，系统上线后一次性支付剩余 70%。合同未明确阶段性验收、缺陷修复期、发票开具条件和上线失败后的付款处理方式。

乙方应在 60 日内完成交付。验收标准为“系统无重大问题即视为验收通过”，甲方收到交付物后 5 日内未提出书面异议的，也视为验收通过。合同未列明功能清单、性能指标、测试用例、整改次数和最终确认流程。

项目源代码、接口文档、数据库设计、UI 设计稿及相关成果归甲乙双方共同所有。乙方可在后续项目中复用通用模块，涉及第三方开源组件的授权合规由双方另行协商。

任一方逾期履行义务，应按合同总价每日万分之五支付违约金。合同未明确延期交付、质量缺陷、数据泄露、逾期付款、知识产权侵权和保密违约的责任边界及赔偿上限。

双方应对项目资料、客户数据和商业信息承担保密义务，但合同未约定保密期限、数据删除、日志留存、权限控制和安全事件通知机制。争议解决条款仅写明“双方友好协商，协商不成另行处理”。`

export const ACG_PROMPT_PRESETS: readonly AcgPromptPreset[] = [
  {
    id: 'software-development-full-review',
    name: '软件开发合同：完整审查',
    taskName: '软件开发合同审查',
    description: '覆盖条款、风险、证据、修改建议与人工复核的完整演示提示词。',
    contractText: softwareDevelopmentContract,
    userIntent: `请以 ACG 多智能体协作方式审查这份软件开发合同，强制生成差异化任务图，并完整执行合同文本解析、条款分类、风险识别、证据/依据匹配、修改建议生成、人工审核要点提取和最终 Markdown 审查报告生成。

重点审查付款条款、验收标准、知识产权归属、开源组件合规、违约责任、保密义务、数据安全、交付范围和争议解决。请尽量并行分析付款、验收、知识产权、违约责任和数据安全五类风险，再汇聚为统一风险结论。

请用低熵通信方式组织上下文：解析节点只投递合同类型、主体、范围、付款、验收、知识产权和争议解决字段；条款分类节点只投递 clauses；风险识别节点只投递 risks、risk_level、risk_score；证据匹配节点只投递 evidences、citations；修改建议节点只投递 revision_suggestions、manual_review_focus。

最终报告必须包含合同基本信息、条款分类摘要、高中低风险清单、每个风险点的条款位置、风险原因、可能后果、证据依据、修改建议、人工复核关注点和签署前处理结论。`
  },
  {
    id: 'software-development-smoke-review',
    name: '软件开发合同：快速验证',
    taskName: '软件开发合同快速审查',
    description: '用于验证材料传入、基础审查和报告交付链路的精简提示词。',
    contractText: softwareDevelopmentContract,
    userIntent: `请审查这份软件开发合同，识别付款、验收、知识产权、数据安全和争议解决中的主要风险。

输出简洁 Markdown 报告，包含风险等级、原因、证据依据、修改建议和签署前复核事项。仅传递完成当前步骤所需的结构化字段。`
  }
]

export const DEFAULT_ACG_PROMPT_PRESET = ACG_PROMPT_PRESETS[0]
