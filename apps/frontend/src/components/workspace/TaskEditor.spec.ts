import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { agentosApi, agentosRequest, type MissionWorkspaceProjection, type WorkspaceEntry } from '@/services/api/agentos'
import { RunRuntimeStore } from '@/workbench/runtime/runtimeEvents'
import TaskEditor from './TaskEditor.vue'

const task: WorkspaceEntry = {
  entryId: 'task:design', kind: 'task', name: '系统架构设计', group: 'steps', displayOrder: 0,
  semanticTaskKey: 'design', taskId: 'task_1', acgNodeId: 'node_1', runId: 'run_1',
  metadata: { outputRef: 'output:node_1', outputSummary: '架构设计完成' },
}

const projection: MissionWorkspaceProjection = {
  mission: {
    missionId: 'mission_1', userId: 'user_1', goal: 'test', description: '', metadata: {},
    createdAt: '2026-09-04T00:00:00Z', updatedAt: '2026-09-04T00:00:00Z', status: 'running',
  },
  activeRun: {
    runId: 'run_1', status: 'running', createdAt: '2026-09-04T00:00:00Z', isActive: true,
  },
  activeGraph: null, runs: [], entries: [task], diagnostics: [],
  graphNodes: [{ acgNodeId: 'node_1', nodeType: 'step', name: '系统架构设计', semanticTaskKey: 'design', displayOrder: 0 }],
}

const mountEditor = (runtimeStore: RunRuntimeStore | null = null) => mount(TaskEditor, {
  props: { entry: task, projection, graphNodes: projection.graphNodes, runtimeObservation: null, runtimeStore },
})

