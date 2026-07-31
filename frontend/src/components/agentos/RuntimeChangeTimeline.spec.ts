import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import RuntimeChangeTimeline from './RuntimeChangeTimeline.vue'

const events = [
  {
    eventId: 'event-evidence', eventType: 'EVIDENCE_MISSING', graphVersion: 1,
    runtimeNodeId: 'risk_analysis', status: 'PROCESSED', createdAt: '2026-07-27T01:00:00Z',
    payload: { reasonCode: 'LEGAL_BASIS_MISSING', targetNodeId: 'risk_analysis', token: 'do-not-render' }
  },
  {
    eventId: 'event-binding', eventType: 'BINDING_UNAVAILABLE', graphVersion: 2,
    runtimeNodeId: 'risk_analysis', status: 'PROCESSED', createdAt: '2026-07-27T02:00:00Z',
    payload: { reasonCode: '<img src=x onerror=alert(1)>' }
  }
]

const patches = [
  {
    patchId: 'patch-add', operationType: 'ADD_SUBGRAPH', sourceEventId: 'event-evidence',
    baseGraphVersion: 1, resultGraphVersion: 2, appliedAt: '2026-07-27T01:00:01Z'
  },
  {
    patchId: 'patch-binding', operationType: 'RETRY_ALTERNATE_BINDING', sourceEventId: 'event-binding',
    baseGraphVersion: 2, resultGraphVersion: 3, appliedAt: '2026-07-27T02:00:01Z'
  },
  {
    patchId: 'patch-condition', operationType: 'ACTIVATE_CONDITIONAL_BRANCH', sourceEventId: 'condition-event',
    baseGraphVersion: 3, resultGraphVersion: 4, appliedAt: '2026-07-27T03:00:01Z'
  }
]

const steps = [
  { stepId: 'evidence_retrieval', status: 'completed', sourcePatchId: 'patch-add', createdGraphVersion: 2 },
  {
    stepId: 'risk_analysis', status: 'completed', attempt: 2, bindingSwitchCount: 1,
    currentBinding: { bindingId: 'backup' },
    bindingHistory: [
      { bindingId: 'primary', selectedAtGraphVersion: 1 },
      { bindingId: 'backup', selectedAtGraphVersion: 3, sourcePatchId: 'patch-binding', sourceEventId: 'event-binding', selectedAt: '2026-07-27T02:00:01Z' }
    ]
  }
]

describe('RuntimeChangeTimeline', () => {
  it('explains subgraph, alternate binding and conditional changes in stable order', () => {
    const wrapper = mount(RuntimeChangeTimeline, {
      props: {
        runtimeEvents: events as any,
        appliedPatches: patches as any,
        stepStates: steps as any,
        branchDecisions: [{
          decisionId: 'd1', controlNodeId: 'risk_route', sourceNodeId: 'risk_analysis',
          sourceOutputVersion: 1, inputHash: 'hash', selectedCaseKey: 'high', selectedEdgeIds: ['high'],
          terminatedEdgeIds: ['low'], skippedNodeIds: ['direct_report'], joinNodeId: 'join',
          sourceEventId: 'condition-event', sourcePatchId: 'patch-condition', decidedAtGraphVersion: 4,
          decidedAt: '2026-07-27T03:00:02Z'
        }]
      }
    })

    const text = wrapper.text()
    expect(text).toContain('新增节点：evidence_retrieval')
    expect(text).toContain('primary 切换为 backup')
    expect(text).toContain('选择了“high”路径')
    expect(text).toContain('v1 → v2')
    expect(wrapper.findAll('li').length).toBe(7)
  })

  it('escapes malicious strings and redacts sensitive raw detail', async () => {
    const wrapper = mount(RuntimeChangeTimeline, { props: { runtimeEvents: events as any } })
    await wrapper.get('summary').trigger('click')
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.html()).toContain('&lt;img')
    expect(wrapper.text()).not.toContain('do-not-render')
    expect(wrapper.text()).toContain('[已隐藏]')
  })
})
