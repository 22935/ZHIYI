/**
 * 本地服务端 ASR 适配：把「本地小模型语音识别」伪装成 SpeechRecognition。
 *
 * 为什么需要它：Electron 的 Chromium 不带浏览器在线识别服务，
 * `webkitSpeechRecognition.start()` 必然失败（'network' / 'not-allowed'）；
 * 后端 /ai/voice/asr 用 sherpa-onnx paraformer 本地小模型离线识别。
 * 这里实现与 RecognitionLike 相同的最小接口，VoiceEngine / WakeWordListener
 * 无需任何改动即可切换到本地识别。
 *
 * 形态：
 * - 单次模式（continuous=false，手动麦克风）：说话 → 静音 1.2s 自动断句 →
 *   整段上传 → 一个 final result → onend；
 * - 常驻模式（continuous=true，语音唤醒）：每 3.5s 切一段滚动上传，
 *   每段一个 final result（resultIndex 递增，配合 newFinalTranscript 语义）。
 *
 * 纯逻辑（重采样 / PCM 编码 / 状态机）与浏览器 IO 分离，jsdom 可完整单测。
 */
import { localFetch, apiUrl } from '@/platform/api'
import type { RecognitionEventLike, RecognitionLike } from '../voice'

export const TARGET_SAMPLE_RATE = 16000
/** 静音判定：低于该 RMS 视为没在说话（安静房间底噪通常 < 0.005）。 */
export const SPEECH_RMS_THRESHOLD = 0.012
/** 单次模式：检测到语音后持续静音多久自动断句。 */
export const SILENCE_STOP_MS = 1200
/** 常驻模式：每段音频时长（识别延迟与边界截词的折中）。 */
export const SEGMENT_MS = 3500
/** 连续多少段识别失败才判定链路不可用。 */
export const MAX_SEGMENT_FAILURES = 3
const UPLOAD_TIMEOUT_MS = 15000

/** 线性插值重采样（跨 chunk 保持相位连续），16k 恒等。 */
export function createResampler(inputRate: number, outputRate: number): (chunk: Float32Array) => Float32Array {
  if (inputRate === outputRate) return (chunk) => chunk
  const ratio = inputRate / outputRate
  let position = 0
  let consumed = 0
  let tail = 0
  return (chunk: Float32Array): Float32Array => {
    const start = consumed
    const end = consumed + chunk.length
    const out: number[] = []
    while (position < end - 1) {
      const local = position - start
      const index = Math.floor(local)
      const frac = local - index
      const s0 = index < 0 ? tail : chunk[index]
      const s1 = chunk[index + 1]
      out.push(s0 + (s1 - s0) * frac)
      position += ratio
    }
    if (chunk.length > 0) tail = chunk[chunk.length - 1]
    consumed = end
    return Float32Array.from(out)
  }
}

export function floatToInt16(input: Float32Array): Int16Array {
  const out = new Int16Array(input.length)
  for (let i = 0; i < input.length; i += 1) {
    const clamped = Math.max(-1, Math.min(1, input[i]))
    out[i] = Math.round(clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff)
  }
  return out
}

export function rms(chunk: Float32Array): number {
  if (!chunk.length) return 0
  let sum = 0
  for (let i = 0; i < chunk.length; i += 1) sum += chunk[i] * chunk[i]
  return Math.sqrt(sum / chunk.length)
}

/** 采集源抽象：产出 16kHz Float32 分片，具体来源（麦克风/测试泵）可注入。 */
export interface AudioSource {
  readonly sampleRate: number
  onChunk: ((pcm: Float32Array) => void) | null
  start(): Promise<void>
  close(): void
}

interface ScriptProcessorLike {
  onaudioprocess: ((event: { inputBuffer: { getChannelData(channel: number): Float32Array } }) => void) | null
  connect(node: unknown): void
  disconnect(): void
}

interface AudioContextLike {
  readonly sampleRate: number
  createScriptProcessor(bufferSize: number, inputChannels: number, outputChannels: number): ScriptProcessorLike
  resume?(): Promise<unknown>
  close(): Promise<unknown> | void
}

