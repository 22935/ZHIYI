<template>
  <section class="dynamic-run-summary" aria-label="动态运行摘要">
    <header>
      <div><span class="eyebrow">Runtime Graph</span><strong>动态运行摘要</strong></div>
      <span class="status" :class="summary.status">{{ statusLabel }}</span>
    </header>
    <div class="summary-grid">
      <div class="summary-primary"><small>图版本</small><b>v{{ summary.graphVersion }}</b></div>
      <div><small>动态步骤</small><b>{{ summary.dynamicStepCount }}</b></div>
      <div><small>绑定切换</small><b>{{ summary.bindingSwitchCount }}</b></div>
      <div><small>条件决策</small><b>{{ summary.conditionalDecisionCount }}</b></div>
      <div><small>条件跳过</small><b>{{ summary.skippedByConditionCount }}</b></div>
      <div><small>已应用 Patch</small><b>{{ summary.appliedPatchCount }}</b></div>
      <div><small>待处理事件</small><b>{{ summary.pendingRuntimeEventCount }}</b></div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, type DeepReadonly } from 'vue'
import type { AcgView, WorkflowProgress, WorkflowRun } from '@/services/api/workflow'
import { buildDynamicRunSummary } from '@/utils/runtimePresentation'

const props = defineProps<{
  progress?: DeepReadonly<WorkflowProgress> | null
  run?: WorkflowRun | null
  view?: AcgView | null
}>()

const summary = computed(() => buildDynamicRunSummary(props.progress, props.run, props.view))
const statusLabel = computed(() => ({
  pending: '等待中', planning: '规划中', running: '运行中', waiting_review: '待审核',
  retrying: '恢复中', failed: '失败', completed: '已完成', cancelled: '已取消'
}[summary.value.status] || summary.value.status))
</script>

<style scoped>
.dynamic-run-summary {
  container: dynamic-run-summary / inline-size;
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
.status.running, .status.retrying { color: var(--info); }
.status.waiting_review { color: var(--warning); }
.status.completed { color: var(--success); }
.status.failed, .status.cancelled { color: var(--danger); }
.summary-grid { display: grid; min-width: 0; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 7px; margin-top: 10px; }
.summary-grid > div { min-width: 0; padding: 7px 8px; border-radius: 7px; background: var(--bg-panel); }
.summary-grid small { display: block; color: var(--text-secondary); font-size: 10px; line-height: 1.3; overflow-wrap: anywhere; }
.summary-grid b { display: block; margin-top: 3px; color: var(--text-primary); font-size: 15px; }
.summary-primary { background: color-mix(in srgb, var(--primary-color) 9%, var(--bg-panel)) !important; }
.summary-primary b { color: var(--primary-color); }
@container dynamic-run-summary (max-width: 680px) {
  .summary-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
}
@container dynamic-run-summary (max-width: 360px) {
  .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  header > div { align-items: flex-start; flex-direction: column; gap: 2px; }
}
</style>
