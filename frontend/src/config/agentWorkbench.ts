// Role/template registry for the AgentOS workbench.
// Keep page rendering generic: add or update roles here, then wire backend workflows later.

export interface TemplateConfig {
  key: string
  roleId: RoleId
  name: string
  brief: string
  title: string
  subtitle: string
  inputTitle: string
  placeholder: string
  actionLabel: string
  flowTitle: string
  outputTitle: string
  configTitle: string
  successMessage: string
  domain: string
  intent: string
  workflowId: string
  workflowLabel: string
  runtimeLabel: string
  executionMode: ExecutionMode
  reviewMode: 'human_in_loop' | 'auto'
  inputKey: string
  inputAliases: string[]
  resultView: ResultView
  defaultText: string
  steps: TemplateStep[]
  outputs: TemplateOutput[]
  monitors: MonitorItem[]
}

export interface RoleTemplateGroup {
  id: RoleId
  short: string
  name: string
  summary: string
  tone: string
  accent: string
  softAccent: string
  templates: TemplateConfig[]
}

export interface TemplateStep {
  id: string
  title: string
  agent: string
  status: string
  tone?: TaskTone
}

export interface TemplateOutput {
  id: string
  title: string
  path: string
}

export interface MonitorItem {
  id: string
  title: string
  value: string
}

export interface FrontendPreviewResult {
  templateKey: string
  roleName: string
  templateName: string
  workflowId: string
  createdAt: string
  summary: string
  panels: Array<{ id: string; title: string; content: string }>
}

export type RoleId = 'lawyer' | 'teacher' | 'programmer' | 'writer'
export type ExecutionMode = 'backend' | 'preview'
export type ResultView = 'contract-review' | 'generic'
export type TaskTone = 'blue' | 'green' | 'purple' | 'orange'

export const taskToneSequence: TaskTone[] = ['blue', 'green', 'purple', 'orange']

export const taskToneStyles: Record<TaskTone, { accent: string; soft: string }> = {
  blue: { accent: 'var(--info)', soft: 'var(--info-fade)' },
  green: { accent: 'var(--success)', soft: 'var(--success-fade)' },
  purple: { accent: 'var(--accent-color)', soft: 'var(--accent-fade)' },
  orange: { accent: 'var(--warning)', soft: 'var(--warning-fade)' }
}

