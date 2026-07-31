import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { workflowApi, type WorkflowRunSummary } from '@/services/api/workflow'
import { useWorkflowRunsStore } from './workflowRuns'

vi.mock('@/services/api/workflow', async importOriginal => {
  const actual = await importOriginal<typeof import('@/services/api/workflow')>()
  return {
    ...actual,
    workflowApi: { ...actual.workflowApi, listRuns: vi.fn() }
  }
})

const summary = (overrides: Partial<WorkflowRunSummary> = {}): WorkflowRunSummary => ({
  taskId: 'task_1', runId: 'run_1', workflowId: 'workflow_1', status: 'running',
  phase: 'executing', message: '执行中', percent: 50,
  totalSteps: 4, pendingSteps: 1, runningSteps: 1, waitingReviewSteps: 0,
  retryingSteps: 0, failedSteps: 0, completedSteps: 2, cancelledSteps: 0,
  currentStepId: 'step_3', activeStepIds: ['step_3'], recoveryCount: 0,
  startedAt: '2026-07-22T00:00:00Z', updatedAt: '2026-07-22T00:01:00Z',
  progress: 0.5, percentage: 50, source: 'chat', createdAt: '2026-07-22T00:00:00Z',
  ...overrides
})

describe('workflow run reference store', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('token', 'test-token')
    setActivePinia(createPinia())
    vi.clearAllMocks()
    vi.mocked(workflowApi.listRuns).mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 100 })
  })

  it('restores the local index and validates malformed entries', () => {
    localStorage.setItem('workflow.run.references.v1', JSON.stringify({
      run_1: { runId: 'run_1', source: 'acg', status: 'running' },
      broken: { source: 'chat' }
    }))
    const store = useWorkflowRunsStore()

    expect(store.getReference('run_1')).toEqual(expect.objectContaining({ source: 'acg', status: 'running' }))
    expect(Object.keys(store.references)).toEqual(['run_1'])
  })

  it('reads old ChatWorkflowBinding data without deleting it', () => {
    const legacy = {
      conversation_1: [{
        conversationId: 'conversation_1', messageId: 'message_1', taskId: 'task_1',
        runId: 'run_chat', workflowId: 'workflow_1', status: 'waiting_review',
        clientRequestId: 'request_1', createdAt: '2026-07-22T00:00:00Z'
      }]
    }
    localStorage.setItem('chat.workflow_bindings.v1', JSON.stringify(legacy))
    const store = useWorkflowRunsStore()

    expect(store.getByConversation('conversation_1')[0]).toEqual(expect.objectContaining({
      runId: 'run_chat', source: 'chat', messageId: 'message_1'
    }))
    expect(JSON.parse(localStorage.getItem('chat.workflow_bindings.v1') || '{}')).toEqual(legacy)
  })

  it('uses backend state over stale local state while preserving Chat navigation', () => {
    const store = useWorkflowRunsStore()
    store.register({ runId: 'run_1', source: 'chat', conversationId: 'conversation_1', status: 'running' })

    store.mergeSummaries([summary({ status: 'completed', phase: 'completed', percent: 100 })])

    expect(store.getReference('run_1')).toEqual(expect.objectContaining({
      status: 'completed', phase: 'completed', source: 'chat', conversationId: 'conversation_1'
    }))
  })

  it('keeps the original ACG source when the Run is opened in the console', () => {
    const store = useWorkflowRunsStore()
    store.register({ runId: 'run_1', source: 'acg', status: 'running' })

    store.register({ runId: 'run_1', source: 'console', status: 'waiting_review' })

    expect(store.getReference('run_1')).toEqual(expect.objectContaining({
      source: 'acg', status: 'waiting_review'
    }))
  })

  it('marks invalid references and excludes them from conversation recovery', () => {
    const store = useWorkflowRunsStore()
    store.register({ runId: 'run_1', source: 'chat', conversationId: 'conversation_1', status: 'running' })

    store.markInvalid('run_1')

    expect(store.getReference('run_1')?.invalid).toBe(true)
    expect(store.getByConversation('conversation_1')).toEqual([])
  })

  it('removes deleted references from memory and local storage', () => {
    const store = useWorkflowRunsStore()
    store.register({ runId: 'run_1', source: 'acg', status: 'completed' })

    store.removeReference('run_1')

    expect(store.getReference('run_1')).toBeUndefined()
    expect(JSON.parse(localStorage.getItem('workflow.run.references.v1') || '{}')).toEqual({})
  })

  it('bootstraps once with a single bounded nonterminal list request', async () => {
    vi.mocked(workflowApi.listRuns).mockResolvedValue({ items: [summary()], total: 1, page: 1, pageSize: 100 })
    const store = useWorkflowRunsStore()

    await Promise.all([store.bootstrap(), store.bootstrap()])

    expect(workflowApi.listRuns).toHaveBeenCalledOnce()
    expect(workflowApi.listRuns).toHaveBeenCalledWith(expect.objectContaining({
      statuses: expect.stringContaining('waiting_review'), pageSize: 100, summary: true
    }))
    expect(store.getReference('run_1')?.status).toBe('running')
  })

  it('persists only reference fields and never full Run payloads', () => {
    const store = useWorkflowRunsStore()
    store.register({
      runId: 'run_1', source: 'console', status: 'running',
      input: { secret: true }, trace: [{ payload: 'secret' }], output: { artifact: 'secret' }
    } as unknown as Parameters<typeof store.register>[0])

    const persisted = localStorage.getItem('workflow.run.references.v1') || ''
    expect(persisted).not.toContain('secret')
    expect(persisted).not.toContain('trace')
    expect(persisted).not.toContain('output')
  })
})
