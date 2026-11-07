import type { CompanionState } from './types'

export const STATE_LABEL: Record<CompanionState, string> = {
  idle: '待机',
  listening: '聆听',
  thinking: '思考中',
  working: '跟进中',
  happy: '开心',
  alert: '需要关注',
  sleeping: '休息中',
  error: '出错了'
}

/** 数字越大越优先，避免低价值的闲时关怀盖过失败告警。 */
export const STATE_PRIORITY: Record<CompanionState, number> = {
  idle: 0,
  sleeping: 0,
  listening: 1,
  // Completion is a user-visible terminal signal and should replace routine
  // thinking/working progress while remaining below alert/error states.
  happy: 4,
  thinking: 3,
  working: 3,
  alert: 4,
  error: 5
}

/** 既有运行时事件族 → 语义状态。事件只是展示信号，运行真相仍以只读投影为准。 */
export const RUNTIME_EVENT_STATE: Record<string, CompanionState> = {
  'run.completed': 'happy',
  'run.failed': 'error',
  'run.cancelled': 'alert',
  'run.waiting_review': 'alert',
  'node.failed': 'error',
  'step.failed': 'error',
  'step.started': 'working',
  'step.succeeded': 'working',
  'node.completed': 'working',
  'planner.started': 'thinking',
  'planner.completed': 'working',
  'model.started': 'thinking',
  'model.first_token': 'thinking',
  'model.completed': 'working',
  'graph.compiled': 'working'
}

export function stateFromRuntimeEvent(eventType: string): CompanionState | null {
  return RUNTIME_EVENT_STATE[eventType] ?? null
}

/**
 * 状态归一：同优先级允许覆盖，低优先级不能打断高优先级。
 * 例如 run.failed 之后到来的普通 step.started 不该把角色切回「跟进中」。
 */
export function resolveState(current: CompanionState, incoming: CompanionState): CompanionState {
  return STATE_PRIORITY[incoming] >= STATE_PRIORITY[current] ? incoming : current
}

export interface Notice {
  id: string
  priority: number
  text: string
  state: CompanionState
  at: number
}

/**
 * 主动播报队列：去重 + 节流 + 优先级。
 * 项目没有 webhook，也不允许新建推送协议；这里只消费上游已订阅的事件。
 */
export class ProactivityQueue {
  private seen = new Set<string>()
  // A fresh queue must allow its first notice immediately. Using zero here
  // incorrectly throttles startup notices when the clock is near epoch.
  private lastSentAt = Number.NEGATIVE_INFINITY

  constructor(private readonly throttleMs = 4000, private readonly now: () => number = () => Date.now()) {}

  enqueue(notice: Notice): Notice | null {
    if (this.seen.has(notice.id)) return null
    this.seen.add(notice.id)
    const at = this.now()
    if (at - this.lastSentAt < this.throttleMs && notice.priority < 4) return null
    this.lastSentAt = at
    return notice
  }

  reset(): void {
    this.seen.clear()
    this.lastSentAt = Number.NEGATIVE_INFINITY
  }
}

/** 空闲一段时间后自动回落，避免角色长期停在思考/告警态。 */
export class IdleFallback {
  private timer: ReturnType<typeof setTimeout> | null = null

  constructor(private readonly delayMs = 5000) {}

  schedule(callback: () => void): void {
    this.clear()
    this.timer = setTimeout(callback, this.delayMs)
  }

  clear(): void {
    if (this.timer !== null) clearTimeout(this.timer)
    this.timer = null
  }
}
