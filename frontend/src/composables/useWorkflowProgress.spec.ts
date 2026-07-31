import { effectScope } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useWorkflowProgress } from './useWorkflowProgress'
import type { WorkflowProgress } from '@/services/api/workflow'

const progress = (overrides: Partial<WorkflowProgress> = {}): WorkflowProgress => ({
  taskId: 'task_1',
  runId: 'run_1',
  workflowId: 'workflow_1',
  status: 'running',
  phase: 'planning',
  message: '正在规划',
  percent: null,
  totalSteps: 0,
  pendingSteps: 0,
  runningSteps: 0,
  waitingReviewSteps: 0,
  retryingSteps: 0,
  failedSteps: 0,
  completedSteps: 0,
  cancelledSteps: 0,
  currentStepId: null,
  activeStepIds: [],
  recoveryCount: 0,
  startedAt: '2026-07-22T00:00:00Z',
  updatedAt: '2026-07-22T00:00:01Z',
  progress: 0,
  percentage: 0,
  ...overrides
})

const deferred = <T>() => {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

describe('useWorkflowProgress', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('queries immediately, then polls every two seconds with real backend values', async () => {
    const onProgressChanged = vi.fn()
    const request = vi.fn().mockResolvedValueOnce(progress()).mockResolvedValueOnce(progress({
      phase: 'executing', percent: 42.86, totalSteps: 7, completedSteps: 3
    }))
    const scope = effectScope()
    const tracker = scope.run(() => useWorkflowProgress({ request, onProgressChanged }))!

    await tracker.start('run_1')
    expect(request).toHaveBeenCalledTimes(1)
    expect(tracker.isIndeterminate.value).toBe(true)

    await vi.advanceTimersByTimeAsync(2000)
    expect(request).toHaveBeenCalledTimes(2)
    expect(tracker.percent.value).toBe(42.86)
    expect(onProgressChanged).toHaveBeenNthCalledWith(1, expect.objectContaining({ phase: 'planning' }), null)
    expect(onProgressChanged).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ phase: 'executing', percent: 42.86 }),
      expect.objectContaining({ phase: 'planning' })
    )
    scope.stop()
  })

  it('keeps a single request in flight and cancels it when the scope is disposed', async () => {
    const pending = deferred<WorkflowProgress>()
    let capturedSignal: AbortSignal | undefined
    const request = vi.fn((_runId, options) => {
      capturedSignal = options?.signal
      return pending.promise
    })
    const scope = effectScope()
    const tracker = scope.run(() => useWorkflowProgress({ request }))!
    void tracker.start('run_1')

    await vi.advanceTimersByTimeAsync(10000)
    expect(request).toHaveBeenCalledTimes(1)
    scope.stop()
    expect(capturedSignal?.aborted).toBe(true)
    pending.resolve(progress())
  })

  it.each([
    ['completed', 'completed'],
    ['failed', 'failed'],
    ['cancelled', 'cancelled']
  ] as const)('stops on terminal phase %s and notifies once', async (phase, status) => {
    const onTerminal = vi.fn()
    const request = vi.fn().mockResolvedValue(progress({ phase, status, percent: phase === 'completed' ? 100 : 50 }))
    const scope = effectScope()
    const tracker = scope.run(() => useWorkflowProgress({ request, onTerminal }))!

    await tracker.start('run_1')
    await vi.advanceTimersByTimeAsync(10000)
    expect(tracker.isTerminal.value).toBe(true)
    expect(request).toHaveBeenCalledTimes(1)
    expect(onTerminal).toHaveBeenCalledTimes(1)
    scope.stop()
  })

  it('keeps polling review and accepts an unchanged updatedAt as success', async () => {
    const review = progress({ phase: 'review', status: 'waiting_review', percent: 80 })
    const request = vi.fn().mockResolvedValue(review)
    const scope = effectScope()
    const tracker = scope.run(() => useWorkflowProgress({ request }))!

    await tracker.start('run_1')
    await vi.advanceTimersByTimeAsync(2000)
    expect(request).toHaveBeenCalledTimes(2)
    expect(tracker.isWaitingReview.value).toBe(true)
    expect(tracker.syncError.value).toBeNull()
    scope.stop()
  })

  it('preserves the last state across a transient error and clears syncError after recovery', async () => {
    const request = vi.fn()
      .mockResolvedValueOnce(progress({ phase: 'executing', percent: 25 }))
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce(progress({ phase: 'executing', percent: 50 }))
    const scope = effectScope()
    const tracker = scope.run(() => useWorkflowProgress({ request }))!

    await tracker.start('run_1')
    await vi.advanceTimersByTimeAsync(2000)
    expect(tracker.percent.value).toBe(25)
    expect(tracker.syncError.value).toContain('暂时中断')
    await vi.advanceTimersByTimeAsync(2000)
    expect(tracker.percent.value).toBe(50)
    expect(tracker.syncError.value).toBeNull()
    scope.stop()
  })

  it('uses generation and abort protection so an old Run cannot overwrite a new Run', async () => {
    const old = deferred<WorkflowProgress>()
    const request = vi.fn((runId: string) => runId === 'run_a'
      ? old.promise
      : Promise.resolve(progress({ runId: 'run_b', phase: 'executing', percent: 60 })))
    const scope = effectScope()
    const tracker = scope.run(() => useWorkflowProgress({ request }))!

    void tracker.start('run_a')
    await tracker.start('run_b')
    old.resolve(progress({ runId: 'run_a', phase: 'completed', percent: 100, status: 'completed' }))
    await Promise.resolve()

    expect(tracker.progress.value?.runId).toBe('run_b')
    expect(tracker.percent.value).toBe(60)
    tracker.reset()
    expect(tracker.progress.value).toBeNull()
    scope.stop()
  })

  it('retries a fresh 404 twice but stops immediately for a restored missing Run', async () => {
    const missing = { response: { status: 404 } }
    const request = vi.fn().mockRejectedValue(missing)
    const scope = effectScope()
    const tracker = scope.run(() => useWorkflowProgress({ request }))!

    await tracker.start('run_fresh', { fresh: true })
    await vi.advanceTimersByTimeAsync(2000)
    expect(request).toHaveBeenCalledTimes(3)
    expect(tracker.syncError.value).toContain('不存在')

    request.mockClear()
    await tracker.start('run_history', { fresh: false })
    expect(request).toHaveBeenCalledTimes(1)
    expect(tracker.isRunning.value).toBe(false)
    scope.stop()
  })
})
