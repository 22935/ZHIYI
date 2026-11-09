/**
 * 语音唤醒：常驻一段低功耗识别会话，听到唤醒词再把话交给主流程。
 *
 * 边界：
 * - 只做「文本匹配 + 重启策略」，麦克风仍由 VoiceHost 注入，jsdom 可完整单测；
 * - 唤醒词从人设名派生，改名后自然跟着变，不写死「知宝」；
 * - 支持一句话直达：说「知宝，现在几点」时唤醒词后面的内容直接进对话，
 *   不必先唤醒再重复一遍。
 */
import { splitTranscript, type RecognitionEventLike, type RecognitionLike } from './voice'

/** 识别会在静音几百毫秒后自动 end，重启间隔留一点余量避免抢麦。 */
export const WAKE_RESTART_DELAY_MS = 600
const MAX_CONSECUTIVE_FAILURES = 3

const PUNCTUATION = /[\s，。、,.!！?？~～…·"'“”‘’：:；;]/g
const LEADING_NOISE = /^[\s，。、,.!！?？~～…·"'“”‘’：:；;]+/
/** 口语里的语气词；「嗯知宝」也算叫到了。 */
const LEADING_FILLER = /^(嗯|啊|哎|诶|欸|喂|那个)[\s，,]*/i

export interface WakeMatch {
  /** 命中的唤醒词，用于回显「我听到你叫我了」。 */
  word: string
  /** 唤醒词之后剩下的那句话，可能为空。 */
  rest: string
}

export function normalizeWakeText(raw: string): string {
  return raw.replace(PUNCTUATION, '').toLowerCase()
}

/**
 * 人设名 → 唤醒词。取名字最后一个字加「小」做昵称（知宝 → 小宝），
 * 这是中文里最自然的叫法，也让「知宝」和「小宝」都能唤醒。
 */
export function buildWakeWords(name: string, extra: readonly string[] = []): string[] {
  const base = name.trim()
  const words = new Set<string>()
  if (base) {
    words.add(base)
    const tail = base.slice(-1)
    if (tail) words.add(`小${tail}`)
  }
  for (const item of extra) {
    const value = item.trim()
    if (value) words.add(value)
  }
  return [...words]
}

/**
 * 命中判定：唤醒词必须出现在句首（可带一个语气词）。
 * 不做全文搜索——伙伴在听的时候用户也可能在跟别人说话，
 * 「我昨天跟知宝聊过」不该把面板叫起来。
 */
export function matchWakeWord(transcript: string, words: readonly string[]): WakeMatch | null {
  const leading = transcript.replace(LEADING_NOISE, '').replace(LEADING_FILLER, '')
  if (!leading) return null
  const normalized = normalizeWakeText(leading)
  for (const word of words) {
    const normalizedWord = normalizeWakeText(word)
    // 唤醒词本身带标点会让「归一化长度」与原文长度错位；直接跳过这种脏配置。
    if (!normalizedWord || normalizedWord.length !== word.trim().length) continue
    if (!normalized.startsWith(normalizedWord)) continue
    const rest = leading.slice(normalizedWord.length).replace(LEADING_NOISE, '')
    return { word, rest }
  }
  return null
}

/**
 * 只取本轮新增的定稿结果。continuous 模式下 results 会累积，
 * 用 splitTranscript 会把上一句再匹配一遍，导致一次唤醒触发两次。
 */
export function newFinalTranscript(event: RecognitionEventLike): string {
  let text = ''
  const start = Math.max(0, event.resultIndex || 0)
  for (let index = start; index < event.results.length; index += 1) {
    const result = event.results[index]
    if (result?.isFinal) text += result[0]?.transcript ?? ''
  }
  return text.trim()
}

/** 保留给宿主做「唤醒后把整句交给对话」时的兜底清洗。 */
export function wakeTranscript(event: RecognitionEventLike): string {
  const { final } = splitTranscript(event)
  return final || newFinalTranscript(event)
}

export interface WakeWordOptions {
  createRecognition(): RecognitionLike | null
  /** 每次比对时现取，改名后无需重建监听器。 */
  words(): readonly string[]
  onWake(rest: string): void
  onBlocked?(reason: 'denied' | 'unavailable'): void
}

/**
 * 常驻监听器。浏览器不会让一次识别永远活着，因此 onend 必须自动重启；
 * 但重启要能在「用户在说话 / 伙伴在朗读 / 免打扰」时立刻停手，
 * 否则会出现自己念自己、或与手动麦克风抢同一路音频。
 */
export class WakeWordListener {
  private recognition: RecognitionLike | null = null
  private timer: ReturnType<typeof setTimeout> | null = null
  private armed = false
  private paused = false
  private failures = 0

  constructor(private readonly options: WakeWordOptions) {}

  /** 真正在监听：已布防且未被暂停。 */
  get active(): boolean {
    return this.armed && !this.paused
  }

  get armedForWake(): boolean {
    return this.armed
  }

  start(): boolean {
    if (this.armed && !this.paused) return true
    this.armed = true
    this.paused = false
    this.failures = 0
    return this.open()
  }

  pause(): void {
    if (!this.armed) return
    this.paused = true
    this.teardown()
  }

  resume(): void {
    if (!this.armed || !this.paused) return
    this.paused = false
    this.open()
  }

  stop(): void {
    this.armed = false
    this.paused = false
    this.teardown()
  }

  dispose(): void {
    this.stop()
  }

  private open(): boolean {
    if (!this.armed || this.paused || this.recognition) return false
    const recognition = this.options.createRecognition()
    if (!recognition) {
      this.armed = false
      this.options.onBlocked?.('unavailable')
      return false
    }
    this.recognition = recognition
    recognition.continuous = true
    recognition.interimResults = true
    recognition.onresult = (event) => {
      const final = newFinalTranscript(event)
      if (!final) return
      // 真正听到一句话才算这次会话可用；否则「启动即报错」会无限重启。
      this.failures = 0
      const match = matchWakeWord(final, this.options.words())
      if (!match) return
      // 自锁：命中后立即暂停，避免同一段音频的后续 final 二次触发。
      this.paused = true
      this.teardown()
      this.options.onWake(match.rest)
    }
    recognition.onerror = (event) => {
      const denied = event.error === 'not-allowed' || event.error === 'service-not-allowed'
      this.teardown()
      if (denied) {
        this.armed = false
        this.options.onBlocked?.('denied')
        return
      }
      this.failures += 1
      if (this.failures > MAX_CONSECUTIVE_FAILURES) {
        this.armed = false
        this.options.onBlocked?.('unavailable')
        return
      }
      this.scheduleRestart()
    }
    recognition.onend = () => {
      this.teardown()
      this.scheduleRestart()
    }
    try {
      recognition.start()
      return true
    } catch {
      this.teardown()
      this.armed = false
      this.options.onBlocked?.('unavailable')
      return false
    }
  }

  private scheduleRestart(): void {
    if (!this.armed || this.paused || this.timer !== null) return
    this.timer = setTimeout(() => {
      this.timer = null
      this.open()
    }, WAKE_RESTART_DELAY_MS)
  }

  private teardown(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer)
      this.timer = null
    }
    const recognition = this.recognition
    this.recognition = null
    if (!recognition) return
    recognition.onresult = null
    recognition.onerror = null
    recognition.onend = null
    try { recognition.abort() } catch { /* already finished */ }
  }
}