/** 真实麦克风采集：getUserMedia → ScriptProcessor → 重采样 16k。 */
export async function openMicrophoneSource(): Promise<AudioSource> {
  const scope = window as unknown as {
    AudioContext?: new () => AudioContextLike
    webkitAudioContext?: new () => AudioContextLike
  }
  const media = window.navigator?.mediaDevices
  if (!media?.getUserMedia) throw new Error('no mediaDevices')
  const Ctor = scope.AudioContext || scope.webkitAudioContext
  if (!Ctor) throw new Error('no AudioContext')
  const stream = await media.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true }
  })
  const ctx = new Ctor()
  try { await ctx.resume?.() } catch { /* autoplay policies */ }
  const node = ctx.createScriptProcessor(4096, 1, 1)
  const resample = createResampler(ctx.sampleRate, TARGET_SAMPLE_RATE)
  const source: AudioSource = {
    sampleRate: TARGET_SAMPLE_RATE,
    onChunk: null,
    async start() { /* 采集在 connect 后自动开始 */ },
    close() {
      node.onaudioprocess = null
      try { node.disconnect() } catch { /* already disconnected */ }
      for (const track of stream.getTracks()) track.stop()
      void Promise.resolve(ctx.close()).catch(() => undefined)
    }
  }
  node.onaudioprocess = (event) => {
    const down = resample(event.inputBuffer.getChannelData(0))
    if (down.length) source.onChunk?.(down)
  }
  node.connect((ctx as unknown as { destination: unknown }).destination)
  return source
}

export class AsrUnavailableError extends Error {
  constructor(message = '本地语音识别模型不可用') { super(message) }
}

export interface AsrUploadResult { text: string }

