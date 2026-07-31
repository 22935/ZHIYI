import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { workflowApi, type WorkflowProgress, type WorkflowRun } from '@/services/api/workflow'
import WorkflowReviewPanel from './WorkflowReviewPanel.vue'

vi.mock('@/services/api/workflow', async importOriginal => {
  const actual = await importOriginal<typeof import('@/services/api/workflow')>()
  return { ...actual, workflowApi: { ...actual.workflowApi, submitReview: vi.fn() } }
})

const progress: WorkflowProgress = {
  taskId: 'task_1', runId: 'run_1', workflowId: 'workflow_1', status: 'waiting_review',
  phase: 'review', message: '请确认风险结论', percent: 50,
  totalSteps: 2, pendingSteps: 1, runningSteps: 0, waitingReviewSteps: 1,
  retryingSteps: 0, failedSteps: 0, completedSteps: 1, cancelledSteps: 0,
  currentStepId: 'human_review', activeStepIds: ['human_review'], recoveryCount: 0,
  startedAt: '2026-07-22T00:00:00Z', updatedAt: '2026-07-22T00:01:00Z', progress: 0.5, percentage: 50
}
const run: WorkflowRun = {
  runId: 'run_1', taskId: 'task_1', workflowId: 'workflow_1', domain: 'test',
  status: 'waiting_review', reviewMode: 'human_in_loop', input: {}, output: {},
  updatedAt: '2026-07-22T00:01:00Z', checkpoints: [], trace: [],
  steps: [{ stepId: 'human_review', name: '人工确认', agentName: 'reviewer', status: 'waiting_review' }]
}

const mountPanel = () => mount(WorkflowReviewPanel, {
  props: { runId: 'run_1', progress, run },
  global: { stubs: { 'el-icon': true } }
})

describe('WorkflowReviewPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(workflowApi.submitReview).mockResolvedValue({ ...run, status: 'running' })
  })

  it('shows only safe review context and no raw payloads', () => {
    const wrapper = mountPanel()
    expect(wrapper.text()).toContain('人工确认')
    expect(wrapper.text()).toContain('请确认风险结论')
    expect(wrapper.text()).not.toContain('input')
    expect(wrapper.text()).not.toContain('trace')
  })

  it('submits approve with optimistic concurrency fields', async () => {
    const wrapper = mountPanel()
    await wrapper.find('textarea').setValue('已核对证据')
    await wrapper.find('button.approve').trigger('click')
    await flushPromises()

    expect(workflowApi.submitReview).toHaveBeenCalledWith('run_1', expect.objectContaining({
      decision: 'approved', comment: '已核对证据', expectedStepStatus: 'waiting_review',
      expectedRunUpdatedAt: run.updatedAt, operationId: expect.any(String)
    }), expect.any(Object))
    expect(wrapper.emitted('reviewed')).toHaveLength(1)
  })

  it('supports reject through the same shared API', async () => {
    const wrapper = mountPanel()
    await wrapper.find('button.reject').trigger('click')
    await flushPromises()
    expect(workflowApi.submitReview).toHaveBeenCalledWith('run_1', expect.objectContaining({ decision: 'rejected' }), expect.any(Object))
  })

  it('exposes a 409 conflict without reporting success', async () => {
    vi.mocked(workflowApi.submitReview).mockRejectedValue({ isAxiosError: true, response: { status: 409 } })
    const wrapper = mountPanel()
    await wrapper.find('button.approve').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('该审核状态已发生变化')
    expect(wrapper.emitted('conflict')).toHaveLength(1)
    expect(wrapper.emitted('reviewed')).toBeUndefined()
  })

  it('hides actions outside waiting_review', () => {
    const wrapper = mount(WorkflowReviewPanel, {
      props: { runId: 'run_1', progress: { ...progress, phase: 'completed', status: 'completed' }, run: { ...run, status: 'completed' } },
      global: { stubs: { 'el-icon': true } }
    })
    expect(wrapper.find('.workflow-review__actions').exists()).toBe(false)
    expect(wrapper.text()).toContain('当前无需审核')
  })
})
