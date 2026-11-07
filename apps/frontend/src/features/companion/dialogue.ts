import { classifyIntent, extractTaskTitle } from './intent'
import type {
  ChatPort, CompanionContext, ProgressSnapshot, TaskIntentCard
} from './types'

/**
 * 引用优先的进度摘要：只呈现生命周期字段，不贴 task input / 输出正文 / 密钥。
 */
export function formatProgress(snapshot: ProgressSnapshot): string {
  if (!snapshot.available) {
    return '我暂时读不到当前运行的状态。可以在工作台打开一次任务，或把 runId 告诉我，我再帮你看。'
  }
  const parts: string[] = []
  parts.push(`运行 ${snapshot.runId ?? '当前任务'} 目前是「${snapshot.phase || snapshot.status || '未知状态'}」。`)
  if (snapshot.totalSteps > 0) {
    parts.push(`已完成 ${snapshot.completedSteps}/${snapshot.totalSteps} 步（${Math.round(snapshot.percent)}%）。`)
  }
  if (snapshot.activeStepIds.length) {
    parts.push(`正在执行 ${snapshot.activeStepIds.slice(0, 3).join('、')}${snapshot.activeStepIds.length > 3 ? ' 等' : ''}。`)
  }
  if (snapshot.waitingReviewSteps > 0) parts.push(`有 ${snapshot.waitingReviewSteps} 项等待人工复核。`)
  if (snapshot.failedSteps > 0) parts.push(`有 ${snapshot.failedSteps} 个步骤失败，建议去工作台看 Trace。`)
  if (snapshot.message) parts.push(`系统提示：${snapshot.message}`)
  parts.push('详细产物与正文请在工作台按引用查看，我不会把正文直接贴在这里。')
  return parts.join('')
}

const POOL: Record<string, string[]> = {
  small_talk: [
    '我在呢。想问进度、聊两句，或者让我帮你记下一个任务都可以。',
    '嗨，我一直在这儿。今天想先看看哪个任务的进展？',
    '你好呀。我能查进度、陪你聊会儿，也能帮你把想做的事整理成一张任务卡。'
  ],
  emotional_support: [
    '听起来你今天不太轻松。先把节奏放慢一点，我陪你。',
    '辛苦了。要不要我帮你看看现在还有哪些任务在跑？先理清楚会轻松些。',
    '我在。需要安静一会儿也没关系，我不会主动打扰你。'
  ],
  system_control: [
    '好的。点角色下方的皮肤按钮就能换形象，点收起我就先退到角落。',
    '我可以安静下来。你也可以随时把我收起，位置会记在本地。'
  ],
  task_dispatch: [
    '我先把你想做的事整理成一张任务卡，确认后再交给工作台，不会替你直接发起。',
    '收到。我先只做记录和确认，真正启动任务还是由你在工作台点确认。'
  ],
  unknown: ['我没太听明白，能再说得具体一点吗？']
}

/** 本地确定性话术 Port：零网络、零模型，离线可用，便于回归测试。 */
export class LocalChatPort implements ChatPort {
  async reply(text: string, context: CompanionContext): Promise<string> {
    const intent = classifyIntent(text).intent
    const pool = POOL[intent] ?? POOL.unknown
    const index = context.messages.filter(item => item.role === 'companion').length % pool.length
    return pool[index]
  }
}

export function buildTaskCard(text: string): TaskIntentCard {
  return {
    title: extractTaskTitle(text) || '未命名任务',
    domain: '待确认',
    intent: '待确认',
    note: '此卡只描述意图。确认后将交给既有任务启动入口，本模块不会直接提交。'
  }
}
