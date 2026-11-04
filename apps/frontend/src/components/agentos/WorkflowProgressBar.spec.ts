import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import WorkflowProgressBar from './WorkflowProgressBar.vue'
import type { WorkflowProgress } from '@/services/api/workflow'

const progress = (overrides: Partial<WorkflowProgress> = {}): WorkflowProgress => ({
  taskId: 'task_1', runId: 'run_1', workflowId: 'workflow_1', status: 'running',
  phase: 'executing', message: 'running risk review', percent: 42.86,
  totalSteps: 7, pendingSteps: 3, runningSteps: 1, waitingReviewSteps: 0,
  retryingSteps: 0, failedSteps: 0, completedSteps: 3, cancelledSteps: 0,
  currentStepId: 'risk_detect', activeStepIds: ['risk_detect'],
  startedAt: '2026-07-22T00:00:00Z', updatedAt: '2026-07-22T00:00:01Z',
  progress: 0.4286, percentage: 42.86, ...overrides
})

afterEach(() => vi.useRealTimers())

describe('WorkflowProgressBar', () => {
  it('renders indeterminate planning without inventing zero percent', () => {
    vi.useFakeTimers()
    const wrapper = mount(WorkflowProgressBar, { props: { progress: progress({ phase: 'planning', percent: null, totalSteps: 0 }) } })
    const bar = wrapper.get('[role="progressbar"]')
    expect(bar.classes()).toContain('is-indeterminate')
    expect(bar.attributes('aria-valuenow')).toBeUndefined()
    expect(wrapper.text()).not.toContain('0%')
  })

  it('renders the exact runtime-derived percent and lifecycle state', async () => {
    vi.useFakeTimers()
    const wrapper = mount(WorkflowProgressBar, { props: { progress: progress() } })
    expect(wrapper.text()).toContain('42.86%')
    expect(wrapper.get('[role="progressbar"]').attributes('aria-valuenow')).toBe('42.86')
    await wrapper.setProps({ progress: progress({ phase: 'review', status: 'waiting_review', percent: 71 }) })
    expect(wrapper.text()).toContain('71%')
    await wrapper.setProps({ progress: progress({ phase: 'failed', status: 'failed', percent: 64 }) })
    expect(wrapper.text()).toContain('64%')
    expect(wrapper.text()).not.toContain('100%')
  })

  it('escapes lifecycle messages', () => {
    vi.useFakeTimers()
    const message = '<script>alert(1)</script>'
    const wrapper = mount(WorkflowProgressBar, { props: { progress: progress({ message }) } })
    expect(wrapper.get('.workflow-progress__message').text()).toBe(message)
    expect(wrapper.find('.workflow-progress__message script').exists()).toBe(false)
  })
  it.each([
    ['已完成', null], ['执行中', progress({ phase:'failed', status:'failed', message:'old failure' })],
    [undefined, progress()], [undefined, null], ['状态待确认', null], ['已完成', progress({ phase:'executing' })]
  ])('prefers lifecycle label %s with nullable Progress', (label, snapshot) => {
    const wrapper = mount(WorkflowProgressBar, { props:{ progress:snapshot, lifecycleLabel:label } })
    expect(wrapper.get('.workflow-progress__phase').text()).toBe(label ?? (snapshot ? '执行节点':'准备任务'))
    if(label) expect(wrapper.get('.workflow-progress__message').text()).toBe(label)
    wrapper.unmount()
  })

})
