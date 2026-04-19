const normalizeKey = (value?: string) => (value || '').trim().toLowerCase()

const tryParseJson = (value: string): any | null => {
  try {
    return JSON.parse(value)
  } catch {
    return null
  }
}

const truncate = (value: string, max = 180) => {
  const text = (value || '').replace(/\s+/g, ' ').trim()
  if (text.length <= max) return text
  return `${text.slice(0, max)}...`
}

export const SKILL_NAME_ZH_MAP: Record<string, string> = {
  case_understanding: '案情理解',
  statute_retrieval: '法条检索',
  case_retrieval: '案例检索',
  evidence_analysis: '证据分析',
  limitation_calculation: '诉讼时效计算',
  jurisdiction_determination: '管辖法院确定',
  hearing_outline_generation: '庭审提纲生成',
  document_generation: '法律文书生成',
  risk_assessment: '风险评估',

  student_diagnosis: '学情诊断',
  lesson_plan_generation: '教案生成',
  homework_grading: '作业批改',
  error_analysis_question_push: '错题归因与推题',
  tutoring_qa: '智能答疑',
  learning_path_planning: '学习路径规划',
  progress_report_generation: '学情报告生成',
  classroom_interaction_design: '课堂互动设计',
  parent_communication_suggestion: '家校沟通建议',

  requirement_analysis: '需求分析',
  codebase_semantic_search: '代码库语义检索',
  code_generation: '代码生成',
  diagram_generation: '图表生成',
  code_review: '代码审查',
  debug_trace: '调试追踪',
  architecture_suggestion: '架构建议',
  unit_test_generation: '单元测试生成',

  inspiration_expand: '灵感拓展',
  outline_generate: '大纲生成',
  content_write: '正文撰写',
  character_relation_map: '人物关系图',
  outline_generation: '大纲生成',
  style_analysis: '风格分析',
  plot_logic_check: '剧情逻辑检查',
  text_polish: '文本润色',
  title_optimization: '标题优化',
  character_design: '角色设计',
  dialogue_generation: '对话生成',
  copywriting: '文案创作',
  seo_optimization: 'SEO优化'
}

const THOUGHT_ZH_BY_ACTION: Record<string, string> = {
  case_understanding: '先梳理案件事实与争议焦点。',
  statute_retrieval: '检索相关法条并建立法律依据。',
  case_retrieval: '检索类案补充裁判思路。',
  evidence_analysis: '评估证据强度与证据链缺口。',
  limitation_calculation: '计算时效起算点与截止日期。',
  jurisdiction_determination: '确定可行的管辖法院。',
  hearing_outline_generation: '输出庭审问答与举证提纲。',
  document_generation: '生成结构化法律文书草稿。',
  risk_assessment: '汇总风险并给出行动建议。',

  student_diagnosis: '先做学情诊断，定位薄弱点。',
  lesson_plan_generation: '结合学情生成可执行教案。',
  homework_grading: '按标准批改并生成反馈。',
  error_analysis_question_push: '归因错题并推送同类训练。',
  tutoring_qa: '分步骤引导答疑，帮助学生自解。',
  learning_path_planning: '规划阶段性学习路径。',
  progress_report_generation: '输出阶段学习报告。',
  classroom_interaction_design: '设计课堂提问与互动流程。',
  parent_communication_suggestion: '生成家校沟通建议。',

  requirement_analysis: '先把需求转成结构化技术规格。',
  codebase_semantic_search: '检索代码库，定位相关函数和类。',
  code_generation: '结合规格与上下文生成实现代码。',
  diagram_generation: '生成 Mermaid 图表用于展示架构/流程。',

  inspiration_expand: '先扩展创意，构建创意树。',
  outline_generate: '将创意转成结构化章节大纲。',
  content_write: '根据大纲与风格生成正文。',
  character_relation_map: '提取人物并生成关系图。'
}

const RISK_LEVEL_ZH_MAP: Record<string, string> = {
  high: '高',
  medium: '中',
  low: '低',
  unknown: '未知'
}

export const toSkillNameZh = (skill?: string) => {
  const key = normalizeKey(skill)
  return SKILL_NAME_ZH_MAP[key] || skill || '未知技能'
}

export const toActionLabelZh = (action?: string) => {
  const key = normalizeKey(action)
  if (!key) return '未指定动作'
  return toSkillNameZh(key)
}

export const toThoughtZh = (thought?: string, action?: string) => {
  const key = normalizeKey(action)
  if (THOUGHT_ZH_BY_ACTION[key]) return THOUGHT_ZH_BY_ACTION[key]
  const raw = (thought || '').trim()
  if (!raw) return '系统正在规划下一步处理动作。'
  return raw
}

export const toRiskLevelZh = (riskLevel?: string) => {
  const key = normalizeKey(riskLevel)
  return RISK_LEVEL_ZH_MAP[key] || riskLevel || '未知'
}

