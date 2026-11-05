import { describe, expect, it } from 'vitest'
import { classifyIntent, extractTaskTitle } from './intent'

describe('companion intent rules', () => {
  it.each([
    ['现在的任务进度怎么样了？', 'progress_query'],
    ['跑到哪一步了', 'progress_query'],
    ['帮我新建一个合同审查任务', 'task_dispatch'],
    ['今天好累啊', 'emotional_support'],
    ['你好，在吗？', 'small_talk'],
    ['换个皮肤吧', 'system_control']
  ])('classifies %s as %s', (text, expected) => {
    expect(classifyIntent(text).intent).toBe(expected)
  })

  it('falls back to small talk instead of blocking on unknown input', () => {
    const result = classifyIntent('随便说点什么')
    expect(result.intent).toBe('small_talk')
    expect(result.confidence).toBeLessThan(0.5)
    expect(result.needsConfirmation).toBe(false)
  })

  it('requires confirmation for task dispatch but never for chat', () => {
    expect(classifyIntent('帮我发起一个数据分析任务').needsConfirmation).toBe(true)
    expect(classifyIntent('你好').needsConfirmation).toBe(false)
  })

  it('extracts an explicit runId slot', () => {
    expect(classifyIntent('看一下 runId: run_42 的进度').slots.runId).toBe('run_42')
  })

  it('returns an empty result for blank input', () => {
    expect(classifyIntent('   ')).toMatchObject({ intent: 'unknown', confidence: 0 })
  })

  it('strips polite prefixes from a task title', () => {
    expect(extractTaskTitle('帮我新建一份季度分析报告。')).toBe('季度分析报告')
  })
})
