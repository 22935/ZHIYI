const DEFAULT_ACG_TASK_TITLE = '未命名 ACG 任务'

type AcgTaskTitleSource = {
  title?: string | null
  workflowId?: string | null
  input?: Record<string, unknown> | null
}

const compactWhitespace = (value: string) => value.replace(/\s+/g, ' ').trim()

export const resolveAcgTaskTitle = ({ title, workflowId, input }: AcgTaskTitleSource): string => {
  const explicitName = typeof input?.taskName === 'string' ? compactWhitespace(input.taskName) : ''
  if (explicitName) return explicitName.slice(0, 80)

  const candidate = compactWhitespace(title || '')
  if (candidate && candidate.length <= 36) return candidate

  if (candidate) {
    const objectMatch = candidate.match(/(审查|复核|分析)(?:这份|该份|本份|该|本)?([^，。；：:\n]{2,24}?(?:合同|协议|材料|文档|数据|项目))/)
    if (objectMatch) return `${objectMatch[2]}${objectMatch[1]}`

    const firstClause = candidate.split(/[，。；：:\n]/, 1)[0]
      .replace(/^请(?:以[^，。；]{0,24})?/, '')
      .trim()
    if (firstClause) return firstClause.length > 30 ? `${firstClause.slice(0, 30)}…` : firstClause
  }

  return workflowId || DEFAULT_ACG_TASK_TITLE
}
