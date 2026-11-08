import { WorkflowProgressPort } from './adapters/progress'
import { buildTaskCard, formatProgress, LocalChatPort } from './dialogue'
import { classifyIntent } from './intent'
import type {
  CompanionContext, CompanionPorts, CompanionTurn, ProgressSnapshot
} from './types'

/** 默认端口装配：本地话术 + 既有只读进度投影，零新增后端接口。 */
export function createDefaultPorts(customSmallTalk: string[] = []): CompanionPorts {
  return {
    chat: new LocalChatPort(customSmallTalk),
    progress: new WorkflowProgressPort()
  }
}

function progressState(snapshot: ProgressSnapshot): CompanionTurn['state'] {
  if (!snapshot.available) return 'idle'
  if (snapshot.failedSteps > 0 || snapshot.status === 'failed') return 'error'
  if (snapshot.waitingReviewSteps > 0 || snapshot.status === 'waiting_review') return 'alert'
  if (snapshot.status === 'completed') return 'happy'
  return 'working'
}

/**
 * 薄编排：接收输入 → 判意图 → 选场景 → 产出回复与展示状态。
 * 只依赖 CompanionPorts 协议，不引用任何内核、Store 或启动链路。
 */
export class CompanionService {
  constructor(private readonly ports: CompanionPorts = createDefaultPorts()) {}

  async handle(
    text: string,
    context: CompanionContext,
    signal?: AbortSignal
  ): Promise<CompanionTurn> {
    const result = classifyIntent(text)
    const intent = result.intent

    if (intent === 'progress_query') {
      const runId = result.slots.runId || this.ports.progress.resolveRunId()
      if (!runId) {
        return {
          reply: '我还没找到正在跟进的运行。打开一个任务，或者把 runId 告诉我，我就能帮你看进度。',
          state: 'idle',
          card: null,
          intent
        }
      }
      const snapshot = await this.ports.progress.read(runId, signal)
      return { reply: formatProgress(snapshot), state: progressState(snapshot), card: null, intent }
    }

    if (intent === 'task_dispatch') {
      return {
        reply: '我先把它整理成一张任务卡。确认之后再交给工作台，我不会替你直接发起任务。',
        state: 'thinking',
        card: buildTaskCard(text),
        intent
      }
    }

    const reply = await this.ports.chat.reply(text, context, signal)
    const state = intent === 'emotional_support'
      ? 'happy'
      : intent === 'system_control' ? 'listening' : 'idle'
    return { reply, state, card: null, intent }
  }
}
