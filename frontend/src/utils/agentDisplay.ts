export const SKILL_NAME_ZH_MAP: Record<string, string> = {
  case_understanding: '案情理解',
  statute_retrieval: '法条检索',
  case_retrieval: '判例检索',
  evidence_analysis: '证据分析',
  limitation_calculation: '诉讼时效',
  jurisdiction_determination: '管辖确定',
  hearing_outline_generation: '庭审提纲',
  document_generation: '文书生成',
  risk_assessment: '风险评估'
}

const THOUGHT_ZH_BY_ACTION: Record<string, string> = {
  case_understanding: '先完成案情梳理，提取争议焦点与关键信息缺口。',
  statute_retrieval: '根据争议焦点检索最相关法条，建立法律依据。',
  case_retrieval: '检索相似判例，为结论提供裁判实践参考。',
  evidence_analysis: '从证据目录中识别证明力、合法性和关联性缺口。',
  limitation_calculation: '计算时效起算点与截止日，识别中断或中止风险。',
  jurisdiction_determination: '结合案由和地域要素，确定可起诉法院选项。',
  hearing_outline_generation: '按开庭流程生成发问、质证和辩论提纲。',
  document_generation: '结合事实与证据生成结构化法律文书草稿。',
  risk_assessment: '评估实体与程序风险，并给出可执行建议。'
}

const RISK_LEVEL_ZH_MAP: Record<string, string> = {
  high: '高',
  medium: '中',
  low: '低',
  unknown: '未知'
}

const normalizeKey = (value?: string) => (value || '').trim().toLowerCase()

const tryParseJson = (value: string): any | null => {
  try {
    return JSON.parse(value)
  } catch {
    return null
  }
}

const truncate = (value: string, max = 140) => {
  const text = (value || '').replace(/\s+/g, ' ').trim()
  if (text.length <= max) return text
  return `${text.slice(0, max)}...`
}

const topNames = (items: any[], max = 2) => {
  return items
    .slice(0, max)
    .map(item => item?.law_name || item?.title || item?.name || item?.case_name || item?.case_no || '')
    .filter(Boolean)
}

export const toSkillNameZh = (skill?: string) => {
  const key = normalizeKey(skill)
  return SKILL_NAME_ZH_MAP[key] || skill || '未知技能'
}

export const toActionLabelZh = (action?: string) => {
  const key = normalizeKey(action)
  const zh = toSkillNameZh(key)
  if (!key) return '未指定动作'
  return zh === key ? key : `${zh}`
}

export const toThoughtZh = (thought?: string, action?: string) => {
  const key = normalizeKey(action)
  if (THOUGHT_ZH_BY_ACTION[key]) return THOUGHT_ZH_BY_ACTION[key]

  const raw = (thought || '').trim()
  if (!raw) return '系统正在规划下一步处理动作。'

  if (/first understand|case facts|legal issues/i.test(raw)) {
    return THOUGHT_ZH_BY_ACTION.case_understanding
  }
  if (/retrieve relevant statutes|legal basis/i.test(raw)) {
    return THOUGHT_ZH_BY_ACTION.statute_retrieval
  }
  if (/retrieve similar cases|reference/i.test(raw)) {
    return THOUGHT_ZH_BY_ACTION.case_retrieval
  }
  if (/evidence|proof/i.test(raw)) {
    return THOUGHT_ZH_BY_ACTION.evidence_analysis
  }
  if (/limitation|deadline|prescription/i.test(raw)) {
    return THOUGHT_ZH_BY_ACTION.limitation_calculation
  }
  if (/jurisdiction|court/i.test(raw)) {
    return THOUGHT_ZH_BY_ACTION.jurisdiction_determination
  }
  if (/hearing outline|trial/i.test(raw)) {
    return THOUGHT_ZH_BY_ACTION.hearing_outline_generation
  }
  if (/generate legal document|draft/i.test(raw)) {
    return THOUGHT_ZH_BY_ACTION.document_generation
  }
  if (/assess legal and evidence risks|risk/i.test(raw)) {
    return THOUGHT_ZH_BY_ACTION.risk_assessment
  }

  return raw
}

export const toRiskLevelZh = (riskLevel?: string) => {
  const key = normalizeKey(riskLevel)
  return RISK_LEVEL_ZH_MAP[key] || riskLevel || '未知'
}

const summarizeCaseUnderstanding = (obj: any) => {
  const facts = truncate(obj?.facts || '')
  const issues = Array.isArray(obj?.legal_issues) ? obj.legal_issues.filter(Boolean).slice(0, 3) : []
  const missing = Array.isArray(obj?.missing_info) ? obj.missing_info.filter(Boolean).length : 0

  const issueText = issues.length ? issues.join('、') : '待补充'
  const factsText = facts || '已提取基础案情信息'
  return `已完成案情结构化：争议焦点 ${issueText}；${factsText}${missing > 0 ? `；待补充信息 ${missing} 项` : ''}`
}