/** PCM16 上传到本地后端；503 → AsrUnavailableError（模型缺失），其余 → 网络。 */
export async function uploadPcm(url: string, pcm: Uint8Array): Promise<AsrUploadResult> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), UPLOAD_TIMEOUT_MS)
  try {
    const response = await localFetch(`${url}?sample_rate=${TARGET_SAMPLE_RATE}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/octet-stream' },
      body: pcm as BodyInit,
      signal: controller.signal
    })
    if (!response.ok) {
      if (response.status === 503) throw new AsrUnavailableError()
      throw new Error(`asr http ${response.status}`)
    }
    const data = await response.json() as { text?: unknown }
    return { text: typeof data.text === 'string' ? data.text.trim() : '' }
  } finally {
    clearTimeout(timer)
  }
}

export interface ServerRecognitionDeps {
  openSource(): Promise<AudioSource>
  upload(pcm: Uint8Array): Promise<AsrUploadResult>
  now(): number
}

interface PendingSegment {
  pcm: Int16Array
  startedAt: number
}

/**
 * RecognitionLike 的本地识别实现。事件语义与浏览器保持一致：
 * 结果只在 onresult 里给，终止只经 onend；abort 丢弃未上传的音频。
 */
export class ServerSpeechRecognition implements RecognitionLike {
  lang = 'zh-CN'
  continuous = false
  interimResults = false
  onresult: ((event: RecognitionEventLike) => void) | null = null
  onerror: ((event: { error?: string }) => void) | null = null
  onend: (() => void) | null = null

  private state: 'idle' | 'recording' | 'finishing' | 'ended' = 'idle'
  private source: AudioSource | null = null
  private buffer: Int16Array[] = []
  private bufferedSamples = 0
  private speechStarted = false
  private lastVoiceAt = 0
  private segmentStartedAt = 0
  private segmentFailures = 0
  private resultBase = 0
  private queue: Promise<void> = Promise.resolve()
  /** 识别结果累积区：必须是可写的真数组（push/按下标回填），对外满足 ArrayLike 即可。 */
  private readonly results: Array<RecognitionEventLike['results'][number]> = []

  constructor(private readonly deps: ServerRecognitionDeps) {}

  start(): void {
    if (this.state !== 'idle') return
    this.state = 'recording'
    this.deps.openSource().then((source) => {
      if (this.state !== 'recording') {
        source.close()
        return
      }
      this.source = source
      this.segmentStartedAt = this.deps.now()
      source.onChunk = (chunk) => this.handleChunk(chunk)
    }).catch(() => {
      this.onerror?.({ error: 'audio-capture' })
      this.finish()
    })
  }

  stop(): void {
    if (this.state === 'idle' || this.state === 'ended') return
    // continuous 模式把当前段一并识别完再收尾；单次模式整段上传。
    this.flushSegment(this.continuous)
    this.finish()
  }

  abort(): void {
    if (this.state === 'idle' || this.state === 'ended') return
    this.buffer = []
    this.bufferedSamples = 0
    this.finish()
  }

  private handleChunk(chunk: Float32Array): void {
    if (this.state !== 'recording') return
    const energy = rms(chunk)
    const now = this.deps.now()
    if (energy >= SPEECH_RMS_THRESHOLD) {
      this.speechStarted = true
      this.lastVoiceAt = now
    }
    this.buffer.push(floatToInt16(chunk))
    this.bufferedSamples += chunk.length

    if (this.continuous) {
      if (now - this.segmentStartedAt >= SEGMENT_MS) this.flushSegment(true)
      return
    }
    // 单次模式：说过话之后持续静音即自动断句，用户不必手动停。
    if (this.speechStarted && this.lastVoiceAt > 0 && now - this.lastVoiceAt >= SILENCE_STOP_MS) {
      this.flushSegment(false)
      this.finish()
    }
  }

  /** 把已缓冲音频切段上传。keepGoing=false 时清空录音（马上要结束）。 */
  private flushSegment(keepGoing: boolean): void {
    if (!this.bufferedSamples) {
      if (keepGoing) this.segmentStartedAt = this.deps.now()
      return
    }
    const pcm = new Int16Array(this.bufferedSamples)
    let offset = 0
    for (const part of this.buffer) {
      pcm.set(part, offset)
      offset += part.length
    }
    this.buffer = []
    this.bufferedSamples = 0
    this.segmentStartedAt = this.deps.now()
    const startedAt = this.deps.now()
    const index = this.results.length
    this.results.push({ 0: { transcript: '' }, isFinal: true })
    this.queue = this.queue
      .then(async () => {
        const result = await this.deps.upload(new Uint8Array(pcm.buffer, pcm.byteOffset, pcm.byteLength))
        this.segmentFailures = 0
        this.results[index] = { 0: { transcript: result.text }, isFinal: true }
        if (this.state === 'ended') return
        if (result.text) {
          this.resultBase = index
          this.onresult?.({ resultIndex: this.resultBase, results: this.results })
        } else if (!this.continuous && this.speechStarted) {
          // 说过话但一个字都没识别出来：按浏览器语义报 no-speech。
          this.onerror?.({ error: 'no-speech' })
        }
      })
      .catch((error: unknown) => {
        if (this.state === 'ended') return
        this.segmentFailures += 1
        if (this.segmentFailures >= MAX_SEGMENT_FAILURES || !this.continuous) {
          const code = error instanceof AsrUnavailableError ? 'asr-unavailable' : 'network'
          this.onerror?.({ error: code })
          this.finish()
        }
      })
    void startedAt
  }

  private finish(): void {
    if (this.state === 'ended') return
    this.state = 'ended'
    const source = this.source
    this.source = null
    source?.close()
    source && (source.onChunk = null)
    // 等在途上传结束后再触发 onend，保证「结果先于结束」的事件顺序。
    this.queue = this.queue.then(() => {
      if (this.state !== 'ended') return
      this.onend?.()
      this.onresult = null
      this.onerror = null
      this.onend = null
    })
  }
}

/**
 * 工厂：Electron（无浏览器识别服务）与非 Chromium 浏览器的本地识别入口。
 * 返回 null 表示宿主连 getUserMedia 都没有，调用方继续走降级提示。
 */
export function createServerRecognition(): RecognitionLike | null {
  if (typeof window === 'undefined') return null
  const media = window.navigator?.mediaDevices
  if (!media?.getUserMedia) return null
  return new ServerSpeechRecognition({
    openSource: () => openMicrophoneSource(),
    upload: (pcm) => uploadPcm(apiUrl('/ai/voice/asr'), pcm),
    now: () => Date.now()
  })
}
