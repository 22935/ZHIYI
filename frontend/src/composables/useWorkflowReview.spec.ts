import { describe, expect, it, vi, beforeEach } from 'vitest'
import { workflowApi, type WorkflowRun } from '@/services/api/workflow'
import { useWorkflowReview } from './useWorkflowReview'

vi.mock('@/services/api/workflow', async importOriginal => {
  const actual = await importOriginal<typeof import('@/services/api/workflow')>()
  return {
    ...actual,
    workflowApi: { ...actual.workflowApi, submitReview: vi.fn() }
  }
})

const run = (status: WorkflowRun['status'] = 'running'): WorkflowRun => ({
  runId: 'run_1', taskId: 'task_1', workflowId: 'workflow_1', domain: 'test',
  status, reviewMode: 'human_in_loop', input: {}, output: {}, steps: [], checkpoints: [], trace: []
})
const input = { runId: 'run_1', stepId: 'review', decision: 'approved' as const, expectedRunUpdatedAt: '2026-07-22T00:00:00Z' }

describe('useWorkflowReview', () => {
  beforeEach(() => vi.clearAllMocks())

  it('submits approve with expected state and a stable operation id', async () => {
    vi.mocked(workflowApi.submitReview).mockResolvedValue(run('running'))
    const reviewed = vi.fn()
    const review = useWorkflowReview({ onReviewed: reviewed })

    const result = await review.submit(input)

    expect(result?.status).toBe('running')
    expect(workflowApi.submitReview).toHaveBeenCalledWith('run_1', expect.objectContaining({
      decision: 'approved', expectedStepStatus: 'waiting_review',
      expectedRunUpdatedAt: input.expectedRunUpdatedAt, operationId: expect.any(String)
    }), expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(reviewed).toHaveBeenCalledOnce()
  })

  it('supports reject without writing a frontend terminal state', async () => {
    vi.mocked(workflowApi.submitReview).mockResolvedValue(run('retrying'))
    const review = useWorkflowReview()

    const result = await review.submit({ ...input, decision: 'rejected' })

    expect(result?.status).toBe('retrying')
    expect(review.lastDecision.value).toBe('rejected')
  })

  it('is single-flight under repeated clicks', async () => {
    let resolveRequest: (value: WorkflowRun) => void = () => undefined
    vi.mocked(workflowApi.submitReview).mockReturnValue(new Promise(resolve => { resolveRequest = resolve }))
    const review = useWorkflowReview()

    const first = review.submit(input)
    const second = review.submit(input)
    expect(workflowApi.submitReview).toHaveBeenCalledOnce()
    await expect(second).resolves.toBeNull()
    resolveRequest(run())
    await first
  })

  it('reuses the operation id after a temporary network failure', async () => {
    vi.mocked(workflowApi.submitReview)
      .mockRejectedValueOnce({ isAxiosError: true, response: { status: 503 } })
      .mockResolvedValueOnce(run())
    const review = useWorkflowReview()

    await review.submit(input)
    const firstOperation = vi.mocked(workflowApi.submitReview).mock.calls[0][1].operationId
    await review.submit(input)
    const secondOperation = vi.mocked(workflowApi.submitReview).mock.calls[1][1].operationId

    expect(secondOperation).toBe(firstOperation)
  })

  it('maps 409 to a conflict callback and does not retry automatically', async () => {
    vi.mocked(workflowApi.submitReview).mockRejectedValue({ isAxiosError: true, response: { status: 409 } })
    const onConflict = vi.fn()
    const review = useWorkflowReview({ onConflict })

    await review.submit(input)

    expect(review.conflict.value).toBe(true)
    expect(review.error.value).toBe('该审核状态已发生变化')
    expect(onConflict).toHaveBeenCalledOnce()
    expect(workflowApi.submitReview).toHaveBeenCalledOnce()
  })

  it('keeps 404 distinct from a review conflict', async () => {
    vi.mocked(workflowApi.submitReview).mockRejectedValue({ isAxiosError: true, response: { status: 404 } })
    const review = useWorkflowReview()

    await review.submit(input)

    expect(review.conflict.value).toBe(false)
    expect(review.error.value).toContain('不存在或当前账户无权审核')
  })
})
