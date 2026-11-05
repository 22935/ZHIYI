import { describe, expect, it, vi } from 'vitest'
import { CompanionService } from './companionService'
import { EMPTY_PROGRESS } from './types'
import type { CompanionContext, CompanionPorts, ProgressSnapshot } from './types'

const context: CompanionContext = { messages: [], progress: null, personaName: '知宝' }

const buildPorts = (overrides: Partial<CompanionPorts> = {}): CompanionPorts => ({
  chat: { reply: vi.fn(async () => '本地回复') },
  progress: {
    resolveRunId: vi.fn(() => 'run_42'),
    read: vi.fn(async () => ({ ...EMPTY_PROGRESS, runId: 'run_42', available: true }))
  },
  ...overrides
})

describe('companion service', () => {
  it('answers a progress query from the read-only projection', async () => {
    const snapshot: ProgressSnapshot = {
      ...EMPTY_PROGRESS,
      runId: 'run_42',
      available: true,
      status: 'running',
      phase: '执行中',
      percent: 50,
      completedSteps: 4,
      totalSteps: 8,
      activeStepIds: ['step_5'],
      waitingReviewSteps: 1
    }
    const ports = buildPorts({
      progress: { resolveRunId: () => 'run_42', read: vi.fn(async () => snapshot) }
    })
    const turn = await new CompanionService(ports).handle('现在的进度怎么样了？', context)
    expect(turn.intent).toBe('progress_query')
    expect(turn.reply).toContain('4/8')
    expect(turn.reply).toContain('等待人工复核')
    expect(turn.reply).not.toContain('task input')
    expect(turn.state).toBe('alert')
    expect(ports.chat.reply).not.toHaveBeenCalled()
  })

  it('uses the explicit runId slot before resolving the active run', async () => {
    const read = vi.fn(async () => ({ ...EMPTY_PROGRESS, available: true }))
    const ports = buildPorts({
      progress: { resolveRunId: vi.fn(() => 'run_active'), read }
    })
    await new CompanionService(ports).handle('看下 runId: run_7 的进度', context)
    expect(read).toHaveBeenCalledWith('run_7', undefined)
    expect(ports.progress.resolveRunId).not.toHaveBeenCalled()
  })

  it('stays quiet when no run is available', async () => {
    const ports = buildPorts({
      progress: {
        resolveRunId: () => null,
        read: vi.fn(async () => ({ ...EMPTY_PROGRESS }))
      }
    })
    const turn = await new CompanionService(ports).handle('进度如何', context)
    expect(turn.reply).toContain('还没找到')
    expect(ports.progress.read).not.toHaveBeenCalled()
  })

  it('produces a task intent card but never submits anything', async () => {
    const ports = buildPorts()
    const turn = await new CompanionService(ports).handle('帮我新建一个合同审查任务', context)
    expect(turn.intent).toBe('task_dispatch')
    expect(turn.card?.title).toBe('合同审查任务')
    expect(turn.card?.note).toContain('不会直接提交')
    expect(turn.state).toBe('thinking')
  })

  it('routes chat and emotional support through the ChatPort', async () => {
    const ports = buildPorts()
    const service = new CompanionService(ports)
    const chat = await service.handle('你好，在吗？', context)
    const comfort = await service.handle('今天好累啊', context)
    expect(ports.chat.reply).toHaveBeenCalledTimes(2)
    expect(chat.reply).toBe('本地回复')
    expect(comfort.state).toBe('happy')
  })

  it('survives a failing progress port without breaking the turn', async () => {
    const ports = buildPorts({
      progress: {
        resolveRunId: () => 'run_42',
        read: vi.fn(async () => ({ ...EMPTY_PROGRESS, runId: 'run_42' }))
      }
    })
    const turn = await new CompanionService(ports).handle('进度怎么样了', context)
    expect(turn.reply).toContain('暂时读不到')
    expect(turn.state).toBe('idle')
  })
})
