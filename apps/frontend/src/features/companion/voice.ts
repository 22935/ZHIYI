/**
 * Companion 语音端口：把「听（ASR）」与「说（TTS）」收敛成一个可注入的引擎。
 *
 * 边界：
 * - 纯展示层能力，不引用任何后端、ACG 或任务执行链路；
 * - 浏览器 API 全部通过 VoiceHost 注入，jsdom / 无麦克风环境可以完整单测；
 * - 语音输出（speechSynthesis）不需要任何媒体权限，Electron 的
 *   hardenSession() 全拒策略不影响朗读；
 * - 语音输入（SpeechRecognition）只在支持它的宿主可用，不可用时由 UI
 *   显式降级到指令按钮与系统语音输入，绝不假装「在听」。
 */

export type VoicePhase =
  | 'idle'
  | 'listening'
  | 'recognizing'
  | 'speaking'
  | 'unsupported'
  | 'denied'

export interface VoiceSettings {
  /** 0.5 ~ 2，默认 1 */
  rate: number
  /** 0 ~ 2，默认 1.1，稍高一点更像小伙伴 */
  pitch: number
  /** 0 ~ 1 */
  volume: number
  muted: boolean
  /**
   * 选定的系统声线（SpeechSynthesisVoice.voiceURI）。
   * 缺省或失效时按语言自动挑一个中文声线，而不是拒绝对话。
   */
  voiceURI?: string | null
}

/** 可切换的声线。只暴露展示与匹配需要的字段，不泄漏宿主对象。 */
export interface VoiceOption {
  uri: string
  name: string
  lang: string
  /** 本地合成（离线可用）；在线声线在断网或换网络时会失效。 */
  local: boolean
}

export const DEFAULT_VOICE_SETTINGS: VoiceSettings = {
  rate: 1,
  pitch: 1.12,
  volume: 0.9,
  muted: false,
  voiceURI: null
}

export interface VoiceCapabilities {
  recognition: boolean
  synthesis: boolean
}

export interface VoiceHandlers {
  onPhase(phase: VoicePhase): void
  onInterim(text: string): void
  onFinal(text: string): void
  onError(message: string): void
}

export interface RecognitionResultLike {
  0: { transcript: string }
  isFinal: boolean
}

export interface RecognitionEventLike {
  resultIndex: number
  results: ArrayLike<RecognitionResultLike>
}

export interface RecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  onresult: ((event: RecognitionEventLike) => void) | null
  onerror: ((event: { error?: string }) => void) | null
  onend: (() => void) | null
  start(): void
  stop(): void
  abort(): void
}

export interface VoiceHost {
  hasRecognition(): boolean
  createRecognition(): RecognitionLike | null
  hasSynthesis(): boolean
  /** 当前宿主的可用声线；不支持枚举时返回空数组。 */
  listVoices(): VoiceOption[]
  /** 浏览器首次 getVoices() 往往为空，需要等 voiceschanged 再取。 */
  onVoicesChanged?(callback: () => void): () => void
  speak(text: string, settings: VoiceSettings, onDone: () => void): void
  cancelSpeak(): void
}

/** 无浏览器能力时的空实现：主流程零感知，UI 会显示降级提示。 */
export const NOOP_VOICE_HOST: VoiceHost = {
  hasRecognition: () => false,
  createRecognition: () => null,
  hasSynthesis: () => false,
  listVoices: () => [],
  speak: (_text, _settings, onDone) => onDone(),
  cancelSpeak: () => undefined
}

interface SpeechRecognitionCtor {
  new (): RecognitionLike
}

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' ? value as Record<string, unknown> : {}

/** 把识别事件的二维结果收成「已定稿」与「临时字幕」两段文本。 */
export function splitTranscript(event: RecognitionEventLike): { final: string; interim: string } {
  let final = ''
  let interim = ''
  for (let i = 0; i < event.results.length; i += 1) {
    const result = event.results[i]
    const text = result?.[0]?.transcript ?? ''
    if (result?.isFinal) final += text
    else interim += text
  }
  return { final: final.trim(), interim: interim.trim() }
}

