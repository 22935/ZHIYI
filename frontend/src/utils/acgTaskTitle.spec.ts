import { describe, expect, it } from 'vitest'
import { resolveAcgTaskTitle } from './acgTaskTitle'

describe('resolveAcgTaskTitle', () => {
  it('prefers the explicit task name stored with a new Run', () => {
    expect(resolveAcgTaskTitle({
      title: '一段很长的旧目标',
      input: { taskName: '软件开发合同审查' }
    })).toBe('软件开发合同审查')
  })

  it('converts a legacy prompt title into a concise task title', () => {
    expect(resolveAcgTaskTitle({
      title: '请以 ACG 多智能体协作方式审查这份软件开发合同，强制生成差异化任务图，并完整执行后续流程。'
    })).toBe('软件开发合同审查')
  })

  it('keeps an existing concise title unchanged', () => {
    expect(resolveAcgTaskTitle({ title: '劳动合同风险复核' })).toBe('劳动合同风险复核')
  })
})
