import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import AcgRunManager from './AcgRunManager.vue'
import { workflowApi, type WorkflowRunSummary } from '@/services/api/workflow'
import { ElMessageBox } from 'element-plus'

vi.mock('@/services/api/workflow', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/api/workflow')>()
  return {
    ...actual,
    workflowApi: {
      ...actual.workflowApi,
      listRuns: vi.fn(),
      deleteRun: vi.fn()
    }
  }
})

const run = (overrides: Partial<WorkflowRunSummary>): WorkflowRunSummary => ({
  taskId: 'task_1', runId: 'run_active_123456789', workflowId: 'legal_contract_review_v1',
  title: '请以 ACG 多智能体协作方式审查这份软件开发合同，强制生成差异化任务图，并完整执行后续流程。', status: 'running', phase: 'executing', message: '风险识别',
  percent: 28, totalSteps: 7, pendingSteps: 4, runningSteps: 1, waitingReviewSteps: 0,
  retryingSteps: 0, failedSteps: 0, completedSteps: 2, cancelledSteps: 0,
  currentStepId: 'risk_detect', activeStepIds: ['risk_detect'], recoveryCount: 0,
  startedAt: '2026-07-26T04:00:00Z', updatedAt: '2026-07-26T04:00:14Z',
  progress: 28, percentage: 28, source: 'acg', createdAt: '2026-07-26T04:00:00Z',
  ...overrides
})

describe('AcgRunManager', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    vi.mocked(workflowApi.listRuns).mockResolvedValue({
      items: [
        run({}),
        run({ runId: 'run_review_1', title: '数据合规风险评估', status: 'waiting_review', phase: 'review', percent: 75 }),
        run({ runId: 'run_done_1', title: '采购合同条款分析', status: 'completed', phase: 'completed', percent: 100 })
      ],
      total: 3, page: 1, pageSize: 100
    })
    vi.mocked(workflowApi.deleteRun).mockResolvedValue({
      runId: 'run_done_1',
      taskId: 'task_1',
      deleted: true,
      taskDeleted: true
    })
  })

  afterEach(() => {
    vi.clearAllMocks()
    vi.useRealTimers()
  })

  it('loads ACG summaries and renders flat status groups', async () => {
    const wrapper = mount(AcgRunManager, {
      props: { activeRunId: 'run_active_123456789' },
      global: { stubs: { 'el-icon': true } }
    })
    await flushPromises()

    expect(workflowApi.listRuns).toHaveBeenCalledWith(
      expect.objectContaining({ source: 'acg', summary: true }),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    expect(wrapper.text()).toContain('运行中')
    expect(wrapper.text()).toContain('等待审核')
    expect(wrapper.text()).toContain('最近完成')
    expect(wrapper.find('.acg-run-item.active').exists()).toBe(true)
    expect(wrapper.find('.acg-run-item__headline strong').text()).toBe('软件开发合同审查')
    expect(wrapper.find('.acg-run-item__identity code').text()).toContain('run_active')
    wrapper.unmount()
  })

  it('emits draft creation and run selection without creating a run itself', async () => {
    const wrapper = mount(AcgRunManager, { global: { stubs: { 'el-icon': true } } })
    await flushPromises()

    await wrapper.find('.acg-new-run').trigger('click')
    await wrapper.find('.acg-run-item__select').trigger('click')

    expect(wrapper.emitted('new')).toHaveLength(1)
    expect(wrapper.emitted('select')?.[0]).toEqual(['run_active_123456789'])
    expect(workflowApi.listRuns).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('only confirms and deletes terminal runs', async () => {
    const confirm = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
    const wrapper = mount(AcgRunManager, { global: { stubs: { 'el-icon': true } } })
    await flushPromises()

    expect(wrapper.find('.status-active .acg-run-delete').exists()).toBe(false)
    expect(wrapper.find('.status-review .acg-run-delete').exists()).toBe(false)
    vi.mocked(workflowApi.listRuns).mockResolvedValue({
      items: [run({}), run({ runId: 'run_review_1', status: 'waiting_review', phase: 'review' })],
      total: 2,
      page: 1,
      pageSize: 100
    })
    await wrapper.find('.status-completed .acg-run-delete').trigger('click')
    await flushPromises()

    expect(confirm).toHaveBeenCalledWith(
      '该操作将永久删除本次运行的步骤、动态历史和执行结果，无法恢复。',
      '删除运行记录？',
      expect.objectContaining({ confirmButtonText: '永久删除' })
    )
    expect(workflowApi.deleteRun).toHaveBeenCalledWith('run_done_1')
    expect(wrapper.emitted('deleted')?.[0]).toEqual(['run_done_1'])
    expect(wrapper.find('.status-completed').exists()).toBe(false)
    confirm.mockRestore()
    wrapper.unmount()
  })
})