describe('TaskEditor stage output', () => {
  afterEach(() => vi.restoreAllMocks())

  it('displays one final document with no duplicate heading or source controls', async () => {
    const report = '# 成果报告\n\n## 恢复计划\n计划只出现一次。'
    vi.spyOn(agentosApi, 'getRunOutput').mockResolvedValue({ runId: 'run_1', outputRef: 'output:node_1', content: {
      final_answer: report, artifact: { artifactType: 'run_deliverable', content: report },
      artifacts: [{ artifactType: 'run_deliverable', content: report }],
      verification: { status: 'partial', checks: [], unresolvedGaps: ['尚未执行恢复测试'] }
    } })
    const wrapper = mountEditor()
    await wrapper.setProps({ entry: { ...task, semanticTaskKey: 'final_report', status: 'completed' } })
    await flushPromises()
    expect(wrapper.findAll('h1')).toHaveLength(1)
    expect(wrapper.get('h1').text()).toBe('成果报告')
    expect(wrapper.text()).toContain('产物验证：部分通过')
    expect(wrapper.text()).toContain('尚未执行恢复测试')
    expect(wrapper.text().split('计划只出现一次。')).toHaveLength(2)
    expect(wrapper.find('.task-document__source').exists()).toBe(false)
    expect(wrapper.find('.stage-output-viewer__source').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('正文只呈现当前 Artifact')
    wrapper.unmount()
  })

  it('shows result loading instead of a task objective for a completed step', async () => {
    let resolveOutput!: (value: { runId: string; outputRef: string; content: unknown }) => void
    vi.spyOn(agentosApi, 'getRunOutput').mockImplementation(() => new Promise(resolve => { resolveOutput = resolve }))
    const wrapper = mountEditor()
    await wrapper.setProps({ entry: { ...task, status: 'completed', objective: '这只是任务描述' } })
    expect(wrapper.get('[role="status"]').text()).toBe('正在读取已保存的步骤结果…')
    expect(wrapper.text()).not.toContain('这只是任务描述')
    expect(wrapper.text()).not.toContain('等待模型输出')
    resolveOutput({ runId: 'run_1', outputRef: 'output:node_1', content: { summary: '已保存的结果' } })
    await flushPromises()
    expect(wrapper.get('.task-document__blocks').text()).toContain('已保存的结果')
  })

  it('uses the persisted result after a live node completes', async () => {
    vi.spyOn(agentosApi, 'getRunOutput').mockResolvedValue({
      runId: 'run_1', outputRef: 'output:node_1', content: { summary: '完整结果' }
    })
    const runtimeStore = new RunRuntimeStore('run_1')
    runtimeStore.apply({
      eventId: 'delta', eventType: 'model.output.delta', runId: 'run_1', nodeId: 'node_1',
      attemptId: 'attempt_1', sequence: 1, payload: { delta: '残留片段' }
    })
    await new Promise(resolve => setTimeout(resolve, 20))
    runtimeStore.apply({
      eventId: 'complete', eventType: 'node.completed', runId: 'run_1', nodeId: 'node_1',
      attemptId: 'attempt_1', sequence: 2, payload: {}
    })
    const wrapper = mountEditor(runtimeStore)
    await flushPromises()
    expect(wrapper.get('.task-document__blocks').text()).toContain('完整结果')
    expect(wrapper.text()).not.toContain('残留片段')
  })

  it('reports an empty completed output instead of waiting for the model', async () => {
    vi.spyOn(agentosApi, 'getRunOutput').mockResolvedValue({
      runId: 'run_1', outputRef: 'output:node_1', content: null
    })
    const wrapper = mountEditor()
    await wrapper.setProps({ entry: { ...task, status: 'completed' } })
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('结果正文为空')
    expect(wrapper.text()).not.toContain('等待模型输出')
  })

  it('projects the encoded gateway output into the step document', async () => {
    vi.spyOn(agentosRequest, 'get').mockResolvedValue({ data: {
      runId: 'run_1', outputRef: 'output:node_1', content: {
        kind: 'object', members: [
          { name: 'summary', value: { kind: 'string', text: '活动整体方案设计' } },
          { name: 'decision', value: { kind: 'string', text: '分组交流并共享阅读心得' } }
        ]
      }
    } } as never)
    const wrapper = mountEditor()
    await flushPromises()

    const body = wrapper.get('.task-document__blocks').text()
    expect(body).toContain('活动整体方案设计')
    expect(body).toContain('分组交流并共享阅读心得')
    expect(body).not.toContain('members')
    expect(body).not.toContain('kind')
  })

  it('loads and displays a persisted node result without calling it a formal Artifact', async () => {
    vi.spyOn(agentosApi, 'getRunOutput').mockResolvedValue({
      runId: 'run_1', outputRef: 'output:node_1', content: { summary: '架构方案', decision: '事件驱动' },
    })
    const wrapper = mountEditor()
    await flushPromises()

    expect(agentosApi.getRunOutput).toHaveBeenCalledWith('run_1', 'output:node_1', expect.anything())
    expect(wrapper.get('[data-testid="task-stage-output"]').text()).toContain('架构方案')
    expect(wrapper.text()).not.toContain('原始结构化结果')
    expect(wrapper.find('.task-document__footer-note').exists()).toBe(false)
    expect(wrapper.text().split('架构方案')).toHaveLength(2)
    expect(wrapper.text()).not.toContain('PERSISTED')
  })

  it('prefers the current live stream while a node is executing', async () => {
    vi.spyOn(agentosApi, 'getRunOutput').mockResolvedValue({
      runId: 'run_1', outputRef: 'output:node_1', content: { summary: '旧结果' },
    })
    const runtimeStore = new RunRuntimeStore('run_1')
    runtimeStore.apply({
      eventId: 'evt_1', eventType: 'model.output.delta', runId: 'run_1', nodeId: 'node_1',
      attemptId: 'attempt_1', sequence: 1, payload: { delta: '正在生成的新阶段结果' },
    })
    await new Promise(resolve => setTimeout(resolve, 20))
    const wrapper = mountEditor(runtimeStore)
    await flushPromises()

    expect(wrapper.get('[data-testid="task-stage-output"]').text()).toContain('正在生成的新阶段结果')
    expect(wrapper.get('[data-testid="task-stage-output"]').text()).not.toContain('旧结果')
  })

  it('promotes a structured result item to the shared Inspector selection', async () => {
    vi.spyOn(agentosApi, 'getRunOutput').mockResolvedValue({
      runId: 'run_1', outputRef: 'output:node_1', content: {
        constraints: [{ constraint: 'RTO 不得超过 2 小时', mandatory: true, source: 'constraint:3' }]
      }
    })
    const wrapper = mountEditor()
    await flushPromises()

    await wrapper.get('.stage-output-viewer__item').trigger('click')

    expect(wrapper.emitted('selectSymbol')?.[0]?.[0]).toMatchObject({
      id: 'task-result:design:constraints:0',
      type: 'result',
      title: 'RTO 不得超过 2 小时',
      subtitle: 'constraints · constraint:3'
    })
  })

  it('renders requirement-analysis output as a requirements document', async () => {
    vi.spyOn(agentosApi, 'getRunOutput').mockResolvedValue({
      runId: 'run_1', outputRef: 'output:node_1', content: {
        requirements: [{ id: 'REQ-03', requirement: '试生产及爬坡周期不超过 6 周，并给出逐周产量与节拍目标。' }],
        acceptance_criteria: [{
          requirement_id: 'REQ-03', metric: '试生产 + 爬坡周数', target: '≤ 6 周', criterion: '逐周目标均已给出。'
        }]
      }
    })
    const wrapper = mountEditor()
    await flushPromises()

    expect(wrapper.find('.task-document__blocks').text()).toContain('REQ-03')
    expect(wrapper.find('.task-document__blocks').text().split('试生产及爬坡周期')).toHaveLength(2)
    expect(wrapper.find('.task-document__blocks').text()).not.toContain('Requirement Acceptance Matrix')
    expect(wrapper.find('.task-document__blocks').find('table').exists()).toBe(false)
    expect(wrapper.find('.task-document__blocks').text().split('≤ 6 周')).toHaveLength(2)
    expect(wrapper.find('.task-document__blocks').text()).not.toContain('metric:')
    expect(wrapper.find('.task-document__blocks').text()).not.toContain('requirement_id:')
    expect(wrapper.findAll('.task-document__gutter').map(gutter => gutter.text())).toEqual(['01', '02'])
    expect(wrapper.findAll('.task-document__block').map(block => block.attributes('data-block-id'))).toEqual([
      'intro',
      'req-03'
    ])
    await wrapper.get('.task-document__gutter[data-block-id="req-03"]').trigger('click')
    expect(wrapper.get('.task-document__block[data-block-id="req-03"]').classes()).toContain('is-focused')
  })
})
