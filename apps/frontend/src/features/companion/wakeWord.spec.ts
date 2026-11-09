import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  WAKE_RESTART_DELAY_MS, WakeWordListener, buildWakeWords, matchWakeWord,
  newFinalTranscript, normalizeWakeText
} from './wakeWord'
import type { RecognitionEventLike, RecognitionLike } from './voice'

class FakeRecognition implements RecognitionLike {
  lang = ''
  continuous = false
  interimResults = false
  onresult: ((event: RecognitionEventLike) => void) | null = null
  onerror: ((event: { error?: string }) => void) | null = null
  onend: (() => void) | null = null
  started = 0
  stopped = 0
  constructor(readonly owner: FakeRecognition[]) { owner.push(this) }
  start(): void { this.started += 1 }
  stop(): void { this.stopped += 1; this.onend?.() }
  abort(): void { this.stopped += 1 }
}

const build = (words: readonly string[] = ['知宝', '小宝']) => {
  const created: FakeRecognition[] = []
  const wakes: string[] = []
  const blocked: string[] = []
  const listener = new WakeWordListener({
    createRecognition: () => new FakeRecognition(created),
    words: () => words,
    onWake: rest => wakes.push(rest),
    onBlocked: reason => blocked.push(reason)
  })
  return { listener, created, wakes, blocked }
}

const finalEvent = (text: string, resultIndex = 0): RecognitionEventLike => ({
  resultIndex,
  results: [{ 0: { transcript: text }, isFinal: true }]
})

afterEach(() => { vi.useRealTimers() })

describe('wake word matching', () => {
  it('derives the nickname from the persona name and dedupes extras', () => {
    expect(buildWakeWords('知宝')).toEqual(['知宝', '小宝'])
    expect(buildWakeWords('团子', ['团子', '小团'])).toEqual(['团子', '小子', '小团'])
    expect(buildWakeWords('   ')).toEqual([])
  })

  it('normalizes punctuation and case before comparing', () => {
    expect(normalizeWakeText(' 知宝，你好！ ')).toBe('知宝你好')
  })

  it('matches at the start and hands back the rest of the sentence', () => {
    expect(matchWakeWord('知宝，现在几点了？', ['知宝']))
      .toEqual({ word: '知宝', rest: '现在几点了？' })
    expect(matchWakeWord('小宝', ['知宝', '小宝'])).toEqual({ word: '小宝', rest: '' })
    // 口语语气词不该挡住唤醒
    expect(matchWakeWord('嗯，小宝 帮我记个任务', ['小宝']))
      .toEqual({ word: '小宝', rest: '帮我记个任务' })
  })

  it('ignores the wake word when it only appears mid-sentence', () => {
    expect(matchWakeWord('我昨天还跟知宝聊过这个', ['知宝'])).toBeNull()
    expect(matchWakeWord('今天天气不错', ['知宝'])).toBeNull()
    expect(matchWakeWord('', ['知宝'])).toBeNull()
  })

  it('only reads the newly finalized part of a continuous session', () => {
    const event: RecognitionEventLike = {
      resultIndex: 1,
      results: [
        { 0: { transcript: '知宝' }, isFinal: true },
        { 0: { transcript: '帮我查进度' }, isFinal: true }
      ]
    }
    expect(newFinalTranscript(event)).toBe('帮我查进度')
    expect(newFinalTranscript(finalEvent('知宝，在吗'))).toBe('知宝，在吗')
  })
})

describe('WakeWordListener lifecycle', () => {
  it('listens continuously and locks itself right after one wake', () => {
    const { listener, created, wakes } = build()
    expect(listener.start()).toBe(true)
    expect(created).toHaveLength(1)
    expect(created[0].continuous).toBe(true)
    expect(created[0].interimResults).toBe(true)
    expect(listener.active).toBe(true)

    created[0].onresult?.(finalEvent('知宝，现在几点'))
    expect(wakes).toEqual(['现在几点'])
    // 命中后自锁：同一段音频的后续结果不会再叫一次
    expect(listener.active).toBe(false)
    created[0].onresult?.(finalEvent('知宝'))
    expect(wakes).toHaveLength(1)

    listener.dispose()
  })

  it('restarts the recognition after the browser ends it', () => {
    vi.useFakeTimers()
    const { listener, created } = build()
    listener.start()
    created[0].onend?.()
    expect(created).toHaveLength(1)
    vi.advanceTimersByTime(WAKE_RESTART_DELAY_MS)
    expect(created).toHaveLength(2)
    expect(created[1].started).toBe(1)
    listener.dispose()
  })

  it('stays quiet while paused and reopens on resume', () => {
    vi.useFakeTimers()
    const { listener, created } = build()
    listener.start()
    listener.pause()
    expect(listener.active).toBe(false)
    created[0].onend?.()
    vi.advanceTimersByTime(WAKE_RESTART_DELAY_MS * 2)
    expect(created).toHaveLength(1)

    listener.resume()
    expect(created).toHaveLength(2)
    expect(listener.active).toBe(true)
    listener.dispose()
  })

  it('stops permanently when the microphone is denied', () => {
    vi.useFakeTimers()
    const { listener, created, blocked } = build()
    listener.start()
    created[0].onerror?.({ error: 'not-allowed' })
    expect(blocked).toEqual(['denied'])
    expect(listener.armedForWake).toBe(false)
    vi.advanceTimersByTime(WAKE_RESTART_DELAY_MS * 4)
    expect(created).toHaveLength(1)
  })

  it('gives up after repeated non-fatal failures instead of restarting forever', () => {
    vi.useFakeTimers()
    const { listener, created, blocked } = build()
    listener.start()
    for (let attempt = 0; attempt < 4; attempt += 1) {
      created[created.length - 1].onerror?.({ error: 'network' })
      vi.advanceTimersByTime(WAKE_RESTART_DELAY_MS)
    }
    expect(blocked).toEqual(['unavailable'])
    expect(listener.armedForWake).toBe(false)
  })

  it('reports unavailable hosts without pretending to listen', () => {
    const blocked: string[] = []
    const listener = new WakeWordListener({
      createRecognition: () => null,
      words: () => ['知宝'],
      onWake: () => undefined,
      onBlocked: reason => blocked.push(reason)
    })
    expect(listener.start()).toBe(false)
    expect(blocked).toEqual(['unavailable'])
    expect(listener.active).toBe(false)
  })
})
