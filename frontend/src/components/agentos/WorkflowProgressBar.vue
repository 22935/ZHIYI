<template>
  <section
    class="workflow-progress"
    :class="[phaseClass, `variant-${variant}`]"
    aria-labelledby="workflow-progress-title"
  >
    <div class="workflow-progress__header">
      <div class="workflow-progress__title-wrap">
        <span class="workflow-progress__dot" aria-hidden="true"></span>
        <strong id="workflow-progress-title">ACG 执行状态</strong>
        <span class="workflow-progress__phase">{{ phaseLabel }}</span>
      </div>
      <span class="workflow-progress__elapsed">已运行 {{ elapsedLabel }}</span>
    </div>

    <p class="workflow-progress__message" aria-live="polite">
      {{ displayMessage }}
    </p>

    <div
      class="workflow-progress__track"
      :class="{ 'is-indeterminate': isIndeterminate }"
      role="progressbar"
      aria-valuemin="0"
      aria-valuemax="100"
      :aria-valuenow="isIndeterminate ? undefined : safePercent"
      :aria-valuetext="ariaValueText"
    >
      <span
        class="workflow-progress__fill"
        :style="isIndeterminate ? undefined : { width: `${safePercent}%` }"
      ></span>
    </div>

    <div class="workflow-progress__footer">
      <div class="workflow-progress__metrics">
        <span>{{ stepSummary }}</span>
        <span>当前活动 {{ progress?.activeStepIds.length ?? 0 }}</span>
        <span>恢复 {{ progress?.recoveryCount ?? 0 }} 次</span>
      </div>
      <strong v-if="!isIndeterminate" class="workflow-progress__percent">
        {{ formattedPercent }}
      </strong>
    </div>

    <p v-if="syncError" class="workflow-progress__sync-error" role="status">
      {{ syncError }}
    </p>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch, type DeepReadonly } from 'vue'
import type { WorkflowProgress, WorkflowProgressPhase } from '@/services/api/workflow'

const props = withDefaults(defineProps<{
  progress: DeepReadonly<WorkflowProgress> | null
  loading?: boolean
  syncError?: string | null
  elapsedSeconds?: number
  variant?: 'default' | 'compact'
}>(), {
  loading: false,
  syncError: null,
  elapsedSeconds: undefined,
  variant: 'default'
})

const PHASE_LABELS: Record<WorkflowProgressPhase, string> = {
  understanding: '理解任务',
  planning: '规划任务',
  graph_building: '构建 ACG',
  executing: '执行节点',
  recovery: '恢复执行',
  review: '等待审核',
  completed: '执行完成',
  failed: '执行失败',
  cancelled: '已取消'
}

const now = ref(Date.now())
const timer = window.setInterval(() => {
  if (typeof document === 'undefined' || document.visibilityState === 'visible') now.value = Date.now()
}, 1000)

watch(() => props.progress?.startedAt, () => {
  now.value = Date.now()
})

onBeforeUnmount(() => window.clearInterval(timer))

const phaseLabel = computed(() =>
  props.progress ? PHASE_LABELS[props.progress.phase] : '准备任务'
)
const phaseClass = computed(() => `phase-${props.progress?.phase ?? 'preparing'}`)
const displayMessage = computed(() => {
  if (props.progress?.message?.trim()) return props.progress.message
  if (props.loading) return '任务正在创建，等待运行标识'
  return '正在准备 ACG 运行'
})
const isIndeterminate = computed(() => props.progress?.percent == null)
const safePercent = computed(() => Math.min(100, Math.max(0, props.progress?.percent ?? 0)))
const formattedPercent = computed(() => {
  const value = props.progress?.percent
  if (value == null) return ''
  return `${Number.isInteger(value) ? value.toFixed(0) : value.toFixed(2)}%`
})
const stepSummary = computed(() => {
  const value = props.progress
  if (!value || value.totalSteps <= 0) return '任务规模计算中'
  return `已完成 ${value.completedSteps} / ${value.totalSteps}`
})
const elapsed = computed(() => {
  if (props.elapsedSeconds !== undefined) return Math.max(0, props.elapsedSeconds)
  const startedAt = props.progress?.startedAt
  if (!startedAt) return null
  const started = Date.parse(startedAt)
  if (!Number.isFinite(started)) return null
  const isTerminal = ['completed', 'failed', 'cancelled'].includes(props.progress?.status ?? '')
  const terminalAt = isTerminal && props.progress?.updatedAt
    ? Date.parse(props.progress.updatedAt)
    : Number.NaN
  const end = Number.isFinite(terminalAt) ? terminalAt : now.value
  return Math.max(0, Math.floor((end - started) / 1000))
})
const elapsedLabel = computed(() => {
  if (elapsed.value === null) return '准备中'
  const minutes = Math.floor(elapsed.value / 60)
  const seconds = elapsed.value % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
})
const ariaValueText = computed(() => {
  if (isIndeterminate.value) return `${phaseLabel.value}：${displayMessage.value}`
  return `${phaseLabel.value}，${formattedPercent.value}：${displayMessage.value}`
})
</script>