/**
 * 朗读文本清洗：去掉 markdown 符号与链接，但保留括号里的正文。
 * 括号内容常常是关键信息（例如「去工作台看看」），整段删掉会让回答
 * 听起来答非所问；只把括号换成一次停顿，语义与听感都更自然。
 */
export function toSpokenText(raw: string, limit = 160): string {
  const text = raw
    .replace(/[`*_#>]/g, '')
    .replace(/https?:\/\/\S+/g, '链接')
    // 好感度附注是给眼睛看的数值反馈，念成「加一好感」很出戏。
    .replace(/[（(]\s*\+?\d+\s*好感\s*[）)]/g, '')
    .replace(/[（(]/g, '，')
    .replace(/[）)]/g, '')
    .replace(/，+/g, '，')
    .replace(/\s+/g, ' ')
    .trim()
  return text.length > limit ? `${text.slice(0, limit)}…` : text
}

export function sanitizeVoiceSettings(raw: unknown): VoiceSettings {
  const data = asRecord(raw)
  const clamp = (value: unknown, min: number, max: number, fallback: number): number =>
    typeof value === 'number' && Number.isFinite(value)
      ? Math.min(max, Math.max(min, value)) : fallback
  return {
    rate: clamp(data.rate, 0.5, 2, DEFAULT_VOICE_SETTINGS.rate),
    pitch: clamp(data.pitch, 0, 2, DEFAULT_VOICE_SETTINGS.pitch),
    volume: clamp(data.volume, 0, 1, DEFAULT_VOICE_SETTINGS.volume),
    muted: data.muted === true,
    voiceURI: typeof data.voiceURI === 'string' && data.voiceURI.trim()
      ? data.voiceURI.trim() : null
  }
}

/**
 * 声线优先级：用户显式选定的 voiceURI → 第一个中文声线 → null（交给宿主默认）。
 * 换设备、换浏览器或系统更新都可能让原 voiceURI 消失，此时静默回落，
 * 而不是让用户面对一个哑巴伙伴。
 */
export function pickVoice<T extends { uri: string; lang: string }>(
  voices: readonly T[],
  voiceURI: string | null | undefined
): T | null {
  if (voiceURI) {
    const chosen = voices.find(voice => voice.uri === voiceURI)
    if (chosen) return chosen
  }
  return voices.find(voice => /^(zh|cmn)/i.test(voice.lang)) ?? null
}

/** 错误码转成人话；不同浏览器/宿主的 error 字符串不统一，统一收敛成四类。 */
export function describeVoiceError(code: string | undefined): string {
  switch (code) {
    case 'not-allowed':
    case 'service-not-allowed':
      return '麦克风权限没开。桌面端可以先用下面的指令按钮，或用系统语音输入（Win+H）。'
    case 'no-speech':
      return '没听见声音，再靠近一点说一次？'
    case 'network':
      return '语音识别服务暂时连不上，先用指令按钮吧。'
    case 'audio-capture':
      return '没找到可用的麦克风。'
    default:
      return '这个环境暂时听不见我说话，可以用指令按钮点我。'
  }
}

export function voiceHint(
  caps: VoiceCapabilities,
  phase: VoicePhase,
  error = ''
): string {
  if (error) return error
  if (phase === 'listening') return '在听呢，说吧～'
  if (phase === 'recognizing') return '我记一下…'
  if (phase === 'speaking') return '我在说，点一下可以打断'
  if (!caps.recognition) return '这里不能语音输入，点指令或按 Win+H 用系统语音输入'
  return '点一下说话，说完我再回答'
}

const MAX_LISTEN_MS = 15_000
const SPEAK_TIMEOUT_MS = 30_000

export function createBrowserVoiceHost(win: Window | null = typeof window === 'undefined' ? null : window): VoiceHost {
  const scope = asRecord(win)
  const Ctor = (scope.SpeechRecognition || scope.webkitSpeechRecognition) as SpeechRecognitionCtor | undefined
  const synth = typeof win !== 'undefined' && win !== null
    ? (scope.speechSynthesis as SpeechSynthesis | undefined) : undefined
  // lib.dom 把构造器挂在全局而非 Window 接口上，从同一个 scope 取更稳。
  const UtteranceCtor = scope.SpeechSynthesisUtterance as
    | (new (text: string) => SpeechSynthesisUtterance)
    | undefined

  // getVoices() 在部分宿主首次调用返回空数组，甚至可能直接抛错，统一收敛。
  const readVoices = (): SpeechSynthesisVoice[] => {
    if (!synth || typeof synth.getVoices !== 'function') return []
    try { return synth.getVoices() } catch { return [] }
  }

  const toOption = (voice: SpeechSynthesisVoice): VoiceOption => ({
    uri: voice.voiceURI,
    name: voice.name,
    lang: voice.lang,
    local: voice.localService !== false
  })

  return {
    hasRecognition() {
      return typeof Ctor === 'function'
    },
    createRecognition() {
      if (typeof Ctor !== 'function') return null
      try {
        const recognition = new Ctor()
        recognition.lang = 'zh-CN'
        recognition.continuous = false
        recognition.interimResults = true
        return recognition
      } catch {
        return null
      }
    },
    hasSynthesis() {
      return Boolean(synth && typeof UtteranceCtor === 'function')
    },
    listVoices() {
      return readVoices().map(toOption)
    },
    onVoicesChanged(callback) {
      if (!synth || typeof synth.addEventListener !== 'function') return () => undefined
      try {
        synth.addEventListener('voiceschanged', callback)
        return () => {
          try { synth.removeEventListener('voiceschanged', callback) } catch { /* detached */ }
        }
      } catch {
        return () => undefined
      }
    },
    speak(text, settings, onDone) {
      if (!synth || typeof UtteranceCtor !== 'function') { onDone(); return }
      try {
        synth.cancel()
        const utterance = new UtteranceCtor(text)
        utterance.lang = 'zh-CN'
        utterance.rate = settings.rate
        utterance.pitch = settings.pitch
        utterance.volume = settings.volume
        const voices = readVoices()
        const chosen = pickVoice(voices.map(toOption), settings.voiceURI)
        const match = chosen ? voices.find(voice => voice.voiceURI === chosen.uri) : undefined
        if (match) utterance.voice = match
        let settled = false
        const done = (): void => {
          if (settled) return
          settled = true
          clearTimeout(timer)
          onDone()
        }
        const timer = setTimeout(done, SPEAK_TIMEOUT_MS)
        utterance.onend = done
        utterance.onerror = done
        synth.speak(utterance)
      } catch {
        onDone()
      }
    },
    cancelSpeak() {
      try { synth?.cancel() } catch { /* host without synthesis */ }
    }
  }
}

/**
 * 语音引擎状态机。所有回调都允许在 dispose 之后触发（浏览器异步事件），
 * 内部用 disposed 标记吞掉，避免组件卸载后 setState。
 */
export class VoiceEngine {
  private recognition: RecognitionLike | null = null
  private listenTimer: ReturnType<typeof setTimeout> | null = null
  private disposed = false
  private phase: VoicePhase = 'idle'
  private handlers: VoiceHandlers | null = null

  constructor(private readonly host: VoiceHost = createBrowserVoiceHost()) {}

  get capabilities(): VoiceCapabilities {
    return {
      recognition: !this.disposed && this.host.hasRecognition(),
      synthesis: !this.disposed && this.host.hasSynthesis()
    }
  }

  /** 当前可选声线。宿主不支持枚举时返回空数组，UI 显示「自动」。 */
  listVoices(): VoiceOption[] {
    if (this.disposed) return []
    return this.host.listVoices()
  }

  /**
   * 供唤醒监听等常驻功能复用同一宿主（同一套能力探测与麦克风实现），
   * 与 start() 的手动聆听互不共享实例，由调用方负责错开时间。
   */
  createRecognition(): RecognitionLike | null {
    if (this.disposed) return null
    return this.host.createRecognition()
  }

  /** 订阅系统声线变化（首次加载完成、插入耳机等）；返回取消订阅函数。 */
  onVoicesChanged(callback: () => void): () => void {
    if (this.disposed) return () => undefined
    return this.host.onVoicesChanged?.(callback) ?? (() => undefined)
  }

  private setPhase(phase: VoicePhase): void {
    if (this.disposed) return
    this.phase = phase
    this.handlers?.onPhase(phase)
  }

  get currentPhase(): VoicePhase { return this.phase }

  start(handlers: VoiceHandlers): boolean {
    if (this.disposed || this.recognition) return false
    this.handlers = handlers
    const recognition = this.host.createRecognition()
    if (!recognition) {
      this.setPhase('unsupported')
      handlers.onError(describeVoiceError(undefined))
      return false
    }
    this.recognition = recognition
    recognition.onresult = (event) => {
      if (this.disposed) return
      const { final, interim } = splitTranscript(event)
      if (interim) {
        this.setPhase('listening')
        handlers.onInterim(interim)
      }
      if (final) {
        this.setPhase('recognizing')
        handlers.onFinal(final)
      }
    }
    recognition.onerror = (event) => {
      if (this.disposed) return
      const denied = event.error === 'not-allowed' || event.error === 'service-not-allowed'
      this.setPhase(denied ? 'denied' : 'idle')
      handlers.onError(describeVoiceError(event.error))
      this.clearRecognition()
    }
    recognition.onend = () => {
      if (this.disposed) return
      if (this.phase === 'listening' || this.phase === 'recognizing') this.setPhase('idle')
      this.clearRecognition()
    }
    try {
      recognition.start()
      this.setPhase('listening')
      this.listenTimer = setTimeout(() => this.stop(), MAX_LISTEN_MS)
      return true
    } catch {
      this.clearRecognition()
      this.setPhase('unsupported')
      handlers.onError(describeVoiceError(undefined))
      return false
    }
  }

  stop(): void {
    if (this.disposed) return
    const recognition = this.recognition
    this.clearRecognition()
    try { recognition?.stop() } catch { /* already stopped */ }
    if (this.phase === 'listening' || this.phase === 'recognizing') this.setPhase('idle')
  }

  private clearRecognition(): void {
    if (this.listenTimer !== null) clearTimeout(this.listenTimer)
    this.listenTimer = null
    if (this.recognition) {
      this.recognition.onresult = null
      this.recognition.onerror = null
      this.recognition.onend = null
    }
    this.recognition = null
  }

  speak(text: string, settings: VoiceSettings, onStart?: () => void, onEnd?: () => void): boolean {
    if (this.disposed || settings.muted || !text.trim()) return false
    if (!this.host.hasSynthesis()) return false
    this.setPhase('speaking')
    onStart?.()
    this.host.speak(toSpokenText(text), settings, () => {
      if (this.disposed) return
      if (this.phase === 'speaking') this.setPhase('idle')
      onEnd?.()
    })
    return true
  }

  cancelSpeak(): void {
    this.host.cancelSpeak()
    if (this.phase === 'speaking') this.setPhase('idle')
  }

  dispose(): void {
    if (this.disposed) return
    this.disposed = true
    // 不能走 stop()：它会因 disposed 提前返回，留下识别实例与超时计时器。
    const recognition = this.recognition
    this.clearRecognition()
    try { recognition?.abort() } catch { /* already finished */ }
    this.host.cancelSpeak()
    this.handlers = null
    this.phase = 'idle'
  }
}
