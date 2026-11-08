import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { agentosApi, type WorkspaceEntry } from '@/services/api/agentos'
import ProjectArtifactInspector from './ProjectArtifactInspector.vue'
import ProjectRunSidebarView from './ProjectRunSidebarView.vue'

const entry: WorkspaceEntry = {
  entryId: 'artifact:final', kind: 'artifact', name: 'final.md', group: 'steps', displayOrder: 0,
  artifactType: 'run_deliverable', semanticTaskKey: 'final', runId: 'run_1',
  metadata: { outputRef: 'output:final' }
}
const content = { final_answer: '# 报告', verification: { status: 'partial', checks: [], unresolvedGaps: ['需实测'] }, deliverable: { sourceRefs: ['source:1'] } }

describe('ProjectArtifactInspector output evidence', () => {
  afterEach(() => vi.restoreAllMocks())

  it('loads the linked output so markdown artifacts retain verification and sources', async () => {
    vi.spyOn(agentosApi, 'getRunOutput').mockResolvedValue({ runId: 'run_1', outputRef: 'output:final', content })
    const wrapper = mount(ProjectRunSidebarView, { props: {
      entry, runId: 'run_1', available: true, graphNode: null, graphNodes: [], graph: null, runStatus: 'completed', historical: false
    } })
    await flushPromises()
    expect(wrapper.text()).toContain('产物验证：部分通过')
    expect(wrapper.text()).toContain('需实测')
    expect(wrapper.text()).toContain('source:1')
    wrapper.unmount()
  })

  it('discards a late response after switching runs and reports failure on the current run', async () => {
    let resolveOld!: (value: any) => void
    vi.spyOn(agentosApi, 'getRunOutput')
      .mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
      .mockRejectedValueOnce(new Error('unavailable'))
    const wrapper = mount(ProjectArtifactInspector, { props: { entry, runId: 'run_1', available: true } })
    await wrapper.setProps({ runId: 'run_2', entry: { ...entry, runId: 'run_2', metadata: { outputRef: 'output:new' } } })
    await flushPromises()
    resolveOld({ runId: 'run_1', outputRef: 'output:final', content })
    await flushPromises()
    expect(wrapper.text()).toContain('暂时无法读取')
    expect(wrapper.text()).not.toContain('产物验证：部分通过')
    expect(wrapper.text()).not.toContain('source:1')
    wrapper.unmount()
  })
})
