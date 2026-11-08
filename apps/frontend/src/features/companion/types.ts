/**
 * Companion 能力域的对外类型。
 *
 * 边界：本目录是接入层纯逻辑，只描述「展示状态 / 意图 / 端口协议」，
 * 不引用 ExecutionRuntime、ACG 节点、Mission 启动链路或任何内核符号。
 */

export type CompanionState =
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'working'
  | 'happy'
  | 'alert'
  | 'sleeping'
  | 'error'

export type SceneId =
  | 'progress_query'
  | 'task_dispatch'
  | 'small_talk'
  | 'emotional_support'
  | 'system_control'
  | 'unknown'

export type DiyShape = 'circle' | 'squircle' | 'drop' | 'star' | 'blob'

/** 用户可自定义的形象配置。全部只存本地，不上送后端。 */
export interface CompanionCustomization {
  version: 1
  name: string
  shape: DiyShape
  primary: string
  accent: string
  background: string
  /** 用户上传并压到 256px 的 dataURL；null 表示用矢量身体。 */
  image: string | null
  voice: {
    rate: number
    pitch: number
    volume: number
    muted: boolean
    /**
     * 用户选定的系统声线（SpeechSynthesisVoice.voiceURI）。
     * null 表示不指定，由宿主按语言自动挑一个中文声线。
     * voiceURI 由操作系统提供，换设备后可能失效，因此一律在读取时净化。
     */
    voiceURI: string | null
  }
  /** 自定义闲聊台词，逐条轮播；为空时回落到内置话术池。 */
  lines: string[]
  motion: boolean
}

export interface SkinManifest {
  id: string
  version: string
  label: string
  rendererType: 'inline-svg' | 'grok-svg' | 'diy-svg'
  /** 业务只发 CompanionState，由皮肤自己声明如何映射到具体形象状态。 */
  stateMap: Record<CompanionState, string>
  fallbackSkinId: string | null
  /** 仅 diy-svg 携带：渲染器据此决定形状、配色、图片与动效。 */
  custom?: CompanionCustomization
}

export interface AvatarRenderer {
  /** 动效皮肤需要异步加载引擎，因此允许返回 Promise。 */
  mount(el: HTMLElement, skin: SkinManifest): void | Promise<void>
  setState(state: CompanionState): void
  /** 朗读 / 收音时的口型与光晕动效；不支持的渲染器可忽略。 */
  setSpeaking?(speaking: boolean): void
  setListening?(listening: boolean): void
  destroy(): void
}

export interface IntentResult {
  intent: SceneId
  confidence: number
  slots: Record<string, string>
  needsConfirmation: boolean
}

export interface CompanionMessage {
  id: string
  role: 'user' | 'companion'
  content: string
  createdAt: number
}

/** 任务意图卡：只描述意图，不拼接也不提交任何任务请求体。 */
export interface TaskIntentCard {
  title: string
  domain: string
  intent: string
  note: string
}

/** 引用优先：只保留摘要字段，不携带 task input、正文或密钥。 */
export interface ProgressSnapshot {
  runId: string | null
  status: string
  phase: string
  percent: number
  completedSteps: number
  totalSteps: number
  activeStepIds: string[]
  waitingReviewSteps: number
  failedSteps: number
  message: string
  available: boolean
}

export interface CompanionContext {
  messages: CompanionMessage[]
  progress: ProgressSnapshot | null
  personaName: string
}

export interface ChatPort {
  reply(text: string, context: CompanionContext, signal?: AbortSignal): Promise<string>
}

export interface ProgressPort {
  resolveRunId(): string | null
  read(runId: string, signal?: AbortSignal): Promise<ProgressSnapshot>
}

export interface CompanionPorts {
  chat: ChatPort
  progress: ProgressPort
}

export interface CompanionTurn {
  reply: string
  state: CompanionState
  card: TaskIntentCard | null
  intent: SceneId
}

export const EMPTY_PROGRESS: ProgressSnapshot = {
  runId: null,
  status: '',
  phase: '',
  percent: 0,
  completedSteps: 0,
  totalSteps: 0,
  activeStepIds: [],
  waitingReviewSteps: 0,
  failedSteps: 0,
  message: '',
  available: false
}
