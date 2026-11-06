import { computed, ref } from 'vue'
import { useChatWorkflowPresentation } from '@/composables/useChatWorkflowPresentation'
import { capabilitiesFixture } from '@/test/fixtures/runCapabilities'
import { describe, it, expect } from 'vitest'
import { projectRunLifecycle, mapRunPhase } from './runLifecycle'
const run = (status = 'running') => ({ missionId: 'm', runId: 'r', runtimeRevision: 4, status } as any)
const project = (detail: any, progress?: any) => projectRunLifecycle({ missionId: 'm', runId: 'r', run: detail, progress })
describe('shared lifecycle authority', () => {
  it.each(['pending','planning','running','waiting_review','retrying','failed','completed','succeeded','cancelled','superseded','queued','unknown'])('maps %s without message or view fallbacks', status => {
    expect(project(run(status)).phase).toBe(({ pending:'QUEUED', planning:'PLANNING', running:'RUNNING', waiting_review:'WAITING_REVIEW', retrying:'RECOVERING', failed:'FAILED', completed:'COMPLETED', succeeded:'COMPLETED', cancelled:'CANCELLED', superseded:'SUPERSEDED', queued:'QUEUED', unknown:'UNKNOWN' } as any)[status])
  })
  it.each(['PLANNING_ACCEPTED','MATERIALIZED_INACTIVE','ACTIVATED_PAUSED','ACTIVATED','DISPATCHED'])('retains formal mapping %s', status => {
    const detail = run('pending'); detail.formalControl = { status, permitStatus:'ISSUED', dispatchEnabled:true, dispatchEligible:true,
      ...(status === 'DISPATCHED' ? { dispatch:{ runId:'r',status:'ACCEPTED' } } : {}) }
    expect(project(detail).phase).toBe(status === 'DISPATCHED' ? 'DISPATCHED' : status === 'ACTIVATED' ? 'READY_TO_DISPATCH' : status === 'ACTIVATED_PAUSED' ? status : 'AWAITING_CONFIRMATION')
  })
  it.each([3,4,5])('retains terminal Run against conflicting progress revision %s', revision => {
    const result = project(run('completed'), { missionId:'m',runId:'r',status:'running',runtimeRevision:revision })
    expect(result.phase).toBe('COMPLETED'); expect(result.synchronizationState).toBe(revision === 3 ? 'PARTIAL' : 'RECONCILING')
    expect(result.progress).toBeNull()
    expect(result.progressObservation?.status).toBe('running')
    expect(result.progressObservationState).toBe(revision === 3 ? 'STALE' : 'RECONCILING')
  })
  it.each(['runId','missionId'])('rejects foreign Progress %s', key => {
    const result = project(run(),{ missionId:'m',runId:'r',status:'completed',[key]:'foreign' })
    expect(result.synchronizationState).toBe('IDENTITY_MISMATCH')
    expect(result.progressObservationState).toBe('IDENTITY_MISMATCH')
    expect(result.progressObservation).toBeNull()
    expect(result.progress).toBeNull()
    expect(result.phase).toBe('RUNNING')
  })
  it('isolates a newer same-status Progress revision while preserving the observation for diagnostics', () => {
    const result = project(run('completed'), { missionId:'m',runId:'r',status:'completed',runtimeRevision:5 })
    expect(result.phase).toBe('COMPLETED')
    expect(result.synchronizationState).toBe('RECONCILING')
    expect(result.progress).toBeNull()
    expect(result.progressObservation?.runtimeRevision).toBe(5)
    expect(result.progressObservationState).toBe('RECONCILING')
  })
  it('marks matching Progress as temporary and absence as unavailable', () => {
    const temporary = project(null,{ missionId:'m',runId:'r',status:'running' })
    expect(temporary.statusSource).toBe('PROGRESS_TEMPORARY')
    expect(temporary.progressObservationState).toBe('TRUSTED')
    expect(temporary.progress).toBeTruthy()
    expect(project(null).phase).toBe('UNKNOWN'); expect(project(null).synchronizationState).toBe('UNAVAILABLE')
    expect(project({ ...run(),missionId:'other' }).phase).toBe('UNKNOWN')
    expect(mapRunPhase(null,null,null,true).phase).toBe('CREATED')
  })
  it('marks a capability revision conflict without granting authority', () => {
    const detail = run(); detail.actionCapabilities = capabilitiesFixture('r','m','running',3)
    expect(project(detail).synchronizationState).toBe('RECONCILING')
    expect(project(detail).phase).toBe('RUNNING')
  })

  it('ignores cached message and AcgView status when the authoritative Run disagrees', () => {
    const detail = run('running'); detail.actionCapabilities = capabilitiesFixture('r','m','running',4)
    const state = useChatWorkflowPresentation({ activeWorkflowRun:ref(detail), activeWorkflowRunId:ref('r'),
      activeAcgView:ref({ status:'failed' } as any), progress:ref(null), expectedMissionId:ref('m'),
      messages:computed(() => [{ workflowRunId:'r',workflowStatus:'completed' }] as any) })
    expect(state.activeWorkflowStatus.value).toBe('running')
    expect(state.lifecycle.value.synchronizationState).toBe('SYNCED')
  })

})
