import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import DynamicRunSummaryCard from './DynamicRunSummaryCard.vue'

describe('DynamicRunSummaryCard', () => {
  it('renders one consistent summary from dynamic runtime projections', () => {
    const wrapper = mount(DynamicRunSummaryCard, {
      props: {
        progress: {
          status: 'running', graphVersion: 2, dynamicStepCount: 2,
          bindingSwitchCount: 1, conditionalDecisionCount: 1, skippedByConditionCount: 2
        } as any,
        view: {
          status: 'running', graphVersion: 2, dynamicStepCount: 2, bindingSwitchCount: 1,
          conditionalDecisionCount: 1, skippedByConditionCount: 2,
          appliedPatches: [{ patchId: 'p1' }, { patchId: 'p2' }, { patchId: 'p3' }],
          runtimeEvents: [{ eventId: 'e1', eventType: 'EVIDENCE_MISSING', status: 'PENDING' }]
        } as any
      }
    })

    expect(wrapper.text()).toContain('v2')
    expect(wrapper.text()).toContain('动态步骤2')
    expect(wrapper.text()).toContain('绑定切换1')
    expect(wrapper.text()).toContain('条件决策1')
    expect(wrapper.text()).toContain('条件跳过2')
    expect(wrapper.text()).toContain('已应用 Patch3')
    expect(wrapper.text()).toContain('待处理事件1')
  })

  it('is backward compatible when all dynamic fields are absent', () => {
    const wrapper = mount(DynamicRunSummaryCard, { props: { run: { status: 'completed' } as any } })
    expect(wrapper.text()).toContain('已完成')
    expect(wrapper.text()).toContain('v1')
    expect(wrapper.findAll('.summary-grid b').map(node => node.text())).toEqual(['v1', '0', '0', '0', '0', '0', '0'])
  })
})
