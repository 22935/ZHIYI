import { describe, expect, it, vi } from 'vitest'
import {
  AsrUnavailableError, MAX_SEGMENT_FAILURES, SEGMENT_MS, SILENCE_STOP_MS, SPEECH_RMS_THRESHOLD,
  ServerSpeechRecognition, createResampler, createServerRecognition, floatToInt16, rms,
  type AudioSource
} from './serverAsr'
import type { RecognitionEventLike } from '../voice'

class FakeSource implements AudioSource {
  sampleRate = 16000
  onChunk: ((pcm: Float32Array) => void) | null = null
  started = false
  closed = false
  async start(): Promise<void> { this.started = true }
  close(): void { this.closed = true }
  pump(chunk: Float32Array): void { this.onChunk?.(chunk) }
}

const loud = (seconds: number): Float32Array => {
  const data = new Float32Array(Math.round(seconds * 16000))
  for (let i = 0; i < data.length; i += 1) data[i] = 0.3 * Math.sin((i / 16000) * 2 * Math.PI * 440)
  return data
}
const silence = (seconds: number): Float32Array => new Float32Array(Math.round(seconds * 16000))

interface Harness {
  recognition: ServerSpeechRecognition
  source: FakeSource
  clock: { now: number }
  uploads: Uint8Array[]
  reply: (text: string) => void
  results: RecognitionEventLike[]
  errors: string[]
  ends: number
}

const build = (options: { continuous?: boolean; failUploads?: number } = {}): Harness => {
  const source = new FakeSource()
  const clock = { now: 1_000_000 }
  const uploads: Uint8Array[] = []
  const results: RecognitionEventLike[] = []
  const errors: string[] = []
  let ends = 0
  let remaining = options.failUploads ?? 0
  const recognition = new ServerSpeechRecognition({
    openSource: async () => source,
    upload: (pcm) => {
      uploads.push(pcm)
      if (remaining > 0) {
        remaining -= 1
        return Promise.reject(new Error('boom'))
      }
      return Promise.resolve({ text: '知宝你好' })
    },
    now: () => clock.now
  })
  recognition.continuous = options.continuous === true
  recognition.onresult = (event) => results.push(event)
  recognition.onerror = (event) => errors.push(String(event.error))
  recognition.onend = () => { ends += 1 }
  const harness: Harness = {
    recognition, source, clock, uploads, results, errors, ends,
    reply: () => undefined
  }
  return harness
}

const settle = async (): Promise<void> => {
  await Promise.resolve()
  await Promise.resolve()
  await Promise.resolve()
}

describe('serverAsr 纯函数', () => {
  it('resampler：16k 恒等，48k→16k 长度正确且相位连续', () => {
    const identity = createResampler(16000, 16000)
    const chunk = new Float32Array([0.1, 0.2, 0.3])
    expect(identity(chunk)).toBe(chunk)

    const down = createResampler(48000, 16000)
    const first = down(new Float32Array(48000).fill(0.5))
    // 首块：可输出 floor((48000-1)/3) 个样本
    expect(first.length).toBeGreaterThan(15800)
    expect(first.length).toBeLessThanOrEqual(16000)
    expect([...first.slice(0, 5)]).toEqual([0.5, 0.5, 0.5, 0.5, 0.5])
    const second = down(new Float32Array(48000).fill(0.5))
    expect(second.length).toBe(16000)
  })

  it('floatToInt16 钳位与量化', () => {
    expect([...floatToInt16(new Float32Array([0, 0.5, -0.5, 2, -2]))])
      .toEqual([0, 16384, -16384, 32767, -32768])
  })

  it('rms：静音接近 0，语音超过阈值', () => {
    expect(rms(silence(0.1))).toBeLessThan(SPEECH_RMS_THRESHOLD)
    expect(rms(loud(0.1))).toBeGreaterThan(SPEECH_RMS_THRESHOLD)
  })

  it('createServerRecognition：无 mediaDevices 的宿主返回 null', () => {
    expect(createServerRecognition()).toBeNull()
  })
})

