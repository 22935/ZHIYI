import type { IntentResult, SceneId } from './types'

/**
 * 规则层意图识别（零模型、确定性）。
 * 后续 P1 可在这一层之后接轻量 LLM 的 JSON schema 分类；模型不可用时
 * 直接回落到这里的结果，陪伴体验不被模型故障阻断。
 */
interface Rule {
  intent: SceneId
  confidence: number
  pattern: RegExp
}

const RULES: Rule[] = [
  {
    intent: 'system_control',
    confidence: 0.92,
    pattern: /(换个|切换|皮肤|形象|隐藏|收起|折叠|设置|颜色|形状|静音|别打扰)/i
  },
  {
    intent: 'progress_query',
    confidence: 0.9,
    pattern: /(进度|进展|到哪一步|跑到哪|跑得怎么样|完成没|状态如何|现在什么状态|怎么样了|还要多久|查看运行|运行到哪)/i
  },
  {
    intent: 'task_dispatch',
    confidence: 0.85,
    pattern: /(帮我|请|麻烦|替我|创建|新建|发起|启动|跑一个|安排|分发).{0,12}(任务|审查|分析|生成|写一份|做一个|执行|报告|方案|流程)|(新建|发起|分发)任务/i
  },
  {
    intent: 'emotional_support',
    confidence: 0.82,
    pattern: /(好累|累了|烦|压力|难过|焦虑|沮丧|崩溃|不开心|emo|陪我|无聊|谢谢|辛苦了|加油|抱抱)/i
  },
  {
    intent: 'small_talk',
    confidence: 0.7,
    pattern: /^(你好|您好|hi|hello|嗨|在吗|早上好|晚上好|你是谁|你会什么)/i
  }
]

const RUN_ID_PATTERN = /run[-_]?id\s*[:=]?\s*([a-z0-9_-]{4,})|#([a-z0-9_-]*run[a-z0-9_-]*)/i

export function classifyIntent(text: string): IntentResult {
  const trimmed = text.trim()
  if (!trimmed) {
    return { intent: 'unknown', confidence: 0, slots: {}, needsConfirmation: false }
  }
  const matched = RULES.find(rule => rule.pattern.test(trimmed))
  const intent: SceneId = matched?.intent ?? 'small_talk'
  const confidence = matched?.confidence ?? 0.4

  const slots: Record<string, string> = {}
  const runIdMatch = trimmed.match(RUN_ID_PATTERN)
  if (runIdMatch) slots.runId = runIdMatch[1] || runIdMatch[2] || ''

  return {
    intent,
    confidence,
    slots,
    needsConfirmation: intent === 'task_dispatch'
  }
}

/** 任务意图卡只提取标题，不推断 domain/工作流，也不拼装任何请求体。 */
export function extractTaskTitle(text: string): string {
  return text
    .replace(/^(帮我|请|麻烦你?|替我|帮我去|能不能|可以)\s*/g, '')
    .replace(/^(创建|新建|发起|启动|跑一个|安排|分发)\s*/g, '')
    .replace(/^(一个|一份|个|份)\s*/g, '')
    .replace(/[。！!？?，,]+$/g, '')
    .trim()
    .slice(0, 60)
}
