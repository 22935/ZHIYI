<template>
  <section class="agentos-run-summary" aria-label="执行运行时 运行态摘要">
    <header>
      <div><span class="eyebrow">Execution Runtime</span><strong>运行态摘要</strong></div>
      <span class="status" :class="statusClass">{{ statusLabel }}</span>
    </header>
    <p v-if="lifecycle.synchronizationState !== 'SYNCED'" role="status">运行状态同步：{{ lifecycle.synchronizationState }}</p>
    <p class="activity-note" :class="{ active: hasRuntimeActivity }">{{ activityLabel }}</p>
    <div class="summary-grid">
      <div class="summary-primary"><small>图版本</small><b>{{ metric(summary.graphVersion) }}</b></div>
      <div><small>总步骤</small><b>{{ metric(summary.totalSteps) }}</b></div>
      <div><small>已完成</small><b>{{ metric(summary.completedSteps) }}</b></div>
      <div><small>活动步骤</small><b>{{ metric(summary.activeSteps) }}</b></div>
      <div><small>条件跳过</small><b>{{ metric(summary.skippedSteps) }}</b></div>
      <div><small>恢复次数</small><b>{{ metric(summary.recoveryCount) }}</b></div>
      <div><small>Patch 引用</small><b>{{ metric(summary.patchRefCount) }}</b></div>
      <div><small>审计事件</small><b>{{ metric(summary.auditEventCount) }}</b></div>
    </div>
    <div v-if="hasAuditBreakdown" class="event-breakdown" aria-label="运行审计来源">
      <span>Trace {{ summary.auditEventCount }}</span>
      <span>Checkpoint {{ checkpointCount }}</span>
      <span>Review {{ reviewCount }}</span>
      <span>血缘 {{ summary.provenanceCount }}</span>
    </div>
  </section>
</template>

<script setup lang="ts">
import { projectRunLifecycle, type RunLifecycleProjection } from '@/features/workspace/runLifecycle'
import { computed, type DeepReadonly } from 'vue'
import type {
  AcgView,
  TraceEvent,
  WorkflowProgress,
  WorkflowRun
} from '@/services/api/workflow'

const props = withDefaults(defineProps<{
  lifecycle?: RunLifecycleProjection
  progress?: DeepReadonly<WorkflowProgress> | null
  run?: WorkflowRun | null
  view?: AcgView | null
  events?: TraceEvent[]
  checkpointCount?: number
  reviewCount?: number
}>(), {
  progress: null,
  run: null,
  view: null,
  events: () => [],
  checkpointCount: 0,
  reviewCount: 0
})

const lifecycle = computed(() => props.lifecycle ?? projectRunLifecycle({ missionId: props.run?.missionId || '', runId: props.run?.runId || '', run: props.run, progress: props.run ? props.progress : null }))
const displayedRun = computed(() => props.run?.runId === lifecycle.value.runId && props.run?.missionId === lifecycle.value.missionId ? props.run : null)
const displayedView = computed(() => props.view?.runId === lifecycle.value.runId ? props.view : null)
const status = computed(() => lifecycle.value.normalizedStatus)
const statusClass = computed(() => status.value)
const statusLabel = computed(() => lifecycle.value.statusLabel)

const uniqueEventCount = computed(() => {
  const ids = new Set<string>()
  const sources = [
    ...props.events.filter(event => event.runId === lifecycle.value.runId),
    ...(displayedView.value?.recoveryTrace || []),
    ...(displayedView.value?.scheduleTrace || []),
    ...(displayedView.value?.contractViolations || [])
  ]
  sources.forEach((event, index) => ids.add(event.eventId || `${event.eventType}:${event.createdAt || index}`))
  return ids.size
})

