import { onScopeDispose, ref, watch, type Ref } from 'vue'
import { agentosApi, type WorkflowRun } from '@/services/api/agentos'
import { isRunDeliverableEntry } from '@/workbench/runtime/deliverableIdentity'
export type DeliveryStatus = 'NOT_COMPLETE' | 'READY' | 'MISSING' | 'UNAVAILABLE'
export function useRunDelivery(owner: Ref<{ conversationId: string; run: WorkflowRun | null; visible: boolean }>) {
  const status = ref<DeliveryStatus>('NOT_COMPLETE')
  const cache = new Map<string, DeliveryStatus>()
  let generation = 0
  let controller: AbortController | undefined
  watch(() => JSON.stringify([owner.value.conversationId, owner.value.run?.missionId, owner.value.run?.runId,
    owner.value.run?.status, owner.value.visible]), async () => {
    const current = ++generation
    controller?.abort()
    const { run, visible } = owner.value
    status.value = 'NOT_COMPLETE'
    if (!visible || !run || !['completed', 'succeeded'].includes(run.status)) return
    status.value = 'UNAVAILABLE'
    const key = JSON.stringify([run.missionId, run.runId])
    if (cache.has(key)) { status.value = cache.get(key)!; return }
    controller = new AbortController()
    try {
      const workspace = await agentosApi.getMissionWorkspace(run.missionId, { runId: run.runId, signal: controller.signal })
      if (current !== generation) return
      if (workspace.mission.missionId !== run.missionId || workspace.activeRun?.runId !== run.runId) return
      const ready = workspace.entries.some(entry => entry.kind === 'artifact' && entry.runId === run.runId
        && entry.identityQuality === 'canonical' && isRunDeliverableEntry(entry)
        && Boolean(entry.artifactId?.trim() && entry.contentRef?.trim()))
      status.value = ready ? 'READY' : 'MISSING'
      cache.set(key, status.value)
    } catch { /* Unverified is distinct from an observed missing deliverable. */ }
  }, { immediate: true, flush: 'sync' })
  onScopeDispose(() => { generation++; controller?.abort() })
  return status
}
