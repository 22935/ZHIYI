<template>
  <InspectorSection title="Execution" :badge="statusBadge">
    <div class="execution-summary">
      <div class="execution-summary__status">
        <span class="execution-summary__dot" :class="`is-${statusTone}`" aria-hidden="true"></span>
        <strong>{{ statusLabel }}</strong>
      </div>
      <div class="execution-summary__count">
        <strong>{{ entry.attemptCount ?? 0 }}</strong>
        <span>执行次数</span>
      </div>
    </div>
    <button
      type="button"
      class="inspector-disclosure"
      :aria-expanded="detailsExpanded"
      @click="detailsExpanded = !detailsExpanded"
    >
      <span>Latest Attempt</span>
      <code :title="latestAttemptId || undefined">{{ latestAttemptId || '未观测' }}</code>
    </button>
    <div v-if="detailsExpanded" class="execution-details">
      <InspectorPropertyList :rows="[
        { label: 'Attempt ID', value: latestAttemptId, code: true },
        { label: 'Runtime Status', value: runtimeStatus, code: true }
      ]" />
    </div>
    <details v-for="item in attempts" :key="item.attempt.attemptId" class="execution-details">
      <summary>Attempt {{ item.attempt.attemptNumber }} · {{ item.attempt.status }} · {{ item.attempt.attemptId }}</summary>
      <InspectorPropertyList :rows="[
        { label: 'Run', value: item.attempt.runId, code: true },
        { label: 'Task', value: item.attempt.taskId, code: true },
        { label: 'Failure', value: item.attempt.failureReason || 'NOT_OBSERVED' },
        { label: 'Executions', value: item.executions.map(execution => `${execution.stepExecutionId}: ${execution.status}`).join(', ') || 'NOT_OBSERVED' }
      ]" />
    </details>
    <p v-if="!attempts.length">Attempt history NOT_OBSERVED。Task 状态保留 Workspace 的语义投影，不由某一次 Attempt 推断。</p>
  </InspectorSection>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { WorkspaceEntry } from '@/services/api/agentos'
import InspectorPropertyList from '@/components/workbench/InspectorPropertyList.vue'
import InspectorSection from '@/components/workbench/InspectorSection.vue'
import { statusSemanticTone } from '@/utils/statusSemantic'
import type { RuntimeObservation } from '@/workbench/runtime/observation'

const props = defineProps<{ entry: WorkspaceEntry; runId?: string | null; runtimeObservation?: RuntimeObservation | null }>()
const attempts = computed(() => {
  const runId = props.runId || props.entry.runId
  const observation = props.runtimeObservation
  if (!runId || observation?.runId !== runId || observation.executionTree?.run.runId !== runId) return []
  return observation.executionTree.nodes.filter(node => (props.entry.taskId && node.task.taskId === props.entry.taskId)
    || (props.entry.semanticTaskKey && node.task.semanticTaskKey === props.entry.semanticTaskKey)
    || (props.entry.acgNodeId && node.acgNodeId === props.entry.acgNodeId))
    .flatMap(node => node.attempts).filter(item => item.attempt.runId === runId)
    .sort((a, b) => a.attempt.attemptNumber - b.attempt.attemptNumber)
})
const detailsExpanded = ref(false)
const latestAttemptId = computed(() => props.entry.latestAttemptId || props.entry.attemptId || null)
const statusValue = computed(() => props.entry.status || 'pending')
const statusBadge = computed(() => statusValue.value.toUpperCase())
const statusLabel = computed(() => ({
  completed: '已完成',
  succeeded: '已完成',
  failed: '失败',
  cancelled: '已取消',
  running: '运行中',
  planning: '规划中',
  executing: '执行中',
  pending: '待执行'
}[statusValue.value] || statusValue.value))
const statusTone = computed(() => {
  const tone = statusSemanticTone(statusValue.value)
  if (tone === 'success') return 'success'
  if (tone === 'failed') return 'danger'
  if (tone === 'running') return 'active'
  if (tone === 'waiting') return 'waiting'
  if (tone === 'retry') return 'retry'
  return 'muted'
})
const runtimeStatus = computed(() => String(props.entry.metadata?.runtimeStatus || '未观测'))
</script>

<style scoped>
.execution-summary { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 42px; padding: 9px 10px; border: 1px solid var(--wb-border-soft); border-radius: var(--wb-radius-sm); background: var(--wb-surface-inset); }
.execution-summary__status { display: flex; align-items: center; gap: 8px; min-width: 0; color: var(--wb-text); }
.execution-summary__status strong { font-size: 13px; font-weight: 650; }
.execution-summary__dot { width: 8px; height: 8px; flex: none; border-radius: 50%; background: var(--wb-text-muted); }
.execution-summary__dot.is-success { background: var(--wb-success); }
.execution-summary__dot.is-danger { background: var(--wb-danger); }
.execution-summary__dot.is-active { background: var(--wb-accent); }
.execution-summary__dot.is-waiting { background: var(--wb-warning); }
.execution-summary__dot.is-retry { background: var(--wb-retry); }
.execution-summary__count { display: grid; justify-items: end; gap: 2px; }
.execution-summary__count strong { color: var(--wb-text); font: 600 18px/1 var(--font-mono, monospace); font-variant-numeric: tabular-nums; }
.execution-summary__count span { color: var(--wb-text-muted); font-size: 10px; }
.inspector-disclosure { display: flex; align-items: center; justify-content: space-between; width: 100%; margin-top: 10px; padding: 8px 0; border: 0; border-top: 1px solid var(--wb-border-soft); color: var(--wb-text-secondary); background: transparent; cursor: pointer; font-size: 11px; text-align: left; }
.inspector-disclosure:hover { color: var(--wb-text); }
.inspector-disclosure code { max-width: 62%; overflow: hidden; color: var(--wb-text-muted); font: 10px var(--font-mono, monospace); text-overflow: ellipsis; white-space: nowrap; }
.execution-details { padding-top: 1px; }
</style>