const summary = computed(() => {
  const runSteps = displayedRun.value?.steps || []
  const viewSteps = displayedView.value?.stepStates || []
  const steps = runSteps.length ? runSteps : viewSteps
  const count = (stepStatus: string) => steps.filter(step => step.status === stepStatus).length
  const patchRefs = new Set<string>()
  return {
    graphVersion: displayedView.value?.graphVersion ?? displayedRun.value?.graphVersion ?? null,
    totalSteps: lifecycle.value.progress?.totalSteps ?? steps.length,
    completedSteps: lifecycle.value.progress?.completedSteps ?? count('completed'),
    activeSteps: lifecycle.value.progress?.activeStepIds?.length ?? displayedRun.value?.activeStepIds?.length ?? count('running'),
    skippedSteps: displayedRun.value?.skippedStepIds?.length ?? count('skipped_by_condition'),
    recoveryCount: displayedView.value?.lowEntropyMetrics?.recoveryCount ?? count('retrying'),
    patchRefCount: patchRefs.size,
    auditEventCount: uniqueEventCount.value,
    provenanceCount: displayedView.value?.interactions?.length ?? 0
  }
})

const hasRuntimeActivity = computed(() => (
  summary.value.patchRefCount > 0
  || summary.value.recoveryCount > 0
  || summary.value.skippedSteps > 0
  || summary.value.auditEventCount > 0
))
const hasAuditBreakdown = computed(() => (
  summary.value.auditEventCount > 0
  || props.checkpointCount > 0
  || props.reviewCount > 0
  || summary.value.provenanceCount > 0
))
const activityLabel = computed(() => {
  if (!hasRuntimeActivity.value) {
    return status.value === 'completed'
      ? '本次运行按已提交的 ACG 完成，未记录恢复或图变更引用。'
      : '当前按已提交的 ACG 执行，等待可验证的运行审计事件。'
  }
  const parts = []
  if (summary.value.patchRefCount) parts.push(`${summary.value.patchRefCount} 个 GraphPatch 引用`)
  if (summary.value.recoveryCount) parts.push(`${summary.value.recoveryCount} 次恢复`)
  if (summary.value.skippedSteps) parts.push(`${summary.value.skippedSteps} 个条件跳过`)
  return parts.length ? `已记录 ${parts.join('、')}。` : `已记录 ${summary.value.auditEventCount} 条运行审计事件。`
})

const metric = (value: number | null | undefined) => value === null || value === undefined ? '—' : value
</script>

<style scoped>
.agentos-run-summary {
  container: agentos-run-summary / inline-size;
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  max-width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--border-light);
  border-radius: 9px;
  background: var(--bg-card);
}
header, header > div { display: flex; min-width: 0; align-items: center; }
header { justify-content: space-between; gap: 12px; }
header > div { flex-wrap: wrap; gap: 4px 9px; }
.eyebrow { color: var(--text-secondary); font-size: 11px; letter-spacing: .04em; text-transform: uppercase; }
header strong { color: var(--text-primary); font-size: 13px; }
.status { flex: 0 0 auto; padding: 3px 8px; border-radius: 999px; background: var(--bg-input); color: var(--text-secondary); font-size: 11px; font-weight: 700; }
.status.running { color: var(--sem-running); }
.status.retrying { color: var(--sem-retry); }
.status.waiting_review { color: var(--sem-waiting); }
.status.completed { color: var(--sem-success); }
.status.failed, .status.cancelled { color: var(--sem-failed); }
.activity-note { margin: 7px 0 0; color: var(--text-secondary); font-size: 11px; line-height: 1.5; text-wrap: pretty; }
.activity-note.active { color: var(--primary-color); }
.summary-grid { display: grid; min-width: 0; grid-template-columns: repeat(8, minmax(0, 1fr)); gap: 7px; margin-top: 10px; }
.summary-grid > div { min-width: 0; padding: 7px 8px; border-radius: 7px; background: var(--bg-panel); }
.summary-grid small { display: block; color: var(--text-secondary); font-size: 10px; line-height: 1.3; overflow-wrap: anywhere; }
.summary-grid b { display: block; margin-top: 3px; color: var(--text-primary); font-size: 15px; }
.summary-primary { background: color-mix(in srgb, var(--primary-color) 9%, var(--bg-panel)) !important; }
.summary-primary b { color: var(--primary-color); }
.event-breakdown { display: flex; flex-wrap: wrap; gap: 6px 14px; margin-top: 8px; color: var(--text-secondary); font-size: 10px; }
@container agentos-run-summary (max-width: 680px) {
  .summary-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
}
@container agentos-run-summary (max-width: 360px) {
  .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  header > div { align-items: flex-start; flex-direction: column; gap: 2px; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition: none !important; }
}
</style>