export const templateDisplayPrompts = {
  'lawyer-review': `请以资深合同审查律师的身份，对以下软件开发合同进行结构化审查。
【业务背景】甲方委托乙方开发 CRM 系统，项目周期 90 天，合同金额 80 万元，甲方关注交付延期、验收标准、源代码权属、保密责任和违约赔偿。
【待审条款】合同约定签署后支付 30%，系统上线后支付 70%；如甲方在 5 个工作日内未提出书面异议，视为验收通过；项目源代码归双方共同所有；乙方可复用通用组件但不得泄露甲方业务数据。
【审查目标】请识别高、中、低风险条款，说明风险成因、可能后果和触发场景；为每个风险匹配可追溯的法律依据或合同解释依据；给出可直接替换进合同的修改建议。
【输出格式】请按“风险摘要、依据链、修改建议、谈判优先级、需人工确认事项”组织结果。`,
  'lawyer-case': `请作为诉讼律师，对以下软件项目争议进行案件分析。
【案情概述】客户委托外包公司开发客户管理系统，合同约定 2026 年 3 月 31 日完成上线。乙方实际在 5 月中旬提交版本，且核心的标签筛选、权限控制、数据导入功能存在缺陷。甲方曾通过邮件、会议纪要和缺陷清单多次催告。
【争议焦点】乙方主张甲方频繁变更需求导致延期，甲方认为需求变更均属于合同范围内的细化说明；双方对验收是否通过、剩余尾款是否应支付、源代码是否应交付存在分歧。
【已有证据】合同及补充协议、需求确认表、迭代计划、缺陷清单、邮件沟通记录、会议纪要、测试报告、付款凭证。
【输出要求】请提炼案件事实时间线、归纳请求权基础、列出关键证据缺口、评估诉讼/仲裁风险，并给出起诉前谈判策略。`,
  'lawyer-research': `请围绕“软件开发合同中的默示验收、源代码权属、延期交付责任”进行法律检索规划。
【使用场景】准备为一份软件外包合同审查报告补充依据，需要同时覆盖合同条款修改、争议预判和谈判备忘录。
【检索范围】优先检索中国大陆现行有效法律法规、司法解释、典型案例、类案裁判观点和行业常见合同条款。
【重点问题】1. 未在约定期限内提出异议能否认定验收通过；2. 定制开发成果与通用组件的权属如何区分；3. 延期交付与需求变更、配合义务之间如何分配责任；4. 违约金、损失赔偿和继续履行的适用边界。
【输出要求】请给出检索关键词、检索式、依据清单、裁判观点摘要、可引用到合同审查报告中的结论。`,
  'lawyer-document': `请以律师函起草律师的身份，基于以下事实生成一份正式但保留谈判空间的律师函草稿。
【事实背景】委托方与外包公司签订 CRM 系统开发合同，约定 2026 年 3 月 31 日前完成上线并交付源代码、部署文档和测试报告。外包公司至今仅提交部分功能，标签筛选、权限控制、数据导入仍无法稳定使用。
【委托方诉求】要求对方在 10 个工作日内完成缺陷修复、提交完整交付物、配合验收，并就延期造成的内部人力和运营损失提出补偿方案。
【证据材料】合同、补充需求确认单、付款凭证、缺陷清单、邮件催告记录、会议纪要、测试截图。
【写作要求】语气专业克制，不直接激化矛盾；清楚列明违约事实、合同依据、整改期限、保留追责权利；末尾加入可协商解决的窗口。`,
  'teacher-lesson': `请为初中数学“一次函数图像与性质”设计一节 45 分钟公开课教案。
【学生情况】八年级学生，能理解变量和坐标系，能代入函数表达式求点，但对斜率、截距与图像变化的关系掌握不稳定，部分学生容易把“图像上升”机械理解为数值变大。
【教学目标】让学生理解一次函数 y=kx+b 中 k、b 对图像的影响，能够根据表达式判断图像趋势，并能用函数图像解释简单真实问题。
【课堂要求】包含导入情境、探究活动、板书设计、例题讲解、学生互动、即时检测、分层练习和课堂总结；请控制每个环节时间。
【输出格式】请按“学情分析、目标、重难点、教学流程、例题、互动问题、板书、作业”组织。`,
  'teacher-grading': `请以初中数学教师的身份批改以下一次函数应用题，并给出可直接反馈给学生的话术。
【题目】某网约车起步价 12 元，超过 3 公里后每公里 2.4 元。请建立路程 x 与费用 y 的函数关系，并解释斜率和截距的实际意义。
【学生答案】y=2.4x+12。斜率表示车费，截距表示公里数。因为每多走一公里多 2.4 元，所以图像一直上升。
【评分标准】满分 10 分：分段条件 2 分，表达式 3 分，斜率解释 2 分，截距解释 2 分，语言完整 1 分。
【输出要求】请给出得分、扣分点、错因诊断、鼓励性反馈、订正示范和 2 道针对性巩固题。`,
  'teacher-diagnosis': `请根据以下材料生成一份学生学情诊断报告。
【学生画像】八年级学生，课堂参与度较高，计算速度较快，但遇到实际情境题容易忽略变量含义，喜欢套公式，解释性表达较弱。
【近期表现】一次函数单元测验 72 分，基础代入题正确率 90%，图像读数题正确率 65%，应用建模题正确率 45%。错题集中在“自变量取值范围、斜率实际意义、分段函数情境”。
【教师目标】希望在两周内帮助学生补齐函数建模和表达能力，同时避免重复刷太多低效计算题。
【输出要求】请输出知识掌握雷达、薄弱点排序、错因分析、两周学习路径、每日练习建议和家长沟通话术。`,
  'teacher-error-push': `请根据以下错题样本，为学生设计分层错题推送。
【错题样本】学生在“根据图像读取速度变化”“判断一次函数中 k 的实际意义”“根据收费规则建立函数表达式”三类题中连续出错，常见答案是只写公式，不解释变量和单位。
【学生基础】计算能力中等偏上，愿意订正，但看到长题干容易跳读；需要从简单情境逐步过渡到综合建模。
【推送目标】先纠正概念误解，再训练读图和建模，最后用一道综合题检查迁移能力。
【输出要求】请归类错因，生成 3 道由易到难的变式题，每题包含答案、解析、提醒语和预计用时，并附 3 天复习安排。`,
  'programmer-requirement': `请作为全栈工程师，对“客户标签管理”功能进行需求分析和交付规划。
【项目背景】现有 CRM 系统包含客户列表、客户详情、用户权限和操作日志模块，技术栈为 Vue 3 + TypeScript + Element Plus，后端为 FastAPI + PostgreSQL。
【功能目标】运营人员可以创建、编辑、删除标签；在客户详情页给客户绑定多个标签；在客户列表中按标签筛选；管理员可查看标签变更日志。
【约束条件】需要复用现有权限体系和审计日志；列表页不能明显变慢；标签名称不可重复；删除标签前需提示影响范围。
【输出要求】请拆解用户故事、接口草案、数据模型、前后端改动点、风险点、测试清单，并生成一个 Mermaid 业务流程图。`,
  'programmer-code': `请根据以下工程任务生成实现方案、代码骨架和测试建议。
【任务目标】为 CRM 系统新增客户标签 CRUD API，并提供前端标签管理列表组件。
【后端要求】使用 FastAPI 路由，支持分页查询、创建、重命名、删除；标签名称唯一；删除前检查是否已绑定客户；所有变更写入 audit_log。
【前端要求】使用 Vue 3 + TypeScript + Element Plus，包含搜索、分页、新建弹窗、编辑弹窗、删除确认和错误提示；样式保持现有管理后台风格。
【测试要求】提供 API 单元测试、前端组件交互测试和至少 5 个边界用例。
【输出格式】请按“实现计划、文件清单、关键代码片段、测试清单、注意事项”组织，不要引入新的大型依赖。`,
  'programmer-search': `请对当前代码库进行语义检索规划，目标是定位“客户标签筛选”和“权限控制”相关实现。
【检索目标】找到客户列表页面、客户详情页、权限判断工具、审计日志写入逻辑、API service 封装和后端客户查询接口。
【线索词】customer、client、tag、label、filter、permission、audit、role、scope、客户、标签、权限、日志。
【希望结果】请输出最可能相关的文件路径、函数/组件名称、调用链关系、数据流入口、需要重点阅读的代码片段，以及新增标签功能时最可能改动的区域。
【约束】请区分“真实命中”“语义推断”和“待确认位置”，避免把不确定内容当成事实。`,
  'programmer-diagram': `请为 CRM 客户标签功能生成架构图和流程图设计说明。
【系统模块】前端包含客户列表、客户详情、标签管理弹窗、权限守卫和 API client；后端包含 tag router、customer service、permission service、audit log service 和 PostgreSQL。
【关键流程】运营人员创建标签；给客户绑定标签；客户列表按标签筛选；管理员查看标签变更日志；无权限用户访问时被拦截。
【图示要求】请输出 Mermaid，至少包含一个模块关系图和一个用户操作流程图；节点名称要清楚，边上标注主要数据或动作。
【附加要求】请补充图示说明、边界条件、权限检查位置和后续可扩展点，例如批量打标、标签分组和标签颜色。`,
  'writer-inspiration': `请把下面的故事种子扩展成多个可写方向。
【灵感种子】一名年轻合同审查律师在深夜检查软件外包合同时，发现某个看似普通的验收条款与十年前一起失踪案中的公司名称产生关联。
【故事气质】法律悬疑、都市现实、克制冷峻，重点不是超自然，而是隐藏在商业文件和人际关系中的真相。
【扩写目标】请生成 5 个不同故事方向，每个方向包含核心冲突、主角欲望、反派或阻力、关键场景、反转点和开篇钩子。
【限制】避免套路化“万能阴谋”，让线索尽量来自合同、邮件、会议纪要、付款记录等现实材料。`,
  'writer-outline': `请为一篇 1.5 万字左右的法律悬疑中篇生成故事大纲。
【设定】主角是初入律所两年的合同审查律师，性格谨慎但有强烈正义感。她在审查一份软件外包合同时，发现验收条款、源代码权属和旧案证据之间存在异常联系。
【核心冲突】客户希望尽快签约，合伙人要求控制成本，主角却怀疑合同背后有人刻意掩盖十年前的数据泄露事故。
【风格要求】节奏紧凑，线索推进清晰，人物动机可信，结尾既有法律层面的解决，也保留现实复杂性。
【输出要求】请给出主题、人物弧光、三幕式结构、章节大纲、关键线索表、悬念布置和结尾方案。`,
  'writer-content': `请根据以下设定写一段约 800 字的小说开场。
【叙事视角】第三人称有限视角，贴近年轻律师林知微的观察和判断。
【场景】凌晨 1 点的律所会议室，窗外下雨，林知微独自审查一份软件外包合同。她原本只想确认验收条款，却在附件文件名和十年前旧案编号之间发现异常。
【风格】冷静、克制、有悬疑感；不要过度解释背景，让细节自然露出；对话少而有张力。
【必须包含】合同条款片段、电脑屏幕上的附件清单、一次突兀的电话震动、主角对风险的职业直觉。
【输出要求】只写正文，不要写分析说明。`,
  'writer-character': `请为法律悬疑故事设计人物关系网。
【核心人物】林知微：年轻合同审查律师，擅长从文件细节发现矛盾；周砚：委托方 CTO，表面配合但隐瞒旧项目经历；沈泊川：外包公司负责人，熟悉十年前的数据泄露事故；许澜：十年前失踪案当事人的姐姐，如今是合规顾问。
【关系要求】每个人都要有公开目标、隐藏秘密、与其他角色的利益冲突和情感牵连。
【故事功能】人物关系需要推动合同审查线、旧案线和主角成长线交织推进。
【输出格式】请生成角色卡、关系矩阵、冲突链条、秘密揭露顺序和可用于章节安排的关键对手戏。`
} as const

