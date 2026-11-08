import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import RunSelectionInspector from './RunSelectionInspector.vue'
import type { RunDocumentSymbol } from '@/workbench/runtime/runDocument'

const symbol = (overrides: Partial<RunDocumentSymbol>): RunDocumentSymbol => ({
  id: 'symbol_1',
  type: 'task',
  status: 'running',
  title: 'Capacity analysis',
  runId: 'run_1',
  children: [],
  ...overrides
})

const mountInspector = (selectedSymbol: RunDocumentSymbol | null) => mount(RunSelectionInspector, {
  props: {
    entry: null,
    selectedSymbol,
    graphNode: null,
    graphNodes: [],
    runId: 'run_1',
    runStatus: 'running',
    historical: false,
    runtimeObservation: null,
    runtimeStore: null
  }
})

describe('RunSelectionInspector', () => {
  it('switches planner metadata from the selected symbol', () => {
    const wrapper = mountInspector(symbol({
      type: 'planner',
      title: 'Task planning',
      status: 'completed',
      metrics: { 'Task Count': 26, 'Dependency Count': 34 }
    }))

    expect(wrapper.text()).toContain('任务规划')
    expect(wrapper.text()).toContain('任务数26')
    expect(wrapper.text()).toContain('依赖数34')
  })

  it('shows safe task, tool and artifact fields without raw payloads', () => {
    const task = mountInspector(symbol({
      type: 'task',
      children: [{
        ...symbol({ id: 'agent_1', type: 'agent', status: 'running', title: 'Agent', subtitle: 'Capacity Analyst' })
      }]
    }))
    expect(task.text()).toContain('执行智能体Capacity Analyst')

    const tool = mountInspector(symbol({
      type: 'tool',
      title: 'Read Material',
      metrics: { Duration: 836, Task: 'Capacity analysis' }
    }))
    expect(tool.text()).toContain('耗时836 ms')
    expect(tool.text()).not.toContain('raw arguments')

    const artifact = mountInspector(symbol({
      type: 'artifact',
      title: 'capacity-analysis.md',
      subtitle: 'text/markdown',
      artifactKey: 'capacity-analysis',
      metrics: { Task: 'Capacity analysis' }
    }))
    expect(artifact.text()).toContain('生成任务Capacity analysis')
  })
})