<style scoped>
.workflow-progress {
  --progress-state: var(--primary-color);
  --progress-gradient-start: color-mix(in srgb, var(--bg-card) 76%, var(--progress-state));
  --progress-gradient-middle: color-mix(in srgb, var(--bg-card) 48%, var(--progress-state));
  --progress-gradient-end: color-mix(in srgb, var(--bg-card) 18%, var(--progress-state));
  padding: 14px 16px;
  overflow: hidden;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-card);
  color: var(--text-regular);
}

.workflow-progress.phase-review,
.workflow-progress.phase-recovery { --progress-state: var(--warning); }
.workflow-progress.phase-completed { --progress-state: var(--success); }
.workflow-progress.phase-failed { --progress-state: var(--danger); }
.workflow-progress.phase-cancelled { --progress-state: var(--text-muted); }

.workflow-progress.variant-compact {
  padding: 10px 12px;
  border-radius: 6px;
}

.workflow-progress.variant-compact .workflow-progress__message { margin: 6px 0 8px; }
.workflow-progress.variant-compact .workflow-progress__footer { margin-top: 7px; }

.workflow-progress__header,
.workflow-progress__footer,
.workflow-progress__title-wrap,
.workflow-progress__metrics {
  display: flex;
  align-items: center;
}

.workflow-progress__header,
.workflow-progress__footer { justify-content: space-between; gap: 12px; }
.workflow-progress__title-wrap { min-width: 0; gap: 8px; }
.workflow-progress__title-wrap strong { color: var(--text-primary); font-size: 13px; }
.workflow-progress__phase,
.workflow-progress__elapsed,
.workflow-progress__metrics { color: var(--text-secondary); font-size: 12px; }
.workflow-progress__phase { white-space: nowrap; }
.workflow-progress__elapsed { flex: none; }
.workflow-progress__dot {
  width: 7px;
  height: 7px;
  flex: none;
  border-radius: 50%;
  background: var(--progress-state);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--progress-state) 16%, transparent);
}

.workflow-progress__message {
  margin: 9px 0 10px;
  overflow-wrap: anywhere;
  color: var(--text-primary);
  font-size: 13px;
  line-height: 1.5;
}

.workflow-progress__track {
  position: relative;
  height: 8px;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--progress-state) 28%, var(--border-light));
  border-radius: 999px;
  background: color-mix(in srgb, var(--bg-input) 92%, var(--progress-state));
  box-shadow: inset 0 1px 2px color-mix(in srgb, var(--text-primary) 6%, transparent);
}

.workflow-progress__fill {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(
    90deg,
    var(--progress-gradient-start) 0%,
    var(--progress-gradient-middle) 48%,
    var(--progress-gradient-end) 100%
  );
  box-shadow: 0 0 10px color-mix(in srgb, var(--progress-state) 28%, transparent);
  transition: width 240ms ease;
}

.workflow-progress__track.is-indeterminate .workflow-progress__fill {
  position: absolute;
  width: 34%;
  background: linear-gradient(
    90deg,
    transparent,
    var(--progress-gradient-middle),
    var(--progress-gradient-end),
    transparent
  );
  animation: progress-flow 1.4s ease-in-out infinite;
}

.workflow-progress__footer { margin-top: 9px; }
.workflow-progress__metrics { gap: 16px; flex-wrap: wrap; }
.workflow-progress__percent { color: var(--progress-state); font-size: 12px; }
.workflow-progress__sync-error {
  margin: 9px 0 0;
  padding-top: 8px;
  border-top: 1px solid var(--border-light);
  color: var(--warning);
  font-size: 12px;
}

@keyframes progress-flow {
  from { transform: translateX(-110%); }
  to { transform: translateX(300%); }
}

@media (max-width: 640px) {
  .workflow-progress__header,
  .workflow-progress__footer { align-items: flex-start; flex-wrap: wrap; }
  .workflow-progress__metrics { width: 100%; gap: 8px 14px; }
}

@media (prefers-reduced-motion: reduce) {
  .workflow-progress__fill { transition: none; }
  .workflow-progress__track.is-indeterminate .workflow-progress__fill {
    left: 33%;
    animation: none;
    background: linear-gradient(90deg, transparent, var(--progress-gradient-middle), var(--progress-gradient-end), transparent);
  }
}
</style>