const makeTemplate = (
  roleId: RoleId,
  config: {
    key: string
    name: string
    brief: string
    inputTitle: string
    placeholder: string
    domain: string
    intent: string
    workflowId: string
    workflowLabel: string
    runtimeLabel: string
    inputKey: string
    inputAliases?: string[]
    resultView?: ResultView
    defaultText: string
    steps: TemplateStep[]
    outputs: TemplateOutput[]
    executionMode?: ExecutionMode
    reviewMode?: 'human_in_loop' | 'auto'
    title?: string
    subtitle?: string
    actionLabel?: string
    flowTitle?: string
    outputTitle?: string
    configTitle?: string
    successMessage?: string
  }
): TemplateConfig => ({
  key: config.key,
  roleId,
  name: config.name,
  brief: config.brief,
  title: config.title || config.name,
  subtitle: config.subtitle || `由 ${config.workflowLabel} 驱动的角色模板，后端接入前先完成前端流程与结果预览。`,
  inputTitle: config.inputTitle,
  placeholder: config.placeholder,
  actionLabel: config.actionLabel || `启动${config.name} Workflow`,
  flowTitle: config.flowTitle || `${config.name}流程`,
  outputTitle: config.outputTitle || `${config.name}输出`,
  configTitle: config.configTitle || `${config.name}配置`,
  successMessage: config.successMessage || `${config.name} Workflow 已启动`,
  domain: config.domain,
  intent: config.intent,
  workflowId: config.workflowId,
  workflowLabel: config.workflowLabel,
  runtimeLabel: config.runtimeLabel,
  executionMode: config.executionMode || 'preview',
  reviewMode: config.reviewMode || 'auto',
  inputKey: config.inputKey,
  inputAliases: config.inputAliases || [],
  resultView: config.resultView || 'generic',
  defaultText: config.defaultText,
  steps: config.steps.map((step, index) => ({
    ...step,
    tone: step.tone || taskToneSequence[index % taskToneSequence.length]
  })),
  outputs: config.outputs,
  monitors: [
    { id: 'runtime', title: '运行方式', value: config.runtimeLabel },
    { id: 'workflow', title: 'Workflow ID', value: config.workflowId },
    { id: 'status', title: '接入状态', value: (config.executionMode || 'preview') === 'backend' ? '可启动后端' : '前端预览' }
  ]
})

