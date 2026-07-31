import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import WorkflowProgressBar from './WorkflowProgressBar.vue'
import type { WorkflowProgress } from '@/services/api/workflow'

const makeProgress = (overrides: Partial<WorkflowProgress> = {}): WorkflowProgress => ({
  taskId: 'task_1', runId: 'run_1', workflowId: 'workflow_1', status: 'running',
  phase: 'executing', message: '正在执行风险识别', percent: 42.86,
  totalSteps: 7, pendingSteps: 3, runningSteps: 1, waitingReviewSteps: 0,
  retryingSteps: 0, failedSteps: 0, completedSteps: 3, cancelledSteps: 0,
  currentStepId: 'risk_detect', activeStepIds: ['risk_detect'], recoveryCount: 0,
  startedAt: '2026-07-22T00:00:00Z', updatedAt: '2026-07-22T00:00:01Z',
  progress: 0.4286, percentage: 42.86,
  ...overrides
})

afterEach(() => vi.useRealTimers())

describe('WorkflowProgressBar', () => {
  it('renders indeterminate planning without a fake 0% and with accessible text', () => {
    vi.useFakeTimers()
    const wrapper = mount(WorkflowProgressBar, {
      props: { progress: makeProgress({ phase: 'planning', percent: null, totalSteps: 0 }) }
    })
    const bar = wrapper.get('[role="progressbar"]')

    expect(bar.classes()).toContain('is-indeterminate')
    expect(bar.attributes('aria-valuenow')).toBeUndefined()
    expect(bar.attributes('aria-valuetext')).toContain('规划任务')
    expect(wrapper.text()).not.toContain('0%')
    expect(wrapper.text()).toContain('任务规模计算中')
    wrapper.unmount()
  })

  it('renders the exact backend percent and determinate ARIA values', () => {
    vi.useFakeTimers()
    const wrapper = mount(WorkflowProgressBar, { props: { progress: makeProgress() } })
    const bar = wrapper.get('[role="progressbar"]')

    expect(wrapper.text()).toContain('42.86%')
    expect(bar.attributes('aria-valuenow')).toBe('42.86')
    expect(wrapper.get('.workflow-progress__fill').attributes('style')).toContain('42.86%')
    wrapper.unmount()
  })

  it('keeps real review/recovery/failed/cancelled semantics', async () => {
    vi.useFakeTimers()
    const wrapper = mount(WorkflowProgressBar, {
      props: { progress: makeProgress({ phase: 'recovery', recoveryCount: 2, percent: 50 }) }
    })
    expect(wrapper.text()).toContain('恢复执行')
    expect(wrapper.text()).toContain('恢复 2 次')

    await wrapper.setProps({ progress: makeProgress({ phase: 'review', status: 'waiting_review', percent: 71 }) })
    expect(wrapper.text()).toContain('等待审核')
    expect(wrapper.text()).toContain('71%')

    await wrapper.setProps({ progress: makeProgress({ phase: 'failed', status: 'failed', percent: 64 }) })
    expect(wrapper.text()).toContain('执行失败')
    expect(wrapper.text()).toContain('64%')
    expect(wrapper.text()).not.toContain('100%')

    await wrapper.setProps({ progress: makeProgress({ phase: 'cancelled', status: 'cancelled', percent: 64 }) })
    expect(wrapper.text()).toContain('已取消')
    expect(wrapper.text()).not.toContain('执行失败')
    wrapper.unmount()
  })

  it('shows completed 100 and keeps the last state when synchronization fails', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-22T02:07:00Z'))
    const wrapper = mount(WorkflowProgressBar, {
      props: {
        progress: makeProgress({
          phase: 'completed', status: 'completed', percent: 100, completedSteps: 7,
          startedAt: '2026-07-22T00:00:00Z', updatedAt: '2026-07-22T00:01:32Z'
        }),
        syncError: '进度同步暂时中断，正在重试'
      }
    })
    expect(wrapper.text()).toContain('执行完成')
    expect(wrapper.text()).toContain('100%')
    expect(wrapper.text()).toContain('已完成 7 / 7')
    expect(wrapper.text()).toContain('进度同步暂时中断')
    expect(wrapper.get('.workflow-progress__elapsed').text()).toBe('已运行 01:32')
    wrapper.unmount()
  })

  it('contains no icon dependency or emoji markup and wraps long messages', () => {
    vi.useFakeTimers()
    const message = '很长的执行状态说明'.repeat(30)
    const wrapper = mount(WorkflowProgressBar, {
      props: { progress: makeProgress({ message }) }
    })
    expect(wrapper.find('svg').exists()).toBe(false)
    expect(wrapper.find('.el-icon').exists()).toBe(false)
    expect(wrapper.get('.workflow-progress__message').text()).toBe(message)
    wrapper.unmount()
  })

  it('renders lifecycle messages as escaped text instead of executable markup', () => {
    vi.useFakeTimers()
    const message = '<img src=x onerror="window.__workflowXss = true"><script>alert(1)</script>'
    const wrapper = mount(WorkflowProgressBar, {
      props: { progress: makeProgress({ message }) }
    })

    expect(wrapper.get('.workflow-progress__message').text()).toBe(message)
    expect(wrapper.find('.workflow-progress__message img').exists()).toBe(false)
    expect(wrapper.find('.workflow-progress__message script').exists()).toBe(false)
    expect(wrapper.get('.workflow-progress__message').html()).toContain('&lt;script&gt;')
    wrapper.unmount()
  })

  it('supports compact Chat rendering without changing progress semantics', () => {
    vi.useFakeTimers()
    const wrapper = mount(WorkflowProgressBar, {
      props: { progress: makeProgress({ percent: 37.5 }), variant: 'compact' }
    })
    expect(wrapper.classes()).toContain('variant-compact')
    expect(wrapper.text()).toContain('37.50%')
    expect(wrapper.get('[role="progressbar"]').attributes('aria-valuenow')).toBe('37.5')
    wrapper.unmount()
  })
})
