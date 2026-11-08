import { describe, expect, it, vi } from 'vitest'
import {
  DEFAULT_VOICE_SETTINGS, NOOP_VOICE_HOST, VoiceEngine, describeVoiceError,
  sanitizeVoiceSettings, splitTranscript, toSpokenText, voiceHint,
  type RecognitionEventLike, type RecognitionLike, type VoiceHost, type VoiceSettings
} from './voice'

class FakeRecognition implements RecognitionLike {
  lang = ''
  continuous = false
  interimResults = false
  onresult: ((event: RecognitionEventLike) => void) | null = null
  onerror: ((event: { error?: string }) => void) | null = null
  onend: (() => void) | null = null
  started = false
  stopped = false
  start(): void { this.started = true }
  stop(): void { this.stopped = true; this.onend?.() }
  abort(): void { this.stopped = true }
}

interface Harness {
  host: VoiceHost
  recognition: FakeRecognition
  spoken: { text: string; settings: VoiceSettings }[]
  cancel: ReturnType<typeof vi.fn>
}

const build = (options: { recognition?: boolean; synthesis?: boolean } = {}): Harness => {
  const recognition = new FakeRecognition()
  const spoken: { text: string; settings: VoiceSettings }[] = []
  const cancel = vi.fn()
  const host: VoiceHost = {
    hasRecognition: () => options.recognition !== false,
    createRecognition: () => {
      if (options.recognition === false) return null
      recognition.lang = 'zh-CN'
      recognition.continuous = false
      recognition.interimResults = true
      return recognition
    },
    hasSynthesis: () => options.synthesis !== false,
    speak: (text, settings, onDone) => {
      spoken.push({ text, settings })
      onDone()
    },
    cancelSpeak: cancel
  }
  return { host, recognition, spoken, cancel }
}

const resultEvent = (entries: { transcript: string; isFinal: boolean }[]): RecognitionEventLike => ({
  resultIndex: 0,
  results: entries.map(item => ({ 0: { transcript: item.transcript }, isFinal: item.isFinal }))
})

describe('voice helpers', () => {
  it('splits interim and final transcript', () => {
    expect(splitTranscript(resultEvent([
      { transcript: '帮我看看', isFinal: true },
      { transcript: '进度', isFinal: false }
    ]))).toEqual({ final: '帮我看看', interim: '进度' })
  })

  it('keeps parenthetical content, cleans markdown and limits length', () => {
    expect(toSpokenText('我先整理成任务卡（确认后再交给工作台），不会替你发起。'))
      .toBe('我先整理成任务卡，确认后再交给工作台，不会替你发起。')
    expect(toSpokenText('访问 `https://example.com/a` 查看 *详情*')).toContain('链接')
    // 养成数值只在气泡里显示，不该被念出来。
    expect(toSpokenText('被摸到头啦（+1 好感）')).toBe('被摸到头啦')
    expect(toSpokenText('啊'.repeat(300), 20)).toHaveLength(21)
  })

  it('clamps voice settings and ignores wrong types', () => {
    expect(sanitizeVoiceSettings({ rate: 99, pitch: -3, volume: 0.4, muted: 'yes' }))
      .toEqual({ rate: 2, pitch: 0, volume: 0.4, muted: false })
    expect(sanitizeVoiceSettings(null)).toEqual(DEFAULT_VOICE_SETTINGS)
  })

  it('explains permission denial in plain Chinese', () => {
    expect(describeVoiceError('not-allowed')).toContain('麦克风权限')
    expect(describeVoiceError('no-speech')).toContain('没听见')
    expect(describeVoiceError(undefined)).toContain('指令按钮')
  })

  it('never claims to be listening when recognition is unavailable', () => {
    const caps = { recognition: false, synthesis: true }
    expect(voiceHint(caps, 'idle')).toContain('不能语音输入')
    expect(voiceHint(caps, 'listening', '')).toContain('在听')
    expect(voiceHint(caps, 'idle', '出错了')).toBe('出错了')
  })
})

