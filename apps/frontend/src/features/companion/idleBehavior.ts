/**
 * 闲时行为编排：决定「什么时候该自己说句话 / 什么时候打盹」。
 *
 * 纯逻辑，时钟与随机数可注入。刻意不引入定时器：
 * 由 UI 层按固定间隔调用 observe()，卸载时一并清理，避免幽灵计时器。
 */
import type { PetMood } from './pet'
import type { CompanionState } from './types'

export interface IdleContext {
  now: number
  lastInteractionAt: number
  state: CompanionState
  mood: PetMood
  quiet: boolean
  hidden: boolean
}

export interface IdleDecision {
  line: string | null
  sleep: boolean
}

const IDLE_LINES: Record<PetMood, string[]> = {
  curious: ['你忙你的，我在这儿看着。', '想问进度随时叫我，我不用休息。', '咦，那个按钮好像亮了一下。'],
  content: ['安静一会儿也挺好。', '任务在跑，我会盯着异常。', '伸个懒腰，继续陪你。'],
  sleepy: ['有点困了，我先眯一小会儿。', '夜里别熬太晚，进度我守着。', '呼……就闭眼三分钟。'],
  excited: ['今天状态不错，要不要查查进度？', '我刚好有劲，摸摸头也可以。', '来活儿了？我准备好了。'],
  concerned: ['有个运行好像不太对劲，抽空看一眼？', '我在这儿，需要的话叫我。']
}

const SLEEP_LINES = ['……zzz', '（轻轻打了个盹）', '我先闭眼，有事叫我。']

/** 只有真正空闲的状态才允许闲聊；告警/思考/跟进中一律不插嘴。 */
const QUIET_STATES: CompanionState[] = ['idle', 'happy', 'sleeping']

export class IdleChoreographer {
  private lastLineAt = Number.NEGATIVE_INFINITY

  constructor(
    private readonly minGapMs = 120_000,
    private readonly idleAfterMs = 45_000,
    private readonly sleepAfterMs = 15 * 60_000,
    private readonly rng: () => number = Math.random
  ) {}

  observe(context: IdleContext): IdleDecision {
    const { now, lastInteractionAt, state, mood, quiet, hidden } = context
    if (quiet || hidden || !QUIET_STATES.includes(state)) return { line: null, sleep: false }
    const idleFor = Math.max(0, now - lastInteractionAt)
    const sleep = idleFor >= this.sleepAfterMs
    if (idleFor < this.idleAfterMs) return { line: null, sleep }
    if (sleep && state !== 'sleeping') {
      // 进入打盹是一次状态变化，不受普通闲聊节流限制。
      this.lastLineAt = now
      return { line: this.pick(SLEEP_LINES), sleep: true }
    }
    if (now - this.lastLineAt < this.minGapMs) return { line: null, sleep }
    if (this.rng() >= 0.35) return { line: null, sleep }
    this.lastLineAt = now
    return { line: this.pick(IDLE_LINES[mood]), sleep }
  }

  reset(): void {
    this.lastLineAt = Number.NEGATIVE_INFINITY
  }

  private pick(lines: string[]): string {
    const index = Math.min(lines.length - 1, Math.max(0, Math.floor(this.rng() * lines.length)))
    return lines[index]
  }
}