describe('ServerSpeechRecognition 单次模式', () => {
  it('说话后静音自动断句：先 onresult(final) 再 onend，音频只上传一次', async () => {
    const harness = build()
    harness.recognition.start()
    await settle()
    harness.source.pump(loud(0.4))
    harness.clock.now += 400
    harness.source.pump(silence(SILENCE_STOP_MS / 1000 + 0.1))
    harness.clock.now += SILENCE_STOP_MS + 100
    // 静音断句在下一块音频到达时判定；再泵一块触发。
    harness.source.pump(silence(0.05))
    await settle()
    await settle()

    expect(harness.uploads).toHaveLength(1)
    expect(harness.results).toHaveLength(1)
    expect(harness.results[0].results[0].isFinal).toBe(true)
    expect(harness.results[0].results[0][0].transcript).toBe('知宝你好')
    expect(harness.errors).toEqual([])
    expect(harness.ends).toBe(1)
    expect(harness.source.closed).toBe(true)
  })

  it('手动 stop()：等完在途上传再 onend（结果先于结束）', async () => {
    const harness = build()
    const order: string[] = []
    harness.recognition.onresult = () => order.push('result')
    harness.recognition.onend = () => order.push('end')
    harness.recognition.start()
    await settle()
    harness.source.pump(loud(0.5))
    harness.recognition.stop()
    await settle()
    await settle()
    expect(order).toEqual(['result', 'end'])
    expect(harness.uploads).toHaveLength(1)
  })

  it('abort()：丢弃音频不上传，只触发 onend', async () => {
    const harness = build()
    harness.recognition.start()
    await settle()
    harness.source.pump(loud(0.5))
    harness.recognition.abort()
    await settle()
    await settle()
    expect(harness.uploads).toHaveLength(0)
    expect(harness.results).toHaveLength(0)
    expect(harness.ends).toBe(1)
  })

  it('识别为空且说过话 → no-speech 错误', async () => {
    const source = new FakeSource()
    const clock = { now: 1_000_000 }
    const errors: string[] = []
    let ends = 0
    const recognition = new ServerSpeechRecognition({
      openSource: async () => source,
      upload: async () => ({ text: '' }),
      now: () => clock.now
    })
    recognition.onerror = (event) => errors.push(String(event.error))
    recognition.onend = () => { ends += 1 }
    recognition.start()
    await settle()
    source.pump(loud(0.4))
    recognition.stop()
    await settle()
    await settle()
    expect(errors).toEqual(['no-speech'])
    expect(ends).toBe(1)
  })

  it('上传失败 → network 错误并结束', async () => {
    const harness = build({ failUploads: 1 })
    harness.recognition.start()
    await settle()
    harness.source.pump(loud(0.4))
    harness.recognition.stop()
    await settle()
    await settle()
    expect(harness.errors).toEqual(['network'])
    expect(harness.ends).toBe(1)
  })

  it('模型缺失（503 语义）→ asr-unavailable', async () => {
    const source = new FakeSource()
    const clock = { now: 0 }
    const errors: string[] = []
    const recognition = new ServerSpeechRecognition({
      openSource: async () => source,
      upload: () => Promise.reject(new AsrUnavailableError()),
      now: () => clock.now
    })
    recognition.onerror = (event) => errors.push(String(event.error))
    recognition.start()
    await settle()
    source.pump(loud(0.4))
    recognition.stop()
    await settle()
    await settle()
    expect(errors).toEqual(['asr-unavailable'])
  })

  it('openSource 失败 → audio-capture', async () => {
    const recognition = new ServerSpeechRecognition({
      openSource: () => Promise.reject(new Error('no mic')),
      upload: async () => ({ text: '' }),
      now: () => 0
    })
    const errors: string[] = []
    let ends = 0
    recognition.onerror = (event) => errors.push(String(event.error))
    recognition.onend = () => { ends += 1 }
    recognition.start()
    await settle()
    await settle()
    expect(errors).toEqual(['audio-capture'])
    expect(ends).toBe(1)
  })
})

describe('ServerSpeechRecognition 常驻模式', () => {
  it('每 SEGMENT_MS 切一段：多段结果 resultIndex 递增，不提前 onend', async () => {
    const harness = build({ continuous: true })
    harness.recognition.start()
    await settle()

    harness.source.pump(loud(0.3))
    harness.clock.now += SEGMENT_MS + 100
    harness.source.pump(loud(0.3)) // 触发切段
    await settle()
    harness.clock.now += SEGMENT_MS + 100
    harness.source.pump(loud(0.3))
    await settle()
    await settle()

    expect(harness.uploads).toHaveLength(2)
    expect(harness.results).toHaveLength(2)
    expect(harness.results[0].resultIndex).toBe(0)
    expect(harness.results[1].resultIndex).toBe(1)
    expect(harness.ends).toBe(0)
    expect(harness.source.closed).toBe(false)

    harness.recognition.stop()
    await settle()
    await settle()
    expect(harness.ends).toBe(1)
    expect(harness.source.closed).toBe(true)
  })

  it(`连续 ${MAX_SEGMENT_FAILURES} 段失败才放弃，之前的失败不致命`, async () => {
    const harness = build({ continuous: true, failUploads: MAX_SEGMENT_FAILURES })
    harness.recognition.start()
    await settle()
    for (let round = 0; round < MAX_SEGMENT_FAILURES; round += 1) {
      harness.source.pump(loud(0.3))
      harness.clock.now += SEGMENT_MS + 100
      harness.source.pump(silence(0.05))
      await settle()
      await settle()
    }
    expect(harness.errors).toEqual(['network'])
    expect(harness.ends).toBe(1)
  })
})