const summarizeStatuteRetrieval = (obj: any) => {
  const statutes = Array.isArray(obj?.statutes) ? obj.statutes : []
  const names = topNames(statutes)
  if (!statutes.length) return '法条检索已执行，当前未命中高相关法条。'
  return `已命中法条 ${statutes.length} 条${names.length ? `（示例：${names.join('、')}）` : ''}`
}

const summarizeCaseRetrieval = (obj: any) => {
  const cases = Array.isArray(obj?.cases) ? obj.cases : []
  const names = topNames(cases)
  if (!cases.length) return '判例检索已执行，当前未命中高相似案例。'
  return `已命中判例 ${cases.length} 条${names.length ? `（示例：${names.join('、')}）` : ''}`
}

const summarizeEvidenceAnalysis = (obj: any) => {
  const evidenceItems = Array.isArray(obj?.evidence_items) ? obj.evidence_items : []
  const missing = Array.isArray(obj?.missing_evidence) ? obj.missing_evidence : []
  return `证据分析完成：识别证据 ${evidenceItems.length} 项${missing.length ? `，待补证据 ${missing.length} 项` : ''}`
}

const summarizeLimitationCalculation = (obj: any) => {
  const status = obj?.status || '已计算'
  const deadline = obj?.deadline || obj?.expiry_date || ''
  const days = obj?.days_remaining
  return `时效分析完成：${status}${deadline ? `，截止 ${deadline}` : ''}${typeof days === 'number' ? `，剩余 ${days} 天` : ''}`
}

const summarizeJurisdiction = (obj: any) => {
  const courts = Array.isArray(obj?.courts)
    ? obj.courts
    : Array.isArray(obj?.recommended_courts)
      ? obj.recommended_courts
      : []
  return `管辖分析完成：提供 ${courts.length} 个法院建议。`
}

const summarizeHearingOutline = (obj: any) => {
  const agenda = Array.isArray(obj?.agenda) ? obj.agenda.length : 0
  const outline = obj?.outline_markdown || obj?.outline || ''
  return `庭审提纲已生成${agenda ? `（${agenda} 个模块）` : ''}${outline ? `，内容约 ${String(outline).length} 字` : ''}`
}

const summarizeDocumentGeneration = (obj: any) => {
  const docType = obj?.document_type || obj?.documentType || '法律文书'
  const sections = Array.isArray(obj?.sections) ? obj.sections.length : 0
  const draft = typeof obj?.draft === 'string' ? obj.draft : ''
  const draftHint = draft ? `；草稿长度约 ${draft.length} 字` : ''
  return `已生成${docType}草稿${sections > 0 ? `（${sections} 个章节）` : ''}${draftHint}`
}

const summarizeRiskAssessment = (obj: any) => {
  const level = toRiskLevelZh(obj?.risk_level || obj?.riskLevel)
  const score = obj?.risk_score ?? obj?.riskScore
  const federated = obj?.federated
  const federatedText = federated?.applied
    ? `；联邦增强已生效（节点 ${federated?.federated_nodes_count ?? 0}）`
    : ''
  return `风险评估完成：风险等级 ${level}${score !== undefined ? `，评分 ${score}` : ''}${federatedText}`
}

export const summarizeObservationZh = (action?: string, observation?: string) => {
  if (!observation) return '暂无观察结果。'

  const raw = observation.trim()
  const key = normalizeKey(action)
  const parsed = tryParseJson(raw)

  if (parsed && typeof parsed === 'object') {
    if (key === 'case_understanding') return summarizeCaseUnderstanding(parsed)
    if (key === 'statute_retrieval') return summarizeStatuteRetrieval(parsed)
    if (key === 'case_retrieval') return summarizeCaseRetrieval(parsed)
    if (key === 'evidence_analysis') return summarizeEvidenceAnalysis(parsed)
    if (key === 'limitation_calculation') return summarizeLimitationCalculation(parsed)
    if (key === 'jurisdiction_determination') return summarizeJurisdiction(parsed)
    if (key === 'hearing_outline_generation') return summarizeHearingOutline(parsed)
    if (key === 'document_generation') return summarizeDocumentGeneration(parsed)
    if (key === 'risk_assessment') return summarizeRiskAssessment(parsed)
    return `已返回结构化结果（${Object.keys(parsed).length} 个字段）。`
  }

  if (key === 'risk_assessment' && /high|medium|low/i.test(raw)) {
    const m = raw.match(/high|medium|low/i)
    if (m) return `风险评估完成：风险等级 ${toRiskLevelZh(m[0])}`
  }

  return truncate(raw, 180)
}