const summarizeLawyerObservation = (action: string, obj: any) => {
  if (action === 'evidence_analysis') {
    const evidenceCount = Array.isArray(obj?.evidence_items) ? obj.evidence_items.length : 0
    const missingCount = Array.isArray(obj?.missing_evidence) ? obj.missing_evidence.length : 0
    return `证据分析完成：识别证据 ${evidenceCount} 项，缺失 ${missingCount} 项。`
  }
  if (action === 'limitation_calculation') {
    const deadline = obj?.deadline || obj?.expiry_date || '未提供'
    const days = typeof obj?.days_remaining === 'number' ? obj.days_remaining : null
    return `时效计算完成：截止日 ${deadline}${days !== null ? `，剩余 ${days} 天` : ''}。`
  }
  if (action === 'jurisdiction_determination') {
    const courts = Array.isArray(obj?.courts)
      ? obj.courts.length
      : Array.isArray(obj?.recommended_courts)
        ? obj.recommended_courts.length
        : 0
    return `管辖分析完成：给出 ${courts} 个法院建议。`
  }
  if (action === 'hearing_outline_generation') {
    const agendaCount = Array.isArray(obj?.agenda) ? obj.agenda.length : 0
    return `庭审提纲生成完成：包含 ${agendaCount} 个关键议题。`
  }
  if (action === 'risk_assessment') {
    const level = toRiskLevelZh(obj?.risk_level || obj?.riskLevel)
    return `风险评估完成：风险等级 ${level}。`
  }
  return ''
}

const summarizeTeacherObservation = (action: string, obj: any) => {
  if (action === 'student_diagnosis') {
    const weakCount = Array.isArray(obj?.weak_points) ? obj.weak_points.length : 0
    const level = obj?.mastery_level || 'unknown'
    return `学情诊断完成：薄弱点 ${weakCount} 项，掌握等级 ${level}。`
  }
  if (action === 'lesson_plan_generation') {
    const lessonLength = String(obj?.lesson_plan || '').length
    return `教案生成完成：内容约 ${lessonLength} 字。`
  }
  if (action === 'homework_grading') {
    const score = obj?.score
    return `作业批改完成：评分 ${score ?? '--'}。`
  }
  if (action === 'error_analysis_question_push') {
    const qCount = Array.isArray(obj?.similar_questions) ? obj.similar_questions.length : 0
    return `错题归因完成：推荐同类练习 ${qCount} 题。`
  }
  if (action === 'progress_report_generation') {
    const trend = obj?.trend?.trend || 'unknown'
    return `学情报告生成完成：趋势 ${trend}。`
  }
  return ''
}

const summarizeProgrammerObservation = (action: string, obj: any) => {
  if (action === 'requirement_analysis') {
    const count = Array.isArray(obj?.functional_requirements) ? obj.functional_requirements.length : 0
    return `需求分析完成：整理功能点 ${count} 项。`
  }
  if (action === 'codebase_semantic_search') {
    const hits = Array.isArray(obj?.hits) ? obj.hits.length : 0
    return `代码检索完成：命中 ${hits} 条代码片段。`
  }
  if (action === 'code_generation') {
    const codeLength = String(obj?.code || '').length
    const language = obj?.target_language || 'unknown'
    return `代码生成完成：语言 ${language}，代码约 ${codeLength} 字符。`
  }
  if (action === 'diagram_generation') {
    const type = obj?.diagram_type || 'flowchart'
    return `图表生成完成：类型 ${type}。`
  }

  if (action === 'code_review') {
    const issueCount = Array.isArray(obj?.issues) ? obj.issues.length : 0
    return `代码审查完成：发现 ${issueCount} 个问题。`
  }
  if (action === 'debug_trace') {
    const stepCount = Array.isArray(obj?.steps) ? obj.steps.length : 0
    return `调试追踪完成：执行 ${stepCount} 步排查。`
  }
  if (action === 'architecture_suggestion') {
    const suggestCount = Array.isArray(obj?.suggestions) ? obj.suggestions.length : 0
    return `架构建议完成：提供 ${suggestCount} 条建议。`
  }
  if (action === 'unit_test_generation') {
    const caseCount = Array.isArray(obj?.test_cases) ? obj.test_cases.length : 0
    return `单元测试生成完成：生成 ${caseCount} 个用例。`
  }
  return ''
}

const summarizeWriterObservation = (action: string, obj: any) => {
  if (action === 'inspiration_expand') {
    const children = Array.isArray(obj?.creative_tree?.children) ? obj.creative_tree.children.length : 0
    return `灵感拓展完成：创意树分支 ${children} 个。`
  }
  if (action === 'outline_generate') {
    const length = String(obj?.outline_markdown || '').length
    return `大纲生成完成：内容约 ${length} 字符。`
  }
  if (action === 'content_write') {
    const length = String(obj?.content || '').length
    return `正文撰写完成：内容约 ${length} 字符。`
  }
  if (action === 'character_relation_map') {
    const nodes = Array.isArray(obj?.relation_graph?.nodes) ? obj.relation_graph.nodes.length : 0
    const edges = Array.isArray(obj?.relation_graph?.edges) ? obj.relation_graph.edges.length : 0
    return `人物关系图生成完成：${nodes} 个角色，${edges} 条关系。`
  }
  return ''
}

export const summarizeObservationZh = (action?: string, observation?: string) => {
  if (!observation) return '暂无观察结果。'

  const raw = observation.trim()
  const key = normalizeKey(action)
  const parsed = tryParseJson(raw)

  if (parsed && typeof parsed === 'object') {
    const summaries = [
      summarizeLawyerObservation(key, parsed),
      summarizeTeacherObservation(key, parsed),
      summarizeProgrammerObservation(key, parsed),
      summarizeWriterObservation(key, parsed)
    ]
    const first = summaries.find(Boolean)
    if (first) return first
    return `已返回结构化结果（${Object.keys(parsed).length} 个字段）。`
  }

  return truncate(raw, 180)
}
