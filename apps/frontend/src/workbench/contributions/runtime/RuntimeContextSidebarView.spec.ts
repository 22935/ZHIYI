import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import RuntimeContextSidebarView from './RuntimeContextSidebarView.vue'
import { createWorkbenchContext } from '@/workbench/context'
import type { RuntimeObservation } from '@/workbench/runtime/observation'
import type { RunContextPackSummary, WorkspaceEntry } from '@/services/api/agentos'

const graphEntry: WorkspaceEntry = {
  entryId: 'overview:graph.acg',
  kind: 'graph',
  name: 'graph.acg',
  group: 'overview',
  displayOrder: 0,
  graphId: 'graph_1',
  graphVersion: 1
}

const pack: RunContextPackSummary = {
  stepId: 'native_general_agent_11',
  contextRef: 'context:run_db6f32ac2f49:native_general_agent_11:0073ec32',
  available: true,
  objective: '我需要为一套运行在 Windows 本机的复杂 AI Agent 系统设计故障恢复与高可用改进方案。',
  stepGoal: '分析策略之间冲突与依赖，给出适配本机单用户场景的选型结论。',
  sourceStepIds: ['native_general_agent_10', 'native_general_agent_7'],
  evidenceRefs: [],
  missingFields: [],
  contractStatus: 'valid',
  tokensDelivered: 3861,
  tokensAvailable: 3861,
  savingRatio: 0,
  fieldCount: 3,
  sourceCount: 2,
  dataKeys: ['strategy_matrix'],
  sourceDataKeys: ['upstream_summary']
}

const observation = (packs: RunContextPackSummary[] | null): RuntimeObservation => ({
  runId: 'run_1',
  runStatus: 'succeeded',
  traces: [],
  events: [],
  communication: [],
  toolCalls: [],
  problems: [],
  audit: {
    provenanceStatus: null, provenanceRecordCount: 0, evidenceCount: 0,
    contractViolationCount: 0, recoveryCount: 0, reviewCount: null
  },
  provenance: { schemaVersion: null, integrityStatus: null, productions: [], consumptions: [], interactions: [] },
  operational: null,
  recoveryTrace: [],
  contractViolations: [],
  scheduleTrace: [],
  patchRefs: [],
  lowEntropy: {
    observed: false, source: null, averageSavingRatio: null, effectiveSavingRatio: null,
    tokensAvailable: null, tokensDelivered: null, tokensSaved: null,
    recoveryCount: 0, degradationCount: 0, interactionCount: 0, contractViolationCount: 0, integrityStatus: null
  },
  resourceObservation: null,
  contextPacks: packs,
  unavailableSources: []
})

const mountView = (packs: RunContextPackSummary[] | null) => {
  const runtimeObservation = observation(packs)
  const context = {
    ...createWorkbenchContext({
      missionId: 'mission_1',
      runId: 'run_1',
      activeEditorId: graphEntry.entryId,
      activeEntryKind: 'graph',
      runtimeObservation
    }),
    entry: graphEntry,
    graphNode: null,
    available: true,
    graph: { graphId: 'graph_1', nodes: [], edges: [], metadata: { graphVersion: 1 } },
    runStatus: 'succeeded'
  }
  return mount(RuntimeContextSidebarView, { props: { context, runtimeObservation } })
}

describe('RuntimeContextSidebarView context packs', () => {
  it('renders a pack card with status badges, token metrics and prose goals', () => {
    const wrapper = mountView([pack])
    const text = wrapper.text()

    expect(text).toContain('上下文数据')
    expect(text).toContain('分析策略之间冲突与依赖')
    expect(text).toContain('已就绪')
    expect(text).toContain('校验通过')
    expect(text).toContain('3861')
    expect(text).toContain('0.0%')
    expect(wrapper.findAll('.context-pack__goal')).toHaveLength(2)
    expect(wrapper.get('.context-pack__goal-label').text()).toBe('任务目标')

    const chips = wrapper.findAll('.context-pack__chips .reference-item')
    expect(chips).toHaveLength(2)
    expect(chips[0].text()).toBe('native_general_agent_10')

    expect(wrapper.get('.context-pack__row-empty').text()).toBe('暂无')
    expect(wrapper.text()).not.toContain('缺失字段')

    const technical = wrapper.get('.context-pack__technical')
    expect(technical.attributes('open')).toBeUndefined()
    expect(technical.text()).toContain('context:run_db6f32ac2f49')
    wrapper.unmount()
  })

  it('keeps raw projection keys out of the visible copy', () => {
    const wrapper = mountView([pack])
    const text = wrapper.text()
    for (const raw of ['available', 'fieldCount', 'sourceCount', 'contractStatus', 'tokensDelivered',
      'tokensAvailable', 'savingRatio', 'sourceStepIds', 'evidenceRefs', 'missingFields',
      'stepId', 'contextRef', 'objective', 'stepGoal']) {
      expect(text).not.toContain(raw)
    }
    wrapper.unmount()
  })

  it('marks unavailable packs and unverified contracts without implying health', () => {
    const wrapper = mountView([{ ...pack, available: false, contractStatus: 'unknown', missingFields: ['strategy_matrix'] }])

    expect(wrapper.text()).toContain('未就绪')
    expect(wrapper.text()).toContain('暂未确认')
    expect(wrapper.get('.context-pack__contract').attributes('data-ok')).toBe('false')

    const warnChips = wrapper.findAll('.context-pack__chips.is-warn .reference-item')
    expect(warnChips).toHaveLength(1)
    expect(warnChips[0].text()).toBe('strategy_matrix')
    wrapper.unmount()
  })

  it('shows an explicit empty state when the snapshot has no packs', () => {
    const wrapper = mountView([])
    expect(wrapper.text()).toContain('暂无上下文包数据。')
    wrapper.unmount()
  })
})
