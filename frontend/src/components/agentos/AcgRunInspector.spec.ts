import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AcgRunInspector from './AcgRunInspector.vue'

describe('AcgRunInspector', () => {
  it('explains the real data projection without inventing metrics before a run starts', () => {
    const wrapper = mount(AcgRunInspector)

    expect(wrapper.text()).toContain('暂无 ACG 运行数据')
    expect(wrapper.text()).toContain('规划、节点、执行进度与低熵通信指标')
    expect(wrapper.text()).not.toContain('Token 节省率')
  })

  it('projects the active ACG run and exposes both operational entries', async () => {
    const wrapper = mount(AcgRunInspector, {
      props: {
        runId: 'run_1234567890abcdef',
        status: 'running',
        statusLabel: '运行中',
        progress: {
          message: '正在执行证据核验', percent: 50, totalSteps: 4, completedSteps: 2,
          runningSteps: 1, waitingReviewSteps: 1, failedSteps: 0, recoveryCount: 1,
          currentStepId: 'evidence_verify', dynamicStepCount: 2, bindingSwitchCount: 1
        } as any,
        blueprint: {
          nodes: [{ nodeId: 'n1' }, { nodeId: 'n2' }, { nodeId: 'n3' }],
          edges: [{ edgeId: 'e1' }, { edgeId: 'e2' }]
        } as any,
        view: {
          lowEntropyMetrics: {
            averageSavingRatio: 0.2, effectiveSavingRatio: 0.25,
            tokensAvailable: 2000, tokensDelivered: 1500, tokensSaved: 500,
            recoveryCount: 1, interactionCount: 6, contractViolationCount: 0,
            integrityStatus: 'valid'
          }
        } as any
      }
    })

    expect(wrapper.text()).toContain('正在执行证据核验')
    expect(wrapper.text()).toContain('3 节点 · 2 关系')
    expect(wrapper.text()).toContain('2 新增 · 1 切换')
    expect(wrapper.text()).toContain('25.0%')
    expect(wrapper.text()).toContain('审计通过')

    const buttons = wrapper.findAll('.inspector-actions button')
    await buttons[0].trigger('click')
    await buttons[1].trigger('click')
    expect(wrapper.emitted('open-acg')).toHaveLength(1)
    expect(wrapper.emitted('open-console')).toHaveLength(1)
  })
})