export const roleTemplateGroups: RoleTemplateGroup[] = [
  {
    id: 'lawyer',
    short: '法',
    name: '律师',
    summary: '合同审查、案件分析、法律检索与文书生成',
    tone: '严谨、可追溯、风险优先',
    accent: '#3f6b63',
    softAccent: 'rgba(63, 107, 99, 0.12)',
    templates: [
      makeTemplate(
        'lawyer',
        {
          key: 'lawyer-review',
          name: '合同审查',
          brief: '风险识别、依据匹配与审查报告',
          title: '律师合同审查',
          subtitle: '基于 WorkflowRun、Trace、Artifacts 与 Human Review 的合同审查工作台。',
          inputTitle: '合同文本',
          placeholder: '粘贴待审查合同文本',
          actionLabel: '启动审查 Workflow',
          flowTitle: '审查流程',
          outputTitle: '结果区域',
          configTitle: '审查配置',
          successMessage: 'Workflow 已执行到 human_review:waiting_review',
          domain: 'legal',
          intent: 'contract_review',
          workflowId: 'legal_contract_review_v1',
          workflowLabel: '合同审查标准流程',
          runtimeLabel: 'ACG 已接入',
          executionMode: 'backend',
          reviewMode: 'human_in_loop',
          inputKey: 'contractText',
          inputAliases: ['caseText'],
          resultView: 'contract-review',
          defaultText: templateDisplayPrompts['lawyer-review'],
          steps: [
            { id: 'parse', title: '合同解析', agent: 'parse_contract', status: '待执行' },
            { id: 'risk', title: '风险识别', agent: 'risk_detect', status: '待执行' },
            { id: 'evidence', title: '依据匹配', agent: 'legal_evidence_match', status: '待执行' },
            { id: 'review', title: '人工审核', agent: 'human_review', status: '审核门控' },
            { id: 'report', title: '报告生成', agent: 'report_generate', status: '待执行' }
          ],
          outputs: [
            { id: 'risks', title: '风险点', path: 'output.artifacts.risk_detect.risks' },
            { id: 'evidences', title: 'Evidence 依据链', path: 'output.artifacts.legal_evidence_match.evidences' },
            { id: 'report', title: '报告预览', path: 'output.artifacts.report_generate.report_markdown' }
          ]
        }
      ),
      makeTemplate(
        'lawyer',
        {
          key: 'lawyer-case',
          name: '案件分析',
          brief: '案情接收、法条检索与风险评估',
          inputTitle: '案情材料',
          placeholder: '输入案件事实、争议焦点、证据线索和期望输出',
          domain: 'legal',
          intent: 'case_analysis',
          workflowId: 'legal_case_analysis_v1',
          workflowLabel: '法律案件分析流程',
          runtimeLabel: 'Pack Workflow 已定义 / 页面待接入',
          inputKey: 'caseText',
          defaultText: templateDisplayPrompts['lawyer-case'],
          steps: [
            { id: 'intake', title: '案情接收', agent: 'case_intake', status: '待执行' },
            { id: 'statute', title: '法条检索', agent: 'statute', status: '待执行' },
            { id: 'risk', title: '风险评估', agent: 'risk', status: '待执行' },
            { id: 'strategy', title: '策略建议', agent: 'case_strategy', status: '前端预览' }
          ],
          outputs: [
            { id: 'facts', title: '案情摘要', path: 'output.artifacts.case_intake.summary' },
            { id: 'statutes', title: '法律依据', path: 'output.artifacts.statute.items' },
            { id: 'risks', title: '诉讼风险', path: 'output.artifacts.risk_assessment.risks' }
          ]
        }
      ),
      makeTemplate(
        'lawyer',
        {
          key: 'lawyer-research',
          name: '法律检索',
          brief: '法规、案例与依据链整理',
          inputTitle: '检索问题',
          placeholder: '描述需要检索的法律问题、管辖地区和使用场景',
          domain: 'legal',
          intent: 'legal_research',
          workflowId: 'legal_research_v1',
          workflowLabel: '法律检索模板流程',
          runtimeLabel: '前端预览 / 后端待接入',
          inputKey: 'query',
          defaultText: templateDisplayPrompts['lawyer-research'],
          steps: [
            { id: 'query', title: '问题拆解', agent: 'legal_query_parse', status: '前端预览' },
            { id: 'statute', title: '法规检索', agent: 'statute_retrieval', status: '前端预览' },
            { id: 'case', title: '案例匹配', agent: 'case_retrieval', status: '前端预览' },
            { id: 'memo', title: '依据备忘录', agent: 'research_memo_generate', status: '前端预览' }
          ],
          outputs: [
            { id: 'query', title: '检索式', path: 'output.artifacts.research.query_plan' },
            { id: 'sources', title: '依据清单', path: 'output.artifacts.research.sources' },
            { id: 'memo', title: '检索备忘录', path: 'output.artifacts.research.memo' }
          ]
        }
      ),
      makeTemplate(
        'lawyer',
        {
          key: 'lawyer-document',
          name: '文书生成',
          brief: '律师函、意见书与谈判清单',
          inputTitle: '文书需求',
          placeholder: '描述文书类型、事实背景、主张目标、证据材料和语气要求',
          domain: 'legal',
          intent: 'document_generation',
          workflowId: 'legal_document_generation_v1',
          workflowLabel: '法律文书生成模板流程',
          runtimeLabel: '前端预览 / 后端待接入',
          inputKey: 'documentRequest',
          defaultText: templateDisplayPrompts['lawyer-document'],
          steps: [
            { id: 'facts', title: '事实归纳', agent: 'case_understanding', status: '前端预览' },
            { id: 'claim', title: '请求权组织', agent: 'claim_structure', status: '前端预览' },
            { id: 'draft', title: '文书草拟', agent: 'document_generation', status: '前端预览' },
            { id: 'review', title: '措辞校验', agent: 'legal_tone_review', status: '前端预览' }
          ],
          outputs: [
            { id: 'facts', title: '事实清单', path: 'output.artifacts.document.facts' },
            { id: 'claims', title: '主张结构', path: 'output.artifacts.document.claims' },
            { id: 'draft', title: '文书草稿', path: 'output.artifacts.document.markdown' }
          ]
        }
      )
    ]
  },
  {
    id: 'teacher',
    short: '教',
    name: '教师',
    summary: '教案生成、作业批改、学情诊断与错题推送',
    tone: '耐心、结构化、循序渐进',
    accent: '#4f6f9f',
    softAccent: 'rgba(79, 111, 159, 0.12)',
    templates: [
      makeTemplate('teacher', {
        key: 'teacher-lesson',
        name: '教案生成',
        brief: '目标、活动、例题与课堂节奏',
        inputTitle: '教学主题',
        placeholder: '输入学段、学科、知识点、学生基础和课时长度',
        domain: 'education',
        intent: 'lesson_plan',
        workflowId: 'education_lesson_plan_v1',
        workflowLabel: '教师教案生成流程',
        runtimeLabel: 'Pack Workflow 已定义 / 页面待接入',
        inputKey: 'topic',
        defaultText: templateDisplayPrompts['teacher-lesson'],
        steps: [
          { id: 'diagnosis', title: '学情判断', agent: 'student_diagnosis', status: '前端预览' },
          { id: 'goal', title: '目标拆解', agent: 'teaching_goal_parse', status: '前端预览' },
          { id: 'plan', title: '教案生成', agent: 'lesson_plan', status: '前端预览' },
          { id: 'interaction', title: '互动设计', agent: 'classroom_interaction_design', status: '前端预览' }
        ],
        outputs: [
          { id: 'lesson', title: '教案草案', path: 'output.artifacts.lesson_plan.markdown' },
          { id: 'activities', title: '课堂活动', path: 'output.artifacts.lesson_plan.activities' },
          { id: 'materials', title: '板书与材料', path: 'output.artifacts.lesson_plan.materials' }
        ]
      }),
      makeTemplate('teacher', {
        key: 'teacher-grading',
        name: '作业批改',
        brief: '评分、错因与反馈建议',
        inputTitle: '作业内容',
        placeholder: '粘贴题目、学生答案、评分标准或希望重点关注的问题',
        domain: 'education',
        intent: 'homework_grading',
        workflowId: 'education_homework_grading_v1',
        workflowLabel: '作业批改模板流程',
        runtimeLabel: '前端预览 / 后端待接入',
        inputKey: 'homework',
        defaultText: templateDisplayPrompts['teacher-grading'],
        steps: [
          { id: 'parse', title: '答案解析', agent: 'homework_answer_parse', status: '前端预览' },
          { id: 'score', title: '评分建议', agent: 'homework_grading', status: '前端预览' },
          { id: 'feedback', title: '反馈生成', agent: 'student_feedback_generate', status: '前端预览' },
          { id: 'followup', title: '跟进练习', agent: 'practice_push', status: '前端预览' }
        ],
        outputs: [
          { id: 'score', title: '评分明细', path: 'output.artifacts.grading.score' },
          { id: 'feedback', title: '学生反馈', path: 'output.artifacts.grading.feedback' },
          { id: 'practice', title: '跟进练习', path: 'output.artifacts.grading.practice' }
        ]
      }),
      makeTemplate('teacher', {
        key: 'teacher-diagnosis',
        name: '学情诊断',
        brief: '知识掌握、薄弱点与学习路径',
        inputTitle: '学情材料',
        placeholder: '描述学生表现、错题样本、测验成绩和学习目标',
        domain: 'education',
        intent: 'student_diagnosis',
        workflowId: 'education_student_diagnosis_v1',
        workflowLabel: '学情诊断模板流程',
        runtimeLabel: '前端预览 / 后端待接入',
        inputKey: 'studentProfile',
        defaultText: templateDisplayPrompts['teacher-diagnosis'],
        steps: [
          { id: 'profile', title: '画像整理', agent: 'student_profile_parse', status: '前端预览' },
          { id: 'knowledge', title: '知识点定位', agent: 'knowledge_gap_detect', status: '前端预览' },
          { id: 'path', title: '学习路径', agent: 'learning_path_planning', status: '前端预览' },
          { id: 'report', title: '诊断报告', agent: 'progress_report_generation', status: '前端预览' }
        ],
        outputs: [
          { id: 'profile', title: '学生画像', path: 'output.artifacts.diagnosis.profile' },
          { id: 'gaps', title: '薄弱知识点', path: 'output.artifacts.diagnosis.gaps' },
          { id: 'path', title: '学习路径', path: 'output.artifacts.diagnosis.path' }
        ]
      }),
      makeTemplate('teacher', {
        key: 'teacher-error-push',
        name: '错题推送',
        brief: '错因归类、变式题与巩固计划',
        inputTitle: '错题样本',
        placeholder: '粘贴错题、学生答案、知识点标签和期望练习难度',
        domain: 'education',
        intent: 'error_question_push',
        workflowId: 'education_error_question_push_v1',
        workflowLabel: '错题推送模板流程',
        runtimeLabel: '前端预览 / 后端待接入',
        inputKey: 'wrongQuestions',
        defaultText: templateDisplayPrompts['teacher-error-push'],
        steps: [
          { id: 'classify', title: '错因归类', agent: 'error_analysis_question_push', status: '前端预览' },
          { id: 'variant', title: '变式生成', agent: 'variant_question_generate', status: '前端预览' },
          { id: 'difficulty', title: '难度分层', agent: 'difficulty_calibrate', status: '前端预览' },
          { id: 'plan', title: '巩固计划', agent: 'review_plan_generate', status: '前端预览' }
        ],
        outputs: [
          { id: 'errors', title: '错因标签', path: 'output.artifacts.error_push.error_tags' },
          { id: 'questions', title: '推送题目', path: 'output.artifacts.error_push.questions' },
          { id: 'plan', title: '复习计划', path: 'output.artifacts.error_push.plan' }
        ]
      })
    ]
  },
  {
    id: 'programmer',
    short: '程',
    name: '程序员',
    summary: '需求分析、代码生成、代码库检索与架构图',
    tone: '清晰、工程化、面向交付',
    accent: '#5169b0',
    softAccent: 'rgba(81, 105, 176, 0.12)',
    templates: [
      makeTemplate('programmer', {
        key: 'programmer-requirement',
        name: '需求分析',
        brief: '需求拆解、代码检索、生成与图示',
        inputTitle: '开发需求',
        placeholder: '描述功能目标、技术栈、代码位置、输出形式和约束',
        domain: 'programmer',
        intent: 'requirement_analysis',
        workflowId: 'programmer_requirement_analysis_v1',
        workflowLabel: '程序员需求分析流程',
        runtimeLabel: 'Pack Workflow 已定义 / 页面待接入',
        inputKey: 'requirement',
        defaultText: templateDisplayPrompts['programmer-requirement'],
        steps: [
          { id: 'requirement', title: '需求分析', agent: 'requirement_analysis', status: '前端预览' },
          { id: 'search', title: '代码检索', agent: 'codebase_semantic_search', status: '前端预览' },
          { id: 'code', title: '代码生成', agent: 'code_generation', status: '前端预览' },
          { id: 'diagram', title: '图示生成', agent: 'diagram_generation', status: '前端预览' }
        ],
        outputs: [
          { id: 'spec', title: '技术需求', path: 'output.artifacts.requirement_analysis.spec' },
          { id: 'code', title: '代码草案', path: 'output.artifacts.code_generation.patch' },
          { id: 'diagram', title: 'Mermaid 图', path: 'output.artifacts.diagram_generation.mermaid' }
        ]
      }),
      makeTemplate('programmer', {
        key: 'programmer-code',
        name: '代码生成',
        brief: '接口、组件、测试与变更说明',
        inputTitle: '代码任务',
        placeholder: '描述要实现的模块、输入输出、边界条件和测试要求',
        domain: 'programmer',
        intent: 'code_generation',
        workflowId: 'programmer_code_generation_v1',
        workflowLabel: '代码生成模板流程',
        runtimeLabel: '前端预览 / 后端待接入',
        inputKey: 'codingTask',
        defaultText: templateDisplayPrompts['programmer-code'],
        steps: [
          { id: 'context', title: '上下文整理', agent: 'code_context_collect', status: '前端预览' },
          { id: 'design', title: '实现设计', agent: 'implementation_plan', status: '前端预览' },
          { id: 'code', title: '代码生成', agent: 'code_generation', status: '前端预览' },
          { id: 'test', title: '测试建议', agent: 'test_case_generate', status: '前端预览' }
        ],
        outputs: [
          { id: 'plan', title: '实现计划', path: 'output.artifacts.code.plan' },
          { id: 'patch', title: '代码 Patch', path: 'output.artifacts.code.patch' },
          { id: 'tests', title: '测试清单', path: 'output.artifacts.code.tests' }
        ]
      }),
      makeTemplate('programmer', {
        key: 'programmer-search',
        name: '代码库检索',
        brief: '语义检索、调用链与改动建议',
        inputTitle: '检索目标',
        placeholder: '描述要查找的功能、类名、接口、错误信息或业务词',
        domain: 'programmer',
        intent: 'codebase_semantic_search',
        workflowId: 'programmer_codebase_search_v1',
        workflowLabel: '代码库检索模板流程',
        runtimeLabel: '前端预览 / 后端待接入',
        inputKey: 'searchQuery',
        defaultText: templateDisplayPrompts['programmer-search'],
        steps: [
          { id: 'query', title: '检索式生成', agent: 'search_query_expand', status: '前端预览' },
          { id: 'semantic', title: '语义检索', agent: 'codebase_semantic_search', status: '前端预览' },
          { id: 'trace', title: '调用链整理', agent: 'call_graph_trace', status: '前端预览' },
          { id: 'change', title: '改动建议', agent: 'change_point_suggest', status: '前端预览' }
        ],
        outputs: [
          { id: 'files', title: '相关文件', path: 'output.artifacts.search.files' },
          { id: 'callgraph', title: '调用链', path: 'output.artifacts.search.callgraph' },
          { id: 'changes', title: '改动点', path: 'output.artifacts.search.change_points' }
        ]
      }),
      makeTemplate('programmer', {
        key: 'programmer-diagram',
        name: '架构图生成',
        brief: '模块关系、流程图与 Mermaid 输出',
        inputTitle: '架构描述',
        placeholder: '描述系统模块、数据流、接口关系和希望生成的图类型',
        domain: 'programmer',
        intent: 'diagram_generation',
        workflowId: 'programmer_diagram_generation_v1',
        workflowLabel: '架构图生成模板流程',
        runtimeLabel: '前端预览 / 后端待接入',
        inputKey: 'diagramRequest',
        defaultText: templateDisplayPrompts['programmer-diagram'],
        steps: [
          { id: 'scope', title: '图范围识别', agent: 'diagram_scope_parse', status: '前端预览' },
          { id: 'nodes', title: '节点抽取', agent: 'architecture_node_extract', status: '前端预览' },
          { id: 'mermaid', title: 'Mermaid 生成', agent: 'diagram_generation', status: '前端预览' },
          { id: 'check', title: '语法校验', agent: 'mermaid_syntax_check', status: '前端预览' }
        ],
        outputs: [
          { id: 'nodes', title: '节点关系', path: 'output.artifacts.diagram.nodes' },
          { id: 'mermaid', title: 'Mermaid 源码', path: 'output.artifacts.diagram.mermaid' },
          { id: 'notes', title: '图示说明', path: 'output.artifacts.diagram.notes' }
        ]
      })
    ]
  },
  {
    id: 'writer',
    short: '写',
    name: '作家',
    summary: '灵感扩写、大纲生成、正文创作与人物关系',
    tone: '富有画面感、结构清楚、表达自然',
    accent: '#8a6a9f',
    softAccent: 'rgba(138, 106, 159, 0.13)',
    templates: [
      makeTemplate('writer', {
        key: 'writer-inspiration',
        name: '灵感扩写',
        brief: '种子想法、冲突和场景扩展',
        inputTitle: '灵感种子',
        placeholder: '输入一句创意、主题、角色、情绪或世界观碎片',
        domain: 'writer',
        intent: 'inspiration_expand',
        workflowId: 'writer_inspiration_expand_v1',
        workflowLabel: '灵感扩写模板流程',
        runtimeLabel: '前端预览 / 后端待接入',
        inputKey: 'inspiration',
        defaultText: templateDisplayPrompts['writer-inspiration'],
        steps: [
          { id: 'seed', title: '种子提炼', agent: 'inspiration_expand', status: '前端预览' },
          { id: 'conflict', title: '冲突生成', agent: 'conflict_generate', status: '前端预览' },
          { id: 'scene', title: '场景扩展', agent: 'scene_idea_expand', status: '前端预览' },
          { id: 'hook', title: '开篇钩子', agent: 'opening_hook_write', status: '前端预览' }
        ],
        outputs: [
          { id: 'ideas', title: '灵感清单', path: 'output.artifacts.inspiration.ideas' },
          { id: 'conflicts', title: '核心冲突', path: 'output.artifacts.inspiration.conflicts' },
          { id: 'hooks', title: '开篇钩子', path: 'output.artifacts.inspiration.hooks' }
        ]
      }),
      makeTemplate('writer', {
        key: 'writer-outline',
        name: '大纲生成',
        brief: '结构、章节和节奏规划',
        inputTitle: '故事设定',
        placeholder: '描述题材、主角、目标、冲突、篇幅和风格',
        domain: 'writer',
        intent: 'story_outline',
        workflowId: 'writer_story_outline_v1',
        workflowLabel: '作家故事大纲流程',
        runtimeLabel: 'Pack Workflow 已定义 / 页面待接入',
        inputKey: 'premise',
        defaultText: templateDisplayPrompts['writer-outline'],
        steps: [
          { id: 'premise', title: '设定整理', agent: 'premise_parse', status: '前端预览' },
          { id: 'outline', title: '大纲生成', agent: 'outline_generate', status: '前端预览' },
          { id: 'pace', title: '节奏校验', agent: 'pace_review', status: '前端预览' },
          { id: 'revision', title: '大纲优化', agent: 'outline_refine', status: '前端预览' }
        ],
        outputs: [
          { id: 'outline', title: '故事大纲', path: 'output.artifacts.outline.markdown' },
          { id: 'beats', title: '情节点', path: 'output.artifacts.outline.beats' },
          { id: 'notes', title: '修改建议', path: 'output.artifacts.outline.notes' }
        ]
      }),
      makeTemplate('writer', {
        key: 'writer-content',
        name: '正文创作',
        brief: '段落、对话和风格续写',
        inputTitle: '正文任务',
        placeholder: '输入大纲、已有片段、目标字数、叙事视角和风格要求',
        domain: 'writer',
        intent: 'content_write',
        workflowId: 'writer_content_write_v1',
        workflowLabel: '正文创作模板流程',
        runtimeLabel: '前端预览 / 后端待接入',
        inputKey: 'writingTask',
        defaultText: templateDisplayPrompts['writer-content'],
        steps: [
          { id: 'brief', title: '写作简报', agent: 'writing_brief_parse', status: '前端预览' },
          { id: 'scene', title: '场景规划', agent: 'scene_plan', status: '前端预览' },
          { id: 'draft', title: '正文生成', agent: 'content_write', status: '前端预览' },
          { id: 'polish', title: '语言润色', agent: 'prose_polish', status: '前端预览' }
        ],
        outputs: [
          { id: 'brief', title: '写作简报', path: 'output.artifacts.content.brief' },
          { id: 'draft', title: '正文草稿', path: 'output.artifacts.content.draft' },
          { id: 'polish', title: '润色建议', path: 'output.artifacts.content.polish_notes' }
        ]
      }),
      makeTemplate('writer', {
        key: 'writer-character',
        name: '人物关系',
        brief: '角色动机、关系网与冲突线',
        inputTitle: '人物设定',
        placeholder: '输入人物名单、身份、目标、秘密和关系线索',
        domain: 'writer',
        intent: 'character_relation_map',
        workflowId: 'writer_character_relation_v1',
        workflowLabel: '人物关系模板流程',
        runtimeLabel: '前端预览 / 后端待接入',
        inputKey: 'characters',
        defaultText: templateDisplayPrompts['writer-character'],
        steps: [
          { id: 'profile', title: '人物画像', agent: 'character_profile_extract', status: '前端预览' },
          { id: 'relation', title: '关系梳理', agent: 'character_relation_map', status: '前端预览' },
          { id: 'motivation', title: '动机分析', agent: 'motivation_analyze', status: '前端预览' },
          { id: 'conflict', title: '冲突线设计', agent: 'relationship_conflict_design', status: '前端预览' }
        ],
        outputs: [
          { id: 'profiles', title: '人物卡', path: 'output.artifacts.character.profiles' },
          { id: 'map', title: '关系图', path: 'output.artifacts.character.relation_map' },
          { id: 'conflicts', title: '冲突线', path: 'output.artifacts.character.conflicts' }
        ]
      })
    ]
  }
]


export const workbenchTemplateAliases: Record<string, string> = {
  'lawyer-draft': 'lawyer-document',
  draft: 'lawyer-document'
}
