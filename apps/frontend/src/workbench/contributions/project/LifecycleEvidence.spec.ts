import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import LifecycleEvidence from './LifecycleEvidence.vue'
import { projectLifecycle } from '@/workbench/runtime/lifecycleProjection'
import { capabilitiesFixture } from '@/test/fixtures/runCapabilities'
import { emptyRuntimeObservation } from '@/workbench/runtime/observation'
import type { MissionWorkspaceProjection, WorkspaceEntry } from '@/services/api/agentos'

const artifact: WorkspaceEntry = { entryId: 'final', kind: 'artifact', name: '方案报告.md', group: 'artifacts',
  displayOrder: 0, runId: 'r', identityQuality: 'canonical', artifactType: 'run_deliverable',
  artifactKey: 'final', artifactId: 'artifact-r', contentRef: 'manifest-r' }
const lifecycle = (options: { status?: string; delivery?: boolean; capabilities?: boolean } = {}) => {
  const status = options.status || 'completed'
  const capabilities = capabilitiesFixture('r', 'm', status, 38, { unavailableReasons: [
    { action: 'canCancel', code: 'RUN_NOT_ACTIVE' }, { action: 'canRetrySuccessor', code: 'RECOVERY_EVIDENCE_UNAVAILABLE' }
  ] })
  const summary = { runId: 'r', missionId: 'm', status, createdAt: '2026-11-08', runtimeRevision: 38,
    ...(options.capabilities === false ? {} : { actionCapabilities: capabilities }) }
  const workspace = { mission: { missionId: 'm' }, activeRun: summary, runs: [summary],
    entries: options.delivery === false ? [] : [artifact], graphNodes: [], diagnostics: [] } as unknown as MissionWorkspaceProjection
  return projectLifecycle({ workspace, selectedRunId: 'r' })
}

describe('Inspector lifecycle reading and authority boundaries', () => {
  it('leads with the completed outcome, keeps identifiers collapsed and opens the actual delivery', async () => {
    const view = lifecycle()
    const observation = emptyRuntimeObservation('r')
    observation.provenance.integrityStatus = 'valid'
    const wrapper = mount(LifecycleEvidence, { props: { lifecycle: view, observation } })
    expect(wrapper.get('.lifecycle-summary').text()).toContain('本次运行已完成')
    expect(wrapper.get('.lifecycle-delivery').text()).toContain('方案报告.md')
    expect(wrapper.get('.lifecycle-delivery').text()).toContain('此校验只说明产物与执行记录的关联情况')
    expect(wrapper.findAll('.inspector-details').every(node => node.attributes('open') === undefined)).toBe(true)
    expect(wrapper.get('.lifecycle-reasons').text()).toContain('当前没有满足恢复条件的失败步骤')
    expect(wrapper.get('.lifecycle-reasons').text()).not.toContain('RECOVERY_EVIDENCE_UNAVAILABLE')
    expect(wrapper.get('.lifecycle-raw').text()).toContain('RUN_NOT_ACTIVE')
    await wrapper.get('.lifecycle-delivery button').trigger('click')
    expect(wrapper.emitted('openArtifact')).toEqual([[artifact]])
    expect(view.capabilities?.canCancel).toBe(false)
    wrapper.unmount()
  })

  it('makes missing final delivery explicit without offering a fabricated download', () => {
    const wrapper = mount(LifecycleEvidence, { props: { lifecycle: lifecycle({ delivery: false }) } })
    expect(wrapper.text()).toContain('尚未确认最终交付物')
    expect(wrapper.find('.lifecycle-delivery button').exists()).toBe(false)
    wrapper.unmount()
  })

  it('does not infer capabilities from a completed status or accept another run provenance', () => {
    const observation = emptyRuntimeObservation('foreign')
    observation.provenance.integrityStatus = 'valid'
    const wrapper = mount(LifecycleEvidence, { props: { lifecycle: lifecycle({ capabilities: false }), observation } })
    expect(wrapper.find('.lifecycle-available').exists()).toBe(false)
    expect(wrapper.text()).toContain('操作状态暂时无法确认')
    expect(wrapper.find('.lifecycle-delivery p').exists()).toBe(false)
    wrapper.unmount()
  })
})