describe('VoiceEngine', () => {
  it('reports capabilities and keeps TTS usable without a microphone', () => {
    const { host } = build({ recognition: false })
    const engine = new VoiceEngine(host)
    expect(engine.capabilities).toEqual({ recognition: false, synthesis: true })
    engine.dispose()
  })

  it('starts recognition, streams interim text and delivers the final sentence', () => {
    const { host, recognition } = build()
    const engine = new VoiceEngine(host)
    const phases: string[] = []
    const interims: string[] = []
    const finals: string[] = []
    expect(engine.start({
      onPhase: phase => phases.push(phase),
      onInterim: text => interims.push(text),
      onFinal: text => finals.push(text),
      onError: () => undefined
    })).toBe(true)
    expect(recognition.started).toBe(true)
    expect(recognition.lang).toBe('zh-CN')

    recognition.onresult?.(resultEvent([{ transcript: '查一下', isFinal: false }]))
    recognition.onresult?.(resultEvent([
      { transcript: '查一下进度', isFinal: true }
    ]))
    expect(interims).toEqual(['查一下'])
    expect(finals).toEqual(['查一下进度'])
    expect(phases).toContain('recognizing')
    engine.dispose()
  })

  it('falls back to unsupported instead of pretending to listen', () => {
    const { host } = build({ recognition: false })
    const engine = new VoiceEngine(host)
    const errors: string[] = []
    const phases: string[] = []
    expect(engine.start({
      onPhase: phase => phases.push(phase),
      onInterim: () => undefined,
      onFinal: () => undefined,
      onError: message => errors.push(message)
    })).toBe(false)
    expect(phases).toContain('unsupported')
    expect(errors[0]).toContain('指令按钮')
    engine.dispose()
  })

  it('turns microphone denial into a denied phase and a human hint', () => {
    const { host, recognition } = build()
    const engine = new VoiceEngine(host)
    const phases: string[] = []
    const errors: string[] = []
    engine.start({
      onPhase: phase => phases.push(phase),
      onInterim: () => undefined,
      onFinal: () => undefined,
      onError: message => errors.push(message)
    })
    recognition.onerror?.({ error: 'not-allowed' })
    expect(phases).toContain('denied')
    expect(errors[0]).toContain('麦克风权限')
    engine.dispose()
  })

  it('speaks with settings, then returns to idle', () => {
    const { host, spoken } = build()
    const engine = new VoiceEngine(host)
    const onStart = vi.fn()
    const onEnd = vi.fn()
    expect(engine.speak('我暂时读不到状态（去工作台看看）', {
      rate: 1.2, pitch: 1.4, volume: 0.5, muted: false
    }, onStart, onEnd)).toBe(true)
    expect(spoken[0].text).toBe('我暂时读不到状态，去工作台看看')
    expect(spoken[0].settings.rate).toBe(1.2)
    expect(onStart).toHaveBeenCalledOnce()
    expect(onEnd).toHaveBeenCalledOnce()
    expect(engine.currentPhase).toBe('idle')
    engine.dispose()
  })

  it('stays silent when muted, when synthesis is missing or after cancel', () => {
    const { host, spoken, cancel } = build()
    const engine = new VoiceEngine(host)
    const settings = { rate: 1, pitch: 1, volume: 1, muted: true }
    expect(engine.speak('你好', settings)).toBe(false)
    expect(spoken).toHaveLength(0)
    expect(engine.speak('你好', { ...settings, muted: false })).toBe(true)
    engine.cancelSpeak()
    expect(cancel).toHaveBeenCalled()
    engine.dispose()

    const silent = new VoiceEngine(NOOP_VOICE_HOST)
    expect(silent.capabilities).toEqual({ recognition: false, synthesis: false })
    expect(silent.speak('你好', { ...settings, muted: false })).toBe(false)
    silent.dispose()
  })

  it('ignores late browser callbacks after dispose', () => {
    const { host, recognition } = build()
    const engine = new VoiceEngine(host)
    const onFinal = vi.fn()
    engine.start({
      onPhase: () => undefined,
      onInterim: () => undefined,
      onFinal,
      onError: () => undefined
    })
    engine.dispose()
    recognition.onresult?.(resultEvent([{ transcript: '晚到的结果', isFinal: true }]))
    expect(onFinal).not.toHaveBeenCalled()
    expect(() => engine.stop()).not.toThrow()
  })
})
