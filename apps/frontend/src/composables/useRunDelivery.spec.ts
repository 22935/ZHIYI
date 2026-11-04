import { effectScope, ref, nextTick } from 'vue'
import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, it, expect, vi } from 'vitest'
import { agentosApi } from '@/services/api/agentos'
import { useRunDelivery } from './useRunDelivery'
afterEach(() => vi.restoreAllMocks())
const artifact = { kind:'artifact',runId:'r',identityQuality:'canonical',artifactKey:'final',artifactType:'run_deliverable',artifactId:'a',contentRef:'c' }
const workspace = (entry: any = artifact) => ({ mission:{ missionId:'m' },activeRun:{ runId:'r' },entries:entry ? [entry] : [] })
const mount = () => { const owner = ref<any>({ conversationId:'ctx',visible:true,run:{ missionId:'m',runId:'r',status:'completed' } }); const scope=effectScope(); const status=scope.run(() => useRunDelivery(owner))!; return { owner,scope,status } }
describe('canonical terminal delivery', () => {
  it.each(['ready','missing','foreign','legacy','supporting','no-id','no-content','wrong-mission','error'])('classifies %s evidence', async kind => {
    const entry = { ...artifact }
    if(kind==='foreign') entry.runId='other'
    if(kind==='legacy') entry.identityQuality='legacy'
    if(kind==='supporting') entry.artifactKey='supporting'
    if(kind==='no-id') entry.artifactId=''
    if(kind==='no-content') entry.contentRef=''
    const read=vi.spyOn(agentosApi,'getMissionWorkspace')
    const result=workspace(kind==='missing' ? null : entry)
    if(kind==='wrong-mission') result.mission.missionId='other'
    if(kind==='error') read.mockRejectedValue(new Error('offline')); else read.mockResolvedValue(result as any)
    const { scope,status }=mount(); await flushPromises()
    expect(status.value).toBe(kind==='ready'?'READY':['wrong-mission','error'].includes(kind)?'UNAVAILABLE':'MISSING'); scope.stop()
  })
  it.each(['conversation','run','hidden'])('ignores late evidence after %s change', async kind => {
    let resolve!: (v:any)=>void
    const read=vi.spyOn(agentosApi,'getMissionWorkspace').mockImplementation(() => new Promise(ok=>{ resolve=ok }))
    const { owner,scope,status }=mount()
    const first = resolve
    owner.value={ ...owner.value, ...(kind==='conversation'?{conversationId:'other'}:kind==='hidden'?{visible:false}:{run:{...owner.value.run,runId:'other'}}) }
    await nextTick(); first(workspace()); await flushPromises()
    expect(status.value).not.toBe('READY'); expect(read.mock.calls[0][1]?.signal?.aborted).toBe(true); scope.stop()
  })
  it('deduplicates successful projection across reactivation', async () => {
    const read=vi.spyOn(agentosApi,'getMissionWorkspace').mockResolvedValue(workspace() as any)
    const { owner,scope,status }=mount(); await flushPromises()
    owner.value.visible=false; await nextTick(); owner.value.visible=true; await flushPromises()
    expect(status.value).toBe('READY'); expect(read).toHaveBeenCalledTimes(1); scope.stop()
  })
  it('keeps one in-flight query when an equivalent Run snapshot is refreshed', async () => {
    let resolve!: (v:any)=>void
    const read=vi.spyOn(agentosApi,'getMissionWorkspace').mockImplementation(() => new Promise(ok=>{resolve=ok}))
    const { owner,scope,status }=mount()
    owner.value={ ...owner.value,run:{ ...owner.value.run } }; await nextTick()
    expect(read).toHaveBeenCalledTimes(1)
    expect(read.mock.calls[0][1]?.signal?.aborted).toBe(false)
    resolve(workspace()); await flushPromises(); expect(status.value).toBe('READY'); scope.stop()
  })

})